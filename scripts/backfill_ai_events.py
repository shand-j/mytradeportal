#!/usr/bin/env python3
"""Backfill historical ``ai_call_events`` rows from pre-telemetry data.

The AI telemetry writer (``app.ai_telemetry``) only landed with Wave 1, so
quotes generated before then have no ``ai_call_events`` rows — but their
``quotes.extra_data["rag"]["llm_usage"]`` blobs still carry the accumulated
token usage + model. This script folds those blobs into synthetic historical
events so spend rollups and cost reconciliation cover the full history:

* One ``feature='quote_draft'`` event per quote that has a rag
  ``llm_usage`` record — ``status='success'``, ``created_at`` = the quote's
  ``created_at``, cost RECOMPUTED via ``app.ai_pricing.estimate_cost`` at the
  quote's date (the blob's own ``est_cost_usd`` is ignored: it was computed
  with the old flat price map) and GBP stamped via the FX rate in force on
  that date. ``raw_payload = {"backfilled": true, "source": "quote_rag_blob"}``.
* One ``feature='demo_quote'`` event per ``demo_quote_events`` row — tenant
  NULL, no cost data (the demo table never recorded tokens), only
  ``latency_seconds = generation_seconds``.

Idempotent: a quote/demo row that already has a backfilled event (matched on
``quote_id`` + ``raw_payload.backfilled`` / ``raw_payload.demo_event_id``) is
skipped, so re-running only picks up new historical data.

Usage (from the repo root, with the repo venv active):

    source .venv/bin/activate
    python scripts/backfill_ai_events.py [--dry-run] [--batch-size 200]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
API_SRC = ROOT / "services" / "api"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

import structlog  # noqa: E402
from app.ai_pricing import estimate_cost  # noqa: E402
from app.config import settings  # noqa: E402
from app.fx import get_usd_gbp_rate  # noqa: E402
from app.models import AiCallEvent, DemoQuoteEvent, Quote  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = structlog.get_logger("scripts.backfill_ai_events")

_GBP_QUANTUM = Decimal("0.0001")


def _rag_llm_usage(quote: Quote) -> dict[str, Any] | None:
    """Return the rag llm_usage blob when it has a usable model + tokens."""
    rag = (quote.extra_data or {}).get("rag")
    if not isinstance(rag, dict):
        return None
    usage = rag.get("llm_usage")
    if not isinstance(usage, dict):
        return None
    if not usage.get("model") or usage.get("prompt_tokens") is None:
        return None
    return usage


async def _has_backfilled_quote_event(db: AsyncSession, quote: Quote) -> bool:
    existing = await db.scalar(
        select(AiCallEvent.id)
        .where(
            AiCallEvent.quote_id == quote.id,
            AiCallEvent.raw_payload["backfilled"].as_boolean(),
        )
        .limit(1)
    )
    return existing is not None


async def backfill_quote_events(
    db: AsyncSession, *, dry_run: bool = False, batch_size: int = 200
) -> dict[str, int]:
    """Insert one backfilled quote_draft event per quote with a rag usage blob."""
    stats = {"scanned": 0, "inserted": 0, "skipped_existing": 0, "skipped_no_usage": 0}
    quotes = list((await db.execute(select(Quote))).scalars().all())
    pending = 0
    for quote in quotes:
        stats["scanned"] += 1
        usage = _rag_llm_usage(quote)
        if usage is None:
            stats["skipped_no_usage"] += 1
            continue
        if await _has_backfilled_quote_event(db, quote):
            stats["skipped_existing"] += 1
            continue
        if dry_run:
            stats["inserted"] += 1
            continue

        event_date = quote.created_at.date()
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        model = str(usage["model"])
        est_cost_usd = estimate_cost(model, prompt_tokens, completion_tokens, at_date=event_date)
        cost_gbp = None
        fx_rate = None
        fx_rate_date = None
        if est_cost_usd is not None:
            fx_rate, fx_rate_date = await get_usd_gbp_rate(db, at_date=event_date)
            cost_gbp = (est_cost_usd * fx_rate).quantize(_GBP_QUANTUM)

        generation_seconds = (quote.extra_data or {}).get("rag", {}).get("generation_seconds")
        db.add(
            AiCallEvent(
                id=uuid4(),
                created_at=quote.created_at,
                tenant_id=quote.tenant_id,
                feature="quote_draft",
                gen_ai_request_model=model,
                gen_ai_usage_input_tokens=prompt_tokens,
                gen_ai_usage_output_tokens=completion_tokens,
                est_cost_usd=est_cost_usd,
                cost_gbp=cost_gbp,
                fx_rate=fx_rate,
                fx_rate_date=fx_rate_date,
                latency_seconds=float(generation_seconds)
                if generation_seconds is not None
                else None,
                status="success",
                attempt_no=1,
                trace_id=(quote.ai_metadata or {}).get("trace_id"),
                quote_id=quote.id,
                quote_request_id=quote.quote_request_id,
                raw_payload={"backfilled": True, "source": "quote_rag_blob"},
            )
        )
        stats["inserted"] += 1
        pending += 1
        if pending >= batch_size:
            await db.commit()
            pending = 0
    if pending:
        await db.commit()
    return stats


async def backfill_demo_events(db: AsyncSession, *, dry_run: bool = False) -> dict[str, int]:
    """Insert one backfilled demo_quote event per demo_quote_events row."""
    stats = {"scanned": 0, "inserted": 0, "skipped_existing": 0}
    rows = list((await db.execute(select(DemoQuoteEvent))).scalars().all())
    for row in rows:
        stats["scanned"] += 1
        existing = await db.scalar(
            select(AiCallEvent.id)
            .where(
                AiCallEvent.feature == "demo_quote",
                AiCallEvent.raw_payload["demo_event_id"].as_string() == str(row.id),
            )
            .limit(1)
        )
        if existing is not None:
            stats["skipped_existing"] += 1
            continue
        if not dry_run:
            db.add(
                AiCallEvent(
                    id=uuid4(),
                    created_at=row.created_at,
                    tenant_id=None,
                    feature="demo_quote",
                    latency_seconds=row.generation_seconds,
                    status="success",
                    attempt_no=1,
                    raw_payload={
                        "backfilled": True,
                        "source": "demo_quote_events",
                        "demo_event_id": str(row.id),
                    },
                )
            )
        stats["inserted"] += 1
    if not dry_run:
        await db.commit()
    return stats


async def run(db: AsyncSession, *, dry_run: bool = False, batch_size: int = 200) -> dict[str, Any]:
    """Run both backfills against an open session (used by main() and tests)."""
    quote_stats = await backfill_quote_events(db, dry_run=dry_run, batch_size=batch_size)
    demo_stats = await backfill_demo_events(db, dry_run=dry_run)
    return {"quotes": quote_stats, "demo": demo_stats}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            stats = await run(session, dry_run=args.dry_run, batch_size=args.batch_size)
    finally:
        await engine.dispose()
    print(f"backfill_ai_events: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
