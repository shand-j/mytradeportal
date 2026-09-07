"""Quote endpoints."""

import asyncio
import time
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import Actions, write_audit_log
from app.calculations import build_invoice_from_quote, calculate_quote_totals
from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.email import send_email
from app.email_templates import quote_ready as quote_ready_template
from app.limiter import limiter, tenant_key
from app.models import (
    BillOfQuantities,
    Communication,
    Contact,
    Quote,
    QuoteLineItem,
    QuoteRequest,
    Tenant,
)
from app.push import notify_customer
from app.rag import (
    estimate_llm_cost_usd,
    generate_quote_from_prompt,
    search_cost_items_with_status,
    validate_generated_quote,
)
from app.rag.validation import build_quote_from_validation
from app.rls import set_tenant_in_session
from app.routers.invoices import _get_invoice, generate_invoice_number
from app.schemas import (
    InvoiceRead,
    QuoteApprove,
    QuoteConvertToInvoice,
    QuoteCreate,
    QuoteGenerateAsyncResponse,
    QuoteGenerateRequest,
    QuoteRead,
    QuoteRefineRequest,
    QuoteUpdate,
)

router = APIRouter(prefix="/quotes", tags=["Quotes"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
MONEY_QUANTIZE = Decimal("0.01")
logger = structlog.get_logger("api.quotes")


async def _get_quote(db: AsyncSession, tenant_id: UUID, quote_id: UUID) -> Quote:
    await set_tenant_in_session(db, tenant_id)
    result = await db.execute(
        select(Quote)
        .options(
            selectinload(Quote.line_items),
            selectinload(Quote.contact),
            selectinload(Quote.bill_of_quantities).selectinload(BillOfQuantities.line_items),
        )
        .where(Quote.id == quote_id, Quote.tenant_id == tenant_id)
    )
    quote = result.scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return quote


@router.get("")
async def list_quotes(tenant: TenantDep, db: DbDep) -> list[QuoteRead]:
    """List quotes for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(
        select(Quote)
        .options(
            selectinload(Quote.line_items),
            selectinload(Quote.contact),
            selectinload(Quote.bill_of_quantities).selectinload(BillOfQuantities.line_items),
        )
        .where(Quote.tenant_id == tenant.id)
        .order_by(Quote.created_at.desc())
    )
    return [QuoteRead.model_validate(q) for q in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_quote(
    data: QuoteCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Create a quote with line items."""
    await set_tenant_in_session(db, tenant.id)

    contact = await db.get(Contact, data.contact_id)
    if contact is None or contact.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    quote = Quote(
        tenant_id=tenant.id,
        contact_id=data.contact_id,
        title=data.title,
        description=data.description,
        vat_rate=data.vat_rate,
        valid_until=data.valid_until,
    )
    quote.line_items = [
        QuoteLineItem(tenant_id=tenant.id, **item.model_dump()) for item in data.line_items
    ]
    calculate_quote_totals(quote)

    db.add(quote)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_CREATED,
        entity_type="quote",
        entity_id=quote.id,
        payload={"title": quote.title, "total": str(quote.total)},
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.get("/{quote_id}")
async def get_quote(quote_id: UUID, tenant: TenantDep, db: DbDep) -> QuoteRead:
    """Get a single quote."""
    quote = await _get_quote(db, tenant.id, quote_id)
    return QuoteRead.model_validate(quote)


@router.patch("/{quote_id}")
async def update_quote(
    quote_id: UUID,
    data: QuoteUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Update a quote's details, status, or line items."""
    quote = await _get_quote(db, tenant.id, quote_id)
    update_data = data.model_dump(exclude_unset=True)

    if "line_items" in update_data:
        new_items = update_data.pop("line_items")
        for item in list(quote.line_items):
            await db.delete(item)
        quote.line_items = [QuoteLineItem(tenant_id=tenant.id, **item) for item in new_items]
        calculate_quote_totals(quote)

    for key, value in update_data.items():
        setattr(quote, key, value)

    _refresh_ai_feedback(quote)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_UPDATED,
        entity_type="quote",
        entity_id=quote.id,
        payload={"changed_fields": sorted(data.model_dump(exclude_unset=True).keys())},
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/send")
async def send_quote(
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Mark a quote as sent."""
    quote = await _get_quote(db, tenant.id, quote_id)
    quote.status = "sent"
    quote.sent_at = datetime.utcnow()
    _refresh_ai_feedback(quote)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_SENT,
        entity_type="quote",
        entity_id=quote.id,
    )
    # Notify the linked homeowner (when the quote is linked to a customer
    # account via its quote_request) so their bell + push fires as soon as the
    # electrician sends.
    if quote.quote_request_id is not None:
        quote_request = await db.get(QuoteRequest, quote.quote_request_id)
        if quote_request is not None and quote_request.customer_id is not None:
            await notify_customer(
                db,
                tenant.id,
                quote_request.customer_id,
                kind="quote_sent",
                title="Your quote is ready to review",
                body=f"Your electrician sent you a quote for '{quote.title}'.",
                link=f"/customer/quote/{quote.id}",
            )
    # Email the customer a review link. Non-fatal — if delivery fails they
    # can still open the quote from the mobile app via the notification.
    contact = await db.get(Contact, quote.contact_id)
    tenant_row = await db.get(Tenant, tenant.id)
    if contact is not None and contact.email:
        app_origin = (
            settings.app_public_url.rstrip("/") if settings.app_public_url else ""
        )
        view_url = f"{app_origin}/customer/quote/{quote.id}" if app_origin else f"/customer/quote/{quote.id}"
        business_name = tenant_row.name if tenant_row is not None else "Your electrician"
        subject, html, text = quote_ready_template(
            customer_name=contact.name.split()[0] if contact.name else "there",
            business_name=business_name,
            quote_title=quote.title,
            quote_total=f"£{quote.total}",
            view_url=view_url,
        )
        try:
            await send_email(
                to_email=contact.email,
                subject=subject,
                html_body=html,
                text_body=text,
                from_name=business_name,
                reply_to=(tenant_row.email if tenant_row is not None and tenant_row.email else None),
            )
        except Exception as exc:
            logger.warning(
                "quote_sent_email_failed",
                quote_id=str(quote.id),
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/reject")
async def reject_quote(
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Mark a quote as rejected."""
    quote = await _get_quote(db, tenant.id, quote_id)
    quote.status = "rejected"
    quote.approved_at = None
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_REJECTED,
        entity_type="quote",
        entity_id=quote.id,
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/approve")
async def approve_quote(
    quote_id: UUID,
    data: QuoteApprove,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Approve or reject a quote."""
    quote = await _get_quote(db, tenant.id, quote_id)
    if data.approved:
        quote.status = "approved"
        quote.approved_at = datetime.utcnow()
        action = Actions.QUOTE_APPROVED
    else:
        quote.status = "rejected"
        quote.approved_at = None
        action = Actions.QUOTE_REJECTED
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=action,
        entity_type="quote",
        entity_id=quote.id,
        payload={"approved": data.approved},
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/refine")
@limiter.limit("10/minute", key_func=tenant_key)
async def refine_quote(
    request: Request,
    quote_id: UUID,
    data: QuoteRefineRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Regenerate the AI-drafted line items from the electrician's instructions.

    Only lines flagged ``ai_generated`` are replaced; line items the
    electrician added or edited manually are preserved. Rate limited like
    ``/generate`` because it makes the same expensive LLM calls.
    """
    quote = await _get_quote(db, tenant.id, quote_id)

    ai_items = [li for li in quote.line_items if li.ai_generated]
    manual_items = [li for li in quote.line_items if not li.ai_generated]

    current_ai_lines = "\n".join(
        f"- {li.description} | quantity {li.quantity} | unit price £{li.unit_price}"
        for li in ai_items
    )
    description = (
        f"Quote: {quote.title}\n"
        f"{quote.description or ''}\n\n"
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
        f"Electrician's refinement instructions (apply these to the line items):\n"
        f"{data.instructions}"
    )

    started = time.perf_counter()
    try:
        retrieved, retrieval_status = await search_cost_items_with_status(
            f"{quote.title} {data.instructions}"
        )
        generated = await generate_quote_from_prompt(
            job_description=description,
            cost_items=retrieved,
            tenant_settings=tenant.settings,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    validated = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings=tenant.settings,
    )
    if not validated["line_items"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI did not return any line items for this refinement. Please try again.",
        )

    # Dedupe safety: even with prompt guidance the model sometimes re-emits a
    # preserved manual line — drop exact duplicates (same description + price).
    manual_keys = {(li.description.strip().lower(), str(li.unit_price)) for li in manual_items}
    kept_lines = []
    for line in validated["line_items"]:
        key = (str(line["description"]).strip().lower(), str(line["unit_price"]))
        if key in manual_keys:
            validated["warnings"].append(
                f"Dropped duplicate of manual line '{line['description']}' from the AI regeneration"
            )
            continue
        kept_lines.append(line)

    # Replace only the AI-generated lines; manual lines keep their positions.
    for item in list(quote.line_items):
        if item.ai_generated:
            await db.delete(item)
    quote.line_items = manual_items
    for line in kept_lines:
        quote.line_items.append(
            QuoteLineItem(
                tenant_id=tenant.id,
                description=line["description"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                ai_generated=True,
            )
        )
    calculate_quote_totals(quote)

    # Capture the previous rag metadata before it is replaced so the AI spend
    # accumulates across the whole generate → refine → re-quote flow.
    previous_rag = (quote.extra_data or {}).get("rag")
    quote.extra_data = {
        **(quote.extra_data or {}),
        "rag": {
            "confidence": validated["confidence"],
            "warnings": validated["warnings"],
            "assumptions": validated.get("assumptions", []),
            "notes": validated["notes"],
            "retrieval_status": retrieval_status,
            "generation_seconds": round(time.perf_counter() - started, 2),
        },
    }
    llm_usage = _accumulate_llm_usage(
        previous_rag if isinstance(previous_rag, dict) else {},
        generated.get("usage"),
    )
    if llm_usage is not None:
        quote.extra_data["rag"]["llm_usage"] = llm_usage
    _snapshot_ai_draft(quote)

    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_UPDATED,
        entity_type="quote",
        entity_id=quote.id,
        payload={
            "refined": True,
            "instructions_chars": len(data.instructions),
            "retrieval_status": retrieval_status,
            "confidence": validated["confidence"],
            "total": str(quote.total),
        },
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """Delete a quote."""
    quote = await _get_quote(db, tenant.id, quote_id)
    snapshot = {"title": quote.title, "status": quote.status, "total": str(quote.total)}
    await db.delete(quote)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_DELETED,
        entity_type="quote",
        entity_id=quote_id,
        payload=snapshot,
    )
    await db.commit()


def _snapshot_ai_draft(quote: Quote) -> None:
    """Snapshot the AI draft into extra_data so later edits can be measured."""
    quote.extra_data = {
        **(quote.extra_data or {}),
        "ai_draft": {
            "line_items": [
                {
                    "description": item.description,
                    "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price),
                }
                for item in quote.line_items
            ],
            "total": str(quote.total),
        },
    }


def _refresh_ai_feedback(quote: Quote) -> None:
    """Compare the current quote against its AI draft snapshot.

    Stored in ``extra_data["ai_feedback"]`` so analytics can measure how often
    electricians edit AI drafts and how far the price drifts. Recomputed on
    every update/send so it always reflects the latest state.
    """
    draft = (quote.extra_data or {}).get("ai_draft")
    if not isinstance(draft, dict):
        return
    draft_lines = draft.get("line_items") or []
    draft_total = Decimal(str(draft.get("total", "0") or "0"))

    line_count_delta = len(quote.line_items) - len(draft_lines)
    price_drift_pct: float | None = None
    if draft_total:
        drift = (quote.total - draft_total) / draft_total * 100
        price_drift_pct = float(round(drift, 2))

    quote.extra_data = {
        **(quote.extra_data or {}),
        "ai_feedback": {
            "edited": line_count_delta != 0 or price_drift_pct not in (None, 0.0),
            "line_count_delta": line_count_delta,
            "price_drift_pct": price_drift_pct,
        },
    }


def _fallback_line_items(description: str) -> list[dict[str, Any]]:
    """Beta demo fallback: plausible guide-priced line items for common jobs.

    Used only when the LLM returns an empty quote so the Beta demo flows never
    hard-fail for the categories exercised in the app.
    """
    lower = description.lower()
    if "ev charger" in lower or "ev-charger" in lower or "electric vehicle" in lower:
        return [
            {
                "description": "EV charger supply and install (labour)",
                "quantity": Decimal("1"),
                "unit_price": Decimal("450.00"),
            },
            {
                "description": "6mm SWA cable and gland kit",
                "quantity": Decimal("10"),
                "unit_price": Decimal("4.50"),
            },
            {
                "description": "RCBO protection and minor materials",
                "quantity": Decimal("1"),
                "unit_price": Decimal("85.00"),
            },
            {
                "description": "Call-out fee",
                "quantity": Decimal("1"),
                "unit_price": Decimal("45.00"),
            },
        ]
    if "consumer unit" in lower or "fuse board" in lower or "fusebox" in lower:
        return [
            {
                "description": "Consumer unit replacement labour",
                "quantity": Decimal("1"),
                "unit_price": Decimal("520.00"),
            },
            {
                "description": "Metal 12-way RCBO consumer unit",
                "quantity": Decimal("1"),
                "unit_price": Decimal("180.00"),
            },
            {
                "description": "Labelling, testing and certification",
                "quantity": Decimal("1"),
                "unit_price": Decimal("95.00"),
            },
            {
                "description": "Call-out fee",
                "quantity": Decimal("1"),
                "unit_price": Decimal("45.00"),
            },
        ]
    if "eicr" in lower or "electrical inspection" in lower or "condition report" in lower:
        return [
            {
                "description": "EICR inspection and testing",
                "quantity": Decimal("1"),
                "unit_price": Decimal("225.00"),
            },
            {
                "description": "EICR certificate and documentation",
                "quantity": Decimal("1"),
                "unit_price": Decimal("35.00"),
            },
            {
                "description": "Call-out fee",
                "quantity": Decimal("1"),
                "unit_price": Decimal("45.00"),
            },
        ]
    if "socket" in lower or "additional points" in lower:
        return [
            {
                "description": "Install double socket (labour per point)",
                "quantity": Decimal("2"),
                "unit_price": Decimal("85.00"),
            },
            {
                "description": "Double socket faceplate and back box",
                "quantity": Decimal("2"),
                "unit_price": Decimal("18.50"),
            },
            {
                "description": "Cable and containment",
                "quantity": Decimal("1"),
                "unit_price": Decimal("45.00"),
            },
            {
                "description": "Call-out fee",
                "quantity": Decimal("1"),
                "unit_price": Decimal("45.00"),
            },
        ]
    if "fault" in lower or "emergency" in lower:
        return [
            {
                "description": "Fault finding and diagnostics (first hour)",
                "quantity": Decimal("1"),
                "unit_price": Decimal("120.00"),
            },
            {
                "description": "Subsequent labour (per hour)",
                "quantity": Decimal("1"),
                "unit_price": Decimal("75.00"),
            },
            {
                "description": "Call-out fee",
                "quantity": Decimal("1"),
                "unit_price": Decimal("65.00"),
            },
        ]
    # Generic fallback so a plausible electrical job never comes back empty.
    return [
        {
            "description": "Electrical labour (guide price)",
            "quantity": Decimal("1"),
            "unit_price": Decimal("250.00"),
        },
        {
            "description": "Materials and sundries",
            "quantity": Decimal("1"),
            "unit_price": Decimal("75.00"),
        },
        {"description": "Call-out fee", "quantity": Decimal("1"), "unit_price": Decimal("45.00")},
    ]


# Structured-intake keys that count as "consumer-unit / access information"
# for the intake-completeness signal (across questionnaire and ai_extracted).
_ACCESS_INFO_KEYS = (
    "consumer_unit_location",
    "consumer_unit",
    "fuse_box_location",
    "fuse_box",
    "access_notes",
    "access",
    "parking",
    "preferred_time",
    "hours_available",
)

# Keys that indicate the customer told us something specific about THIS job
# (as opposed to generic property facts). Extracting any of these is the
# biggest lever the AI chat has to push confidence up.
_JOB_SPECIFICITY_KEYS = (
    "location",
    "room",
    "rooms",
    "quantity",
    "count",
    "how_many",
    "existing_setup",
    "existing",
    "current_state",
    "symptoms",
    "problem",
    "issue",
    "when_started",
    "timeline",
    "preference",
    "wants",
    "wanted",
    "brand",
    "finish",
    "budget",
)

# Signal weights (must sum to 1.0). Weighted rather than 6-equal so a rich AI
# chat can push completeness above 0.7 even without a fully-filled form.
_INTAKE_WEIGHTS = {
    "description": 0.10,
    "property_type": 0.10,
    "bedrooms": 0.10,
    "access_info": 0.15,
    "urgency": 0.05,
    "triage_run": 0.10,
    "job_specificity": 0.25,  # AI chat's biggest lever
    "extraction_richness": 0.15,  # scales 0-1 by number of extracted facts
}


def _intake_completeness(
    description: str,
    quote_request: QuoteRequest | None = None,
    property_type: str | None = None,
    site_survey: dict[str, Any] | None = None,
) -> float:
    """Score how complete the customer's intake is, as a 0-1 fraction.

    Weighted signals (weights in :data:`_INTAKE_WEIGHTS`):
        - description length > 10 chars
        - property type (form OR ai_extracted)
        - bedroom count (form OR ai_extracted)
        - access / consumer-unit info (form OR ai_extracted, expanded key set)
        - urgency recorded
        - triage completed (any ai_extracted facts)
        - job-specificity (customer told us something specific about THIS job)
        - extraction-richness (0-1 by how many facts the AI chat extracted)

    The last two carry ~40% of the weight so a rich AI follow-up chat
    meaningfully pushes confidence up rather than just adding a single 1/6
    triage-completed bump. Feeds the Confidence 2.0 formula in
    :func:`app.rag.validation.validate_generated_quote`.
    """
    structured = (quote_request.structured_data if quote_request else None) or {}
    survey = site_survey or {}

    def _section(name: str) -> dict[str, Any]:
        value = structured.get(name)
        return value if isinstance(value, dict) else {}

    property_info = _section("property")
    questionnaire = _section("questionnaire")
    ai_extracted = _section("ai_extracted")

    known_property_type = (
        property_type
        or property_info.get("type")
        or ai_extracted.get("property_type")
        or survey.get("property_type")
    )
    bedrooms = (
        property_info.get("bedrooms") or ai_extracted.get("bedrooms") or survey.get("bedrooms")
    )
    access_info = any(
        questionnaire.get(key) or ai_extracted.get(key) for key in _ACCESS_INFO_KEYS
    )
    urgency = quote_request.urgency if quote_request is not None else None
    job_specificity = any(ai_extracted.get(key) for key in _JOB_SPECIFICITY_KEYS)
    # Count non-empty extracted facts, capped at 4. 4+ facts = full richness
    # credit; 2-3 = partial; 0-1 = none.
    extraction_count = sum(1 for value in ai_extracted.values() if value not in (None, "", [], {}))
    extraction_richness = min(extraction_count, 4) / 4

    signals: dict[str, float] = {
        "description": 1.0 if len(description.strip()) > 10 else 0.0,
        "property_type": 1.0 if known_property_type else 0.0,
        "bedrooms": 1.0 if bedrooms is not None else 0.0,
        "access_info": 1.0 if access_info else 0.0,
        "urgency": 1.0 if urgency else 0.0,
        "triage_run": 1.0 if ai_extracted else 0.0,
        "job_specificity": 1.0 if job_specificity else 0.0,
        "extraction_richness": extraction_richness,
    }
    total = sum(_INTAKE_WEIGHTS[key] * signals[key] for key in _INTAKE_WEIGHTS)
    return round(total, 2)


def _accumulate_llm_usage(
    existing_rag: dict[str, Any], usage: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Merge one LLM call's token usage into the rag ``llm_usage`` record.

    Multi-call flows (generate → refine → re-quote) sum prompt/completion
    tokens and the estimated cost so ``extra_data["rag"]["llm_usage"]``
    reflects the quote's total AI spend. Returns the existing record
    unchanged when the provider did not report usage, or ``None`` when no
    usage has ever been recorded.
    """
    existing = existing_rag.get("llm_usage")
    if usage is None:
        return existing if isinstance(existing, dict) else None
    model = settings.llm_model
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    cost = estimate_llm_cost_usd(model, prompt_tokens, completion_tokens)
    if isinstance(existing, dict):
        prompt_tokens += int(existing.get("prompt_tokens") or 0)
        completion_tokens += int(existing.get("completion_tokens") or 0)
        previous_cost = existing.get("est_cost_usd")
        if cost is not None or previous_cost is not None:
            cost = round(float(cost or 0.0) + float(previous_cost or 0.0), 6)
    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "est_cost_usd": cost,
    }


async def _generate_rag_quote(
    quote: Quote,
    data: QuoteGenerateRequest,
    tenant: TenantDep,
    quote_request: QuoteRequest | None = None,
) -> None:
    """Populate a quote using the faster RAG path (retrieval + LLM)."""
    started = time.perf_counter()
    retrieved, retrieval_status = await search_cost_items_with_status(data.description)
    generated = await generate_quote_from_prompt(
        job_description=data.description,
        cost_items=retrieved,
        tenant_settings=tenant.settings,
        property_type=data.property_type,
        site_survey=data.site_survey,
    )
    generation_seconds = round(time.perf_counter() - started, 2)
    completeness = _intake_completeness(
        data.description,
        quote_request,
        property_type=data.property_type,
        site_survey=data.site_survey,
    )
    validated = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings=tenant.settings,
        completeness=completeness,
    )
    build_quote_from_validation(quote, validated, retrieval_status=retrieval_status)
    if not quote.line_items:
        # Beta safety net: if the LLM returns no line items, seed the quote with
        # sensible defaults for the demo categories so the electrician can still
        # review, edit and send.
        for line in _fallback_line_items(data.description):
            quote.line_items.append(
                QuoteLineItem(
                    tenant_id=quote.tenant_id,
                    description=line["description"],
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    ai_generated=True,
                )
            )
        calculate_quote_totals(quote)

    quote.extra_data = {**(quote.extra_data or {})}
    quote.extra_data["rag"]["generation_seconds"] = generation_seconds
    quote.extra_data["rag"]["completeness"] = completeness
    llm_usage = _accumulate_llm_usage(quote.extra_data["rag"], generated.get("usage"))
    if llm_usage is not None:
        quote.extra_data["rag"]["llm_usage"] = llm_usage
    _snapshot_ai_draft(quote)


def _build_lead_description(quote_request: QuoteRequest) -> str:
    """Compose an LLM job description from a captured quote request."""
    sd = quote_request.structured_data or {}
    parts: list[str] = []
    category = sd.get("category") or sd.get("title")
    if category:
        parts.append(f"Job type: {category}.")
    if quote_request.raw_text:
        parts.append(str(quote_request.raw_text))

    def _summarise(label: str, obj: object) -> None:
        if isinstance(obj, dict):
            pairs = [f"{k}: {v}" for k, v in obj.items() if v not in (None, "", [], {})]
            if pairs:
                parts.append(f"{label}: " + ", ".join(pairs) + ".")

    _summarise("Property", sd.get("property"))
    _summarise("Details", sd.get("questionnaire"))
    # Facts the customer confirmed during AI triage chat.
    _summarise("Customer-confirmed details", sd.get("ai_extracted"))

    description = " ".join(parts).strip()
    return description or "Electrical work requested by a customer."


async def _fetch_quote_request_communications(
    db: AsyncSession, tenant_id: UUID, quote_request_id: UUID
) -> list[Communication]:
    """Load in-app chat messages linked to a quote request, oldest first."""
    await set_tenant_in_session(db, tenant_id)
    result = await db.execute(
        select(Communication)
        .where(
            Communication.tenant_id == tenant_id,
            Communication.quote_request_id == quote_request_id,
        )
        .order_by(Communication.created_at.asc())
    )
    return list(result.scalars().all())


async def _append_chat_context(
    db: AsyncSession,
    tenant_id: UUID,
    quote_request: QuoteRequest,
    description: str,
) -> str:
    """Append the lead's chat history (customer/AI/business) to the job
    description so clarifying answers supplied after the lead was submitted
    inform the generated quote."""
    communications = await _fetch_quote_request_communications(db, tenant_id, quote_request.id)
    chat_messages = [comm for comm in communications if comm.body]
    if not chat_messages:
        return description
    role_labels = {
        "customer": "Customer",
        "business": "Electrician",
        "ai": "Assistant",
    }
    chat_parts = ["\n\nAdditional context from customer chat:"]
    for comm in chat_messages:
        label = role_labels.get(comm.sender_role, "Assistant")
        chat_parts.append(f"{label}: {comm.body}")
    return description + "\n" + "\n".join(chat_parts)


async def _generate_quote_impl(
    data: QuoteGenerateRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Shared implementation for the quote-generation routes.

    Kept decorator-free: slowapi fires on internal calls too, so routes must
    wrap this rather than calling each other, or one request debits the
    tenant's rate-limit bucket twice.
    """
    await set_tenant_in_session(db, tenant.id)

    # Generating from a lead: pull the description and contact from the captured
    # quote request, and link the resulting quote back to it.
    quote_request: QuoteRequest | None = None
    lead_title: str | None = None
    if data.quote_request_id:
        quote_request = await db.scalar(
            select(QuoteRequest)
            .options(selectinload(QuoteRequest.contact))
            .where(QuoteRequest.id == data.quote_request_id)
        )
        if quote_request is None or quote_request.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quote request"
            )
        if not data.description.strip():
            data.description = _build_lead_description(quote_request)

        # The customer-facing title comes from the lead itself — before any
        # chat transcript is appended to the prompt context below.
        sd = quote_request.structured_data or {}
        lead_title = sd.get("title") or sd.get("category") or quote_request.raw_text or ""

        # Append any customer/AI/business chat history to the job description so
        # clarifying answers supplied after the lead was submitted inform the
        # generated quote.
        data.description = await _append_chat_context(
            db, tenant.id, quote_request, data.description
        )

    if quote_request is not None and quote_request.contact_id:
        contact = await db.get(Contact, quote_request.contact_id)
        if contact is None or contact.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")
    elif data.contact_id:
        contact = await db.get(Contact, data.contact_id)
        if contact is None or contact.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")
    else:
        contact = Contact(
            tenant_id=tenant.id,
            name=data.customer_name or "Generated lead",
            email=data.customer_email,
            phone=data.customer_phone,
        )
        db.add(contact)
        await db.flush()
        await db.refresh(contact)

    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title=str(lead_title or data.description)[:80].strip() or "AI-drafted quote",
        description=data.description,
    )

    try:
        await _generate_rag_quote(quote, data, tenant, quote_request)
        if not quote.line_items:
            raise RuntimeError(
                "The AI did not return any line items for this job. Please try "
                "again or build the quote manually."
            )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    db.add(quote)
    await db.flush()

    # Link the lead to the generated quote so the two-sided loop is traceable.
    if quote_request is not None:
        quote_request.quote_id = quote.id
        quote_request.status = "converted_to_quote"
        quote_request.converted_at = datetime.utcnow()
        quote.quote_request_id = quote_request.id

    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_GENERATED,
        entity_type="quote",
        entity_id=quote.id,
        payload={
            "backend": "rag",
            "description_chars": len(data.description or ""),
            "property_type": data.property_type,
            "quote_request_id": str(data.quote_request_id) if data.quote_request_id else None,
            "total": str(quote.total),
        },
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/generate", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute", key_func=tenant_key)
async def generate_quote(
    request: Request,
    data: QuoteGenerateRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Generate a draft quote from a natural-language job description.

    Rate limited to 10 generations per minute per tenant — LLM + OCERP calls
    are expensive and a runaway client can otherwise exhaust the budget.
    """
    return await _generate_quote_impl(data, tenant, current_user, db)


@router.post("/generate-async", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute", key_func=tenant_key)
async def generate_quote_async(
    request: Request,
    data: QuoteGenerateRequest,
    background_tasks: BackgroundTasks,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteGenerateAsyncResponse:
    """Accept a quote-generation request and run it in a background worker.

    Returns 202 immediately; the worker runs the same generation pipeline as
    ``POST /quotes/generate`` and notifies the tenant's staff (and the
    customer, when the lead is linked to a customer account) of the outcome
    via persistent notifications. Same per-tenant rate limit as ``/generate``.
    """
    # Validate synchronously what can be validated cheaply so the client gets
    # an immediate 400 instead of a silent background failure.
    if data.quote_request_id is not None:
        await set_tenant_in_session(db, tenant.id)
        quote_request = await db.scalar(
            select(QuoteRequest).where(QuoteRequest.id == data.quote_request_id)
        )
        if quote_request is None or quote_request.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quote request"
            )

    # Imported lazily: app.quote_automation already imports this router, so a
    # module-level import would be circular.
    from app.quote_automation import generate_quote_async_worker

    background_tasks.add_task(generate_quote_async_worker, tenant.id, data)
    return QuoteGenerateAsyncResponse(status="generating", quote_request_id=data.quote_request_id)


@router.post("/generate-boq", status_code=status.HTTP_501_NOT_IMPLEMENTED)
@limiter.limit("10/minute", key_func=tenant_key)
async def generate_boq_quote(
    request: Request,
    data: QuoteGenerateRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """OCERP / BoQ generation is parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OCERP / BoQ generation is parked for the mobile-pivot MVP. Use /quotes/generate instead.",
    )


@router.get("/{quote_id}/boq")
async def get_quote_boq(quote_id: UUID, tenant: TenantDep, db: DbDep) -> None:
    """OCERP / BoQ endpoints are parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="BoQ endpoints are parked for the mobile-pivot MVP.",
    )


@router.patch("/{quote_id}/boq")
async def update_quote_boq(
    quote_id: UUID,
    data: QuoteUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """OCERP / BoQ endpoints are parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="BoQ endpoints are parked for the mobile-pivot MVP.",
    )


@router.post(
    "/{quote_id}/boq/regenerate",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
@limiter.limit("10/minute", key_func=tenant_key)
async def regenerate_quote_boq(
    request: Request,
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """OCERP / BoQ endpoints are parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="BoQ endpoints are parked for the mobile-pivot MVP.",
    )


@router.post(
    "/{quote_id}/convert-to-invoice",
    status_code=status.HTTP_201_CREATED,
)
async def convert_quote_to_invoice(
    quote_id: UUID,
    data: QuoteConvertToInvoice,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Convert a quote into a draft invoice."""
    quote = await _get_quote(db, tenant.id, quote_id)

    if quote.status in {"invoiced", "cancelled", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote cannot be converted to an invoice",
        )
    if not quote.line_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote has no line items",
        )

    invoice_number = data.invoice_number or await generate_invoice_number(db, tenant.id)
    due_date = data.due_date or (datetime.utcnow() + timedelta(days=14))

    invoice = build_invoice_from_quote(quote, invoice_number, due_date)
    quote.status = "invoiced"

    db.add(invoice)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_CONVERTED_TO_INVOICE,
        entity_type="quote",
        entity_id=quote.id,
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
        },
    )
    await db.commit()
    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.get("/{quote_id}/pdf")
async def quote_pdf(quote_id: UUID, tenant: TenantDep, db: DbDep) -> StreamingResponse:
    """Generate a PDF version of a quote.

    FPDF is synchronous I/O and blocks the event loop for tens to hundreds of
    milliseconds per quote — long enough to stall every other request on the
    same worker. We snapshot the ORM data into plain dicts first (no lazy
    loading from inside the thread) and then build the PDF in a worker
    thread via :func:`asyncio.to_thread`.
    """
    quote = await _get_quote(db, tenant.id, quote_id)
    snapshot = _quote_pdf_snapshot(quote, tenant.name)
    pdf_bytes = await asyncio.to_thread(_render_quote_pdf, snapshot)

    buffer = BytesIO(pdf_bytes)
    buffer.seek(0)
    filename = f"quote-{quote.id}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


def _quote_pdf_snapshot(quote: Quote, tenant_name: str) -> dict[str, Any]:
    """Pre-materialise everything the PDF renderer needs as plain primitives.

    Done on the asyncio thread (where the AsyncSession lives) so the
    threadpool job never accidentally triggers an ORM lazy-load — which
    would crash with a "greenlet_spawn has not been called" error.
    """
    snapshot_line_items = [
        {
            "description": li.description,
            "quantity": float(li.quantity),
            "unit_price": float(li.unit_price),
            "total": float(li.total),
        }
        for li in quote.line_items
    ]

    boq = quote.bill_of_quantities
    if boq and boq.customer_summary_lines:
        snapshot_line_items = [
            {
                "description": str(item.get("description", "")),
                "quantity": 1.0,
                "unit_price": float(item.get("total", 0) or 0),
                "total": float(item.get("total", 0) or 0),
            }
            for item in boq.customer_summary_lines
        ]

    return {
        "id": str(quote.id),
        "tenant_name": tenant_name,
        "title": quote.title,
        "status": quote.status,
        "created_at": quote.created_at,
        "subtotal": float(quote.subtotal),
        "vat_rate": float(quote.vat_rate),
        "vat_amount": float(quote.vat_amount),
        "total": float(quote.total),
        "contact": {
            "name": quote.contact.name,
            "email": quote.contact.email,
            "phone": quote.contact.phone,
        },
        "line_items": snapshot_line_items,
    }


def _render_quote_pdf(snapshot: dict[str, Any]) -> bytes:
    """Render a quote PDF from a pre-materialised snapshot.

    Pure-sync, no ORM, safe to call from a worker thread.
    """
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, snapshot["tenant_name"], ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, "Quote", ln=True)  # type: ignore[arg-type]
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Customer details
    contact = snapshot["contact"]
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Customer", ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, contact["name"], ln=True)  # type: ignore[arg-type]
    if contact["email"]:
        pdf.cell(0, 8, contact["email"], ln=True)  # type: ignore[arg-type]
    if contact["phone"]:
        pdf.cell(0, 8, contact["phone"], ln=True)  # type: ignore[arg-type]
    pdf.ln(5)

    # Quote summary
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, snapshot["title"], ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {snapshot['created_at'].strftime('%d/%m/%Y')}", ln=True)  # type: ignore[arg-type]
    pdf.cell(0, 6, f"Status: {snapshot['status'].upper()}", ln=True)  # type: ignore[arg-type]
    pdf.ln(5)

    # Line items table
    pdf.set_fill_color(245, 244, 240)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 8, "Item", 1, 0, "L", True)  # type: ignore[arg-type]
    pdf.cell(25, 8, "Qty", 1, 0, "C", True)  # type: ignore[arg-type]
    pdf.cell(30, 8, "Unit Price", 1, 0, "R", True)  # type: ignore[arg-type]
    pdf.cell(30, 8, "Total", 1, 1, "R", True)  # type: ignore[arg-type]

    pdf.set_font("Helvetica", "", 10)
    for item in snapshot["line_items"]:
        start_y = pdf.get_y()
        pdf.multi_cell(100, 8, item["description"], border=1, align="L")
        row_h = pdf.get_y() - start_y
        pdf.set_xy(110, start_y)
        pdf.cell(25, row_h, str(item["quantity"]), 1, 0, "C")  # type: ignore[arg-type]
        pdf.set_xy(135, start_y)
        pdf.cell(30, row_h, f"£{item['unit_price']:,.2f}", 1, 0, "R")  # type: ignore[arg-type]
        pdf.set_xy(165, start_y)
        pdf.cell(30, row_h, f"£{item['total']:,.2f}", 1, 1, "R")  # type: ignore[arg-type]

    pdf.ln(5)

    # Totals
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, f"Subtotal: £{snapshot['subtotal']:,.2f}", ln=True, align="R")  # type: ignore[arg-type]
    vat_label = f"VAT ({snapshot['vat_rate'] * 100:.0f}%): £{snapshot['vat_amount']:,.2f}"
    pdf.cell(0, 8, vat_label, ln=True, align="R")  # type: ignore[arg-type]
    pdf.cell(0, 8, f"Total: £{snapshot['total']:,.2f}", ln=True, align="R")  # type: ignore[arg-type]

    output = pdf.output(dest="S")  # type: ignore[call-overload]
    # fpdf2 returns bytearray; older fpdf returns str. Normalise to bytes.
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
