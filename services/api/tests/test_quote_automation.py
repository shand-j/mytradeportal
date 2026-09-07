"""Tests for background quote automation (app/quote_automation.py).

Covers the two scheduled workers:

* auto-draft — a public quote-request submission kicks off AI quote generation
  in the background; the 201 ack never waits on the LLM.
* re-quote — when the triage chat closes, the linked draft quote's AI line
  items are regenerated from the enriched request data, unless the electrician
  has touched the quote.

The workers open their own session via ``app.quote_automation.get_db_session``;
tests patch it to the per-test session so the workers see rows still inside
the test transaction.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app.models import Communication, Contact, Quote, QuoteLineItem, QuoteRequest
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _fix_max_followup_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the triage turn cap to the value ``_seed_triage_at_turn_cap`` targets."""
    from app.routers import communications as comms_router

    monkeypatch.setattr(comms_router.settings, "max_followup_turns", 3)


pytestmark = pytest.mark.asyncio

RETRIEVED = [
    {
        "code": "ELEC-CU-UPGRADE",
        "description": "Upgrade consumer unit",
        "unit": "each",
        "unit_price": "480.00",
        "category": "Consumer Units",
    }
]


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


def _worker_session(db: AsyncSession) -> Any:
    """Patch the background workers' session factory to the test session."""

    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    return patch("app.quote_automation.get_db_session", _session)


def _llm_patches(generated: dict[str, Any]) -> tuple[Any, Any]:
    return (
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=(RETRIEVED, "grounded")),
        ),
        patch(
            "app.routers.quotes.generate_quote_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
    )


async def test_public_submission_auto_drafts_quote(client: AsyncClient, db: AsyncSession) -> None:
    """A public submission returns 201 immediately and a linked AI draft quote
    appears in the background, identical in shape to /quotes/generate output."""
    tenant = await _create_tenant(client, f"auto-{uuid4().hex[:8]}")
    generated = {"line_items": [{"code": "ELEC-CU-UPGRADE", "quantity": 1}], "notes": ""}

    retrieval_patch, generation_patch = _llm_patches(generated)
    with _worker_session(db), retrieval_patch, generation_patch:
        response = await client.post(
            f"/businesses/{tenant['slug']}/quote-requests",
            json={
                "contact": {
                    "name": "Auto Homeowner",
                    "email": "auto@example.com",
                    "postcode": "M1 1AA",
                },
                "category": "consumer_unit",
                "title": "Consumer unit upgrade",
                "raw_text": "Old fuse board keeps tripping",
            },
        )

    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]

    lead = await client.get(f"/quote-requests/{lead_id}", headers={"X-Tenant-ID": tenant["id"]})
    assert lead.status_code == 200, lead.text
    lead_body = lead.json()
    assert lead_body["status"] == "converted_to_quote"
    assert lead_body["quote_id"] is not None

    quote = lead_body["quote"]
    assert quote is not None
    assert quote["status"] == "draft"
    assert quote["quote_request_id"] == lead_id
    # Title comes from the lead; AI flags and rag metadata match /quotes/generate.
    assert quote["title"] == "Consumer unit upgrade"
    assert quote["ai_generated"] is True
    assert quote["retrieval_status"] == "grounded"
    assert len(quote["line_items"]) == 1
    assert quote["line_items"][0]["ai_generated"] is True
    assert quote["total"] == "576.00"


async def test_public_submission_auto_draft_failure_still_acks(
    client: AsyncClient, db: AsyncSession
) -> None:
    """An LLM failure in the background worker is logged and swallowed — the
    submission ack is unaffected and no quote is linked."""
    tenant = await _create_tenant(client, f"auto-{uuid4().hex[:8]}")

    with (
        _worker_session(db),
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(side_effect=RuntimeError("LLM API key is not configured")),
        ),
    ):
        response = await client.post(
            f"/businesses/{tenant['slug']}/quote-requests",
            json={"contact": {"name": "Auto Homeowner"}, "category": "ev_charger"},
        )

    assert response.status_code == 201, response.text
    lead = await client.get(
        f"/quote-requests/{response.json()['id']}", headers={"X-Tenant-ID": tenant["id"]}
    )
    lead_body = lead.json()
    assert lead_body["status"] == "pending"
    assert lead_body["quote_id"] is None


async def _create_lead_with_quote(
    db: AsyncSession, tenant_id: UUID, *, all_ai: bool = True, status: str = "draft"
) -> tuple[QuoteRequest, Quote]:
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Lead Owner", email="lead.owner@example.com")
    db.add(contact)
    await db.flush()
    quote_request = QuoteRequest(
        tenant_id=tenant_id,
        contact_id=contact.id,
        source="app",
        raw_text="Fuse board keeps tripping",
        structured_data={"category": "consumer_unit", "title": "Fuse board replacement"},
    )
    db.add(quote_request)
    await db.flush()
    quote = Quote(
        tenant_id=tenant_id,
        contact_id=contact.id,
        title="Fuse board replacement",
        status=status,
        quote_request_id=quote_request.id,
    )
    quote.line_items = [
        QuoteLineItem(
            tenant_id=tenant_id,
            description="AI labour",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            ai_generated=True,
        ),
        QuoteLineItem(
            tenant_id=tenant_id,
            description="Second line",
            quantity=Decimal("1"),
            unit_price=Decimal("50.00"),
            ai_generated=all_ai,
        ),
    ]
    db.add(quote)
    await db.flush()
    quote_request.quote_id = quote.id
    await db.flush()
    return quote_request, quote


def _seed_triage_at_turn_cap(
    db: AsyncSession, tenant_id: UUID, quote_request: QuoteRequest
) -> None:
    base = datetime.utcnow() - timedelta(minutes=10)
    for index in range(3):
        db.add(
            Communication(
                tenant_id=tenant_id,
                contact_id=quote_request.contact_id,
                quote_request_id=quote_request.id,
                channel="in_app_chat",
                direction="outbound",
                sender_role="ai",
                body=f"Question {index}",
                ai_metadata={"complete": False, "confidence": 30},
                created_at=base + timedelta(minutes=index * 2),
            )
        )
    db.add(
        Communication(
            tenant_id=tenant_id,
            contact_id=quote_request.contact_id,
            quote_request_id=quote_request.id,
            channel="in_app_chat",
            direction="inbound",
            sender_role="customer",
            body="It's a 1960s semi, fuse box under the stairs",
            created_at=base + timedelta(minutes=7),
        )
    )


async def _close_triage(
    admin_client: AsyncClient,
    db: AsyncSession,
    quote_request: QuoteRequest,
    generated: dict[str, Any],
) -> tuple[Any, Any]:
    """Drive ai-followup to a turn-cap closure and let the re-quote worker run.

    Returns the HTTP response and the quote-generation mock so tests can assert
    whether regeneration happened and inspect the prompt it received.
    """
    followup_payload = {
        "confidence": 45,
        "complete": False,
        "message": "Anything else?",
        "extracted": {"consumer_unit_location": "under the stairs"},
        "suggested_questions": ["How old is the wiring?"],
    }
    generate_mock = AsyncMock(return_value=generated)
    with (
        _worker_session(db),
        patch(
            "app.routers.communications.generate_followup",
            new=AsyncMock(return_value=followup_payload),
        ),
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=(RETRIEVED, "grounded")),
        ),
        patch("app.routers.quotes.generate_quote_from_prompt", new=generate_mock),
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")
    return response, generate_mock


async def test_requote_regenerates_all_ai_draft_on_close(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """All-AI draft quote is regenerated in place when the triage closes."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request, quote = await _create_lead_with_quote(db, tenant_id)
    _seed_triage_at_turn_cap(db, tenant_id, quote_request)
    await db.flush()

    regenerated = {
        "line_items": [
            {
                "description": "Consumer unit replacement (labour)",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 320.00,
            }
        ],
        "notes": "Regenerated from triage answers",
    }
    response, generate_mock = await _close_triage(admin_client, db, quote_request, regenerated)

    assert response.status_code == 200, response.text
    assert response.json()["ai_metadata"]["requires_callback"] is True
    assert generate_mock.await_count == 1
    # The regeneration prompt includes the triage chat transcript.
    prompt_description = generate_mock.call_args.kwargs["job_description"]
    assert "fuse box under the stairs" in prompt_description
    assert "under the stairs" in prompt_description  # ai_extracted fact

    rows = (
        (await db.execute(select(QuoteLineItem).where(QuoteLineItem.quote_id == quote.id)))
        .scalars()
        .all()
    )
    assert [li.description for li in rows] == ["Consumer unit replacement (labour)"]
    assert all(li.ai_generated for li in rows)

    await db.refresh(quote)
    assert quote.subtotal == Decimal("320.00")
    rag = quote.extra_data["rag"]
    assert rag["retrieval_status"] == "grounded"
    assert rag["notes"] == "Regenerated from triage answers"
    assert quote.extra_data["ai_draft"]["line_items"][0]["description"] == (
        "Consumer unit replacement (labour)"
    )


async def test_requote_skipped_when_electrician_edited(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A draft the electrician touched (any non-AI line) is left alone."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request, quote = await _create_lead_with_quote(db, tenant_id, all_ai=False)
    _seed_triage_at_turn_cap(db, tenant_id, quote_request)
    await db.flush()

    regenerated = {"line_items": [{"code": "ELEC-CU-UPGRADE", "quantity": 1}], "notes": ""}
    response, generate_mock = await _close_triage(admin_client, db, quote_request, regenerated)

    assert response.status_code == 200, response.text
    assert generate_mock.await_count == 0

    rows = (
        (await db.execute(select(QuoteLineItem).where(QuoteLineItem.quote_id == quote.id)))
        .scalars()
        .all()
    )
    assert {li.description for li in rows} == {"AI labour", "Second line"}


async def test_requote_skipped_when_quote_no_longer_draft(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A quote that has left draft status is not regenerated."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request, quote = await _create_lead_with_quote(db, tenant_id, status="sent")
    _seed_triage_at_turn_cap(db, tenant_id, quote_request)
    await db.flush()

    regenerated = {"line_items": [{"code": "ELEC-CU-UPGRADE", "quantity": 1}], "notes": ""}
    response, generate_mock = await _close_triage(admin_client, db, quote_request, regenerated)

    assert response.status_code == 200, response.text
    assert generate_mock.await_count == 0

    rows = (
        (await db.execute(select(QuoteLineItem).where(QuoteLineItem.quote_id == quote.id)))
        .scalars()
        .all()
    )
    assert {li.description for li in rows} == {"AI labour", "Second line"}
