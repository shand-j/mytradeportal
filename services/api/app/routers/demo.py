"""Public, no-auth demo of the AI quote generator for the marketing site.

Lets a visitor on the landing page try "generate a guide-priced quote from a
job description" without login, tenant, or email. Two endpoints:

* ``POST /demo/quotes/generate`` — retrieve → generate → validate → respond.
* ``POST /demo/quotes/refine`` — stateless regeneration of the AI lines only.

Statelessness is the core constraint: quotes are generated, returned, and
never stored. The only durable writes are :class:`DemoQuoteEvent` rows — a
count of generations plus marketing metadata (salted IP hash, browser headers,
UTM parameters). Job descriptions, generated quotes and line items are never
persisted.

Rate limits are per source IP (the default limiter key), generous enough for
genuine exploration but tight enough to cap LLM spend from a single address.
"""

from __future__ import annotations

import hashlib
import time
from decimal import Decimal
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.models import DemoQuoteEvent
from app.rag import (
    generate_quote_from_prompt,
    search_cost_items_with_status,
    validate_generated_quote,
)
from app.routers.quotes import _fallback_line_items, _intake_completeness

router = APIRouter(prefix="/demo", tags=["demo"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = structlog.get_logger("api.demo")

# Demo represents a typical VAT-registered UK domestic electrician. These keys
# mirror the tenant settings the RAG pipeline reads (source of truth:
# ``app/rag/generation.py::_build_user_prompt`` reads ``minimum_charge`` /
# ``markup_percent`` / ``hourly_labour_rate`` and
# ``app/rag/validation.py::validate_generated_quote`` reads ``minimum_charge``
# and ``hourly_labour_rate``; the Tenant convenience properties in
# ``app/models.py`` confirm the same key names and defaults). Both spellings
# of the markup key are supplied because the prompt builder and the Tenant
# model historically disagreed on ``markup_percent`` vs ``markup_percentage``.
DEMO_TENANT_SETTINGS: dict[str, Any] = {
    "hourly_labour_rate": "65.00",
    "daily_labour_rate": "450.00",
    "minimum_charge": "80.00",
    "markup_percent": "20",
    "markup_percentage": "20",
    "vat_rate": "20",
}

# The demo business is VAT-registered, so quotes carry the UK standard rate.
DEMO_VAT_RATE = Decimal("0.20")

_MONEY_QUANTIZE = Decimal("0.01")
_LLM_BUSY_MESSAGE = "The AI is busy right now — try again in a moment."


class DemoQuoteGenerateRequest(BaseModel):
    description: str = Field(min_length=20, max_length=4000)
    property_type: str | None = None
    site_survey: dict[str, Any] | None = None
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)


class DemoLineItem(BaseModel):
    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "ea"
    unit_price: Decimal = Decimal("0.00")
    ai_generated: bool = False


class DemoQuoteRefineRequest(BaseModel):
    """Stateless refine: the caller round-trips the generate response's lines."""

    description: str = Field(min_length=20, max_length=4000)
    instructions: str = Field(min_length=3, max_length=1000)
    line_items: list[DemoLineItem] = Field(min_length=1)
    property_type: str | None = None
    site_survey: dict[str, Any] | None = None


class DemoLineItemRead(BaseModel):
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    total: Decimal
    ai_generated: bool


class DemoQuoteAI(BaseModel):
    confidence: float
    warnings: list[str]
    assumptions: list[str]
    notes: str | None = None


class DemoQuoteResponse(BaseModel):
    """Mirrors the AI-relevant fields of ``QuoteRead`` for the demo client."""

    line_items: list[DemoLineItemRead]
    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal
    ai: DemoQuoteAI
    retrieval_status: str | None = None
    generation_seconds: float


def _client_ip_hash(request: Request) -> str:
    """Salted sha256 of the source IP — the raw IP is never persisted."""
    ip = get_remote_address(request)
    return hashlib.sha256(f"{ip}|{settings.auth_secret_key}".encode()).hexdigest()


async def _record_demo_event(
    db: AsyncSession,
    request: Request,
    data: DemoQuoteGenerateRequest | DemoQuoteRefineRequest,
    generation_seconds: float,
) -> None:
    """Insert one usage row. A storage failure must never break the demo."""
    utm = (
        {
            "utm_source": data.utm_source,
            "utm_medium": data.utm_medium,
            "utm_campaign": data.utm_campaign,
        }
        if isinstance(data, DemoQuoteGenerateRequest)
        else {}
    )
    event = DemoQuoteEvent(
        ip_hash=_client_ip_hash(request),
        user_agent=(request.headers.get("user-agent") or None),
        accept_language=(request.headers.get("accept-language") or None),
        referer=(request.headers.get("referer") or None),
        generation_seconds=generation_seconds,
        **utm,
    )
    try:
        db.add(event)
        await db.commit()
    except Exception as exc:  # analytics must never fail the demo
        await db.rollback()
        logger.warning(
            "demo_event_insert_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )


def _build_response(
    line_items: list[DemoLineItem],
    ai: DemoQuoteAI,
    retrieval_status: str | None,
    generation_seconds: float,
) -> DemoQuoteResponse:
    subtotal = Decimal("0")
    reads: list[DemoLineItemRead] = []
    for item in line_items:
        total = (item.quantity * item.unit_price).quantize(_MONEY_QUANTIZE)
        subtotal += total
        reads.append(
            DemoLineItemRead(
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                total=total,
                ai_generated=item.ai_generated,
            )
        )
    subtotal = subtotal.quantize(_MONEY_QUANTIZE)
    total = (subtotal * (Decimal("1") + DEMO_VAT_RATE)).quantize(_MONEY_QUANTIZE)
    return DemoQuoteResponse(
        line_items=reads,
        subtotal=subtotal,
        vat_rate=DEMO_VAT_RATE,
        vat_amount=total - subtotal,
        total=total,
        ai=ai,
        retrieval_status=retrieval_status,
        generation_seconds=generation_seconds,
    )


def _run_validation(
    generated: dict[str, Any],
    retrieved: list[dict[str, Any]],
    description: str,
    property_type: str | None,
    site_survey: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate LLM output, falling back to guide-priced demo lines when empty.

    Reuses the tenant pipeline's completeness scoring and fallback catalogue
    so the demo behaves like a real tenant generation.
    """
    completeness = _intake_completeness(
        description,
        property_type=property_type,
        site_survey=site_survey,
    )
    validated = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings=DEMO_TENANT_SETTINGS,
        completeness=completeness,
    )
    if not validated["line_items"]:
        validated["warnings"].append(
            "The AI could not draft line items for this description; "
            "guide-price defaults were used."
        )
        validated["line_items"] = [
            {
                "description": line["description"],
                "quantity": line["quantity"],
                "unit_price": line["unit_price"],
                "unit": "ea",
            }
            for line in _fallback_line_items(description)
        ]
    return validated


def _ai_from_validated(validated: dict[str, Any]) -> DemoQuoteAI:
    return DemoQuoteAI(
        confidence=validated["confidence"],
        warnings=validated["warnings"],
        assumptions=validated.get("assumptions", []),
        notes=validated.get("notes"),
    )


@router.post("/quotes/generate")
@limiter.limit("5/minute;50/day")
async def demo_generate_quote(
    request: Request,
    data: DemoQuoteGenerateRequest,
    db: DbDep,
) -> DemoQuoteResponse:
    """Generate a guide-priced quote for a job description. No auth required."""
    started = time.perf_counter()
    try:
        retrieved, retrieval_status = await search_cost_items_with_status(data.description)
        generated = await generate_quote_from_prompt(
            job_description=data.description,
            cost_items=retrieved,
            tenant_settings=DEMO_TENANT_SETTINGS,
            property_type=data.property_type,
            site_survey=data.site_survey,
        )
    except RuntimeError as exc:
        logger.error("demo_quote_llm_error", error=str(exc)[:300])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_LLM_BUSY_MESSAGE,
        ) from exc
    generation_seconds = round(time.perf_counter() - started, 2)

    validated = _run_validation(
        generated, retrieved, data.description, data.property_type, data.site_survey
    )
    line_items = [
        DemoLineItem(
            description=line["description"],
            quantity=line["quantity"],
            unit=line.get("unit") or "ea",
            unit_price=line["unit_price"],
            ai_generated=True,
        )
        for line in validated["line_items"]
    ]
    await _record_demo_event(db, request, data, generation_seconds)
    return _build_response(
        line_items,
        _ai_from_validated(validated),
        retrieval_status,
        generation_seconds,
    )


@router.post("/quotes/refine")
@limiter.limit("10/minute;100/day")
async def demo_refine_quote(
    request: Request,
    data: DemoQuoteRefineRequest,
    db: DbDep,
) -> DemoQuoteResponse:
    """Statelessly regenerate the AI-drafted lines from visitor instructions.

    Mirrors the tenant refine: lines with ``ai_generated=false`` are preserved
    untouched and only the AI lines are regenerated from the original
    description plus the refinement instructions.
    """
    ai_items = [li for li in data.line_items if li.ai_generated]
    manual_items = [li for li in data.line_items if not li.ai_generated]

    current_ai_lines = "\n".join(
        f"- {li.description} | quantity {li.quantity} | unit price £{li.unit_price}"
        for li in ai_items
    )
    description = (
        f"Customer job description:\n{data.description}\n\n"
        f"AI-drafted line items to regenerate:\n{current_ai_lines or '(none)'}\n\n"
    )
    if manual_items:
        manual_lines = "\n".join(
            f"- {li.description} | quantity {li.quantity} | unit price £{li.unit_price}"
            for li in manual_items
        )
        description += (
            "Manually added line items (final — they are kept separately; do NOT "
            f"include them in your response):\n{manual_lines}\n\n"
        )
    description += (
        "Electrician's refinement instructions (apply these to the line items):\n"
        f"{data.instructions}"
    )

    started = time.perf_counter()
    try:
        retrieved, retrieval_status = await search_cost_items_with_status(
            f"{data.description} {data.instructions}"
        )
        generated = await generate_quote_from_prompt(
            job_description=description,
            cost_items=retrieved,
            tenant_settings=DEMO_TENANT_SETTINGS,
            property_type=data.property_type,
            site_survey=data.site_survey,
        )
    except RuntimeError as exc:
        logger.error("demo_quote_refine_llm_error", error=str(exc)[:300])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_LLM_BUSY_MESSAGE,
        ) from exc
    generation_seconds = round(time.perf_counter() - started, 2)

    validated = _run_validation(
        generated, retrieved, data.description, data.property_type, data.site_survey
    )

    # Dedupe safety (same as the tenant refine): drop regenerated lines that
    # exactly duplicate a preserved manual line.
    manual_keys = {(li.description.strip().lower(), li.unit_price) for li in manual_items}
    kept_lines: list[DemoLineItem] = list(manual_items)
    for line in validated["line_items"]:
        key = (str(line["description"]).strip().lower(), line["unit_price"])
        if key in manual_keys:
            validated["warnings"].append(
                f"Dropped duplicate of manual line '{line['description']}' from the AI regeneration"
            )
            continue
        kept_lines.append(
            DemoLineItem(
                description=line["description"],
                quantity=line["quantity"],
                unit=line.get("unit") or "ea",
                unit_price=line["unit_price"],
                ai_generated=True,
            )
        )

    await _record_demo_event(db, request, data, generation_seconds)
    return _build_response(
        kept_lines,
        _ai_from_validated(validated),
        retrieval_status,
        generation_seconds,
    )
