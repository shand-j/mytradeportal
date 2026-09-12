"""Tests for scripts/backfill_ai_events.py (idempotent historical event fold)."""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from app.ai_pricing import estimate_cost
from app.config import settings
from app.models import AiCallEvent, Contact, DemoQuoteEvent, Quote, Tenant
from app.rls import set_tenant_in_session
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import backfill_ai_events  # noqa: E402


async def _seed_quote(db: AsyncSession) -> Quote:
    tenant = Tenant(slug=f"backfill-{uuid4().hex[:8]}", name="Backfill Electrical")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Jane Homeowner", email="jane@example.com")
    db.add(contact)
    await db.flush()
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="Rewire kitchen",
        created_at=datetime(2026, 6, 15, 9, 30),
        extra_data={
            "rag": {
                "generation_seconds": 4.25,
                "llm_usage": {
                    "model": "openai/kimi-k2.6",
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                    "est_cost_usd": 0.999,  # stale flat-map figure; must be ignored
                },
            }
        },
    )
    db.add(quote)
    await db.commit()
    return quote


@pytest.mark.asyncio
async def test_backfill_inserts_recomputed_event(db: AsyncSession) -> None:
    quote = await _seed_quote(db)

    stats = await backfill_ai_events.backfill_quote_events(db)
    assert stats["inserted"] == 1
    assert stats["skipped_existing"] == 0

    event = await db.scalar(select(AiCallEvent).where(AiCallEvent.quote_id == quote.id))
    assert event is not None
    assert event.feature == "quote_draft"
    assert event.status == "success"
    assert event.tenant_id == quote.tenant_id
    assert event.created_at == quote.created_at
    assert event.latency_seconds == 4.25
    assert event.raw_payload["backfilled"] is True
    expected_usd = estimate_cost("openai/kimi-k2.6", 1000, 500, at_date=quote.created_at.date())
    assert expected_usd is not None
    assert event.est_cost_usd == expected_usd
    # fx_rates is empty in tests, so the fallback constant applies.
    fallback = Decimal(str(settings.fx_usd_gbp_fallback_rate))
    assert event.cost_gbp == (expected_usd * fallback).quantize(Decimal("0.0001"))


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db: AsyncSession) -> None:
    quote = await _seed_quote(db)

    first = await backfill_ai_events.backfill_quote_events(db)
    second = await backfill_ai_events.backfill_quote_events(db)
    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped_existing"] == 1

    events = (
        (await db.execute(select(AiCallEvent).where(AiCallEvent.quote_id == quote.id)))
        .scalars()
        .all()
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_backfill_skips_quotes_without_usage(db: AsyncSession) -> None:
    tenant = Tenant(slug=f"backfill-{uuid4().hex[:8]}", name="Backfill Electrical")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="No AI", email="noai@example.com")
    db.add(contact)
    await db.flush()
    db.add(Quote(tenant_id=tenant.id, contact_id=contact.id, title="Manual quote"))
    await db.commit()

    stats = await backfill_ai_events.backfill_quote_events(db)
    assert stats["inserted"] == 0
    assert stats["skipped_no_usage"] == 1


@pytest.mark.asyncio
async def test_demo_backfill_records_generation_seconds_only(db: AsyncSession) -> None:
    # Other suites leave demo_quote events + DemoQuoteEvent rows behind (shared
    # session DB) — clear both so the counts below are deterministic.
    await db.execute(delete(AiCallEvent).where(AiCallEvent.feature == "demo_quote"))
    await db.execute(delete(DemoQuoteEvent))
    await db.commit()

    demo = DemoQuoteEvent(ip_hash="a" * 64, generation_seconds=2.5)
    db.add(demo)
    await db.commit()

    first = await backfill_ai_events.backfill_demo_events(db)
    assert first["inserted"] == 1

    event = await db.scalar(select(AiCallEvent).where(AiCallEvent.feature == "demo_quote"))
    assert event is not None
    assert event.tenant_id is None
    assert event.latency_seconds == 2.5
    assert event.est_cost_usd is None
    assert event.cost_gbp is None
    assert event.raw_payload["demo_event_id"] == str(demo.id)

    second = await backfill_ai_events.backfill_demo_events(db)
    assert second["inserted"] == 0
    assert second["skipped_existing"] == 1
