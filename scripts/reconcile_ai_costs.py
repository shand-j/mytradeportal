#!/usr/bin/env python3
"""Reconcile estimated AI spend against the provider invoice for a period.

Sums ``est_cost_usd`` (and the GBP conversion actually stamped) over
``ai_call_events`` for a date range and compares the USD total against the
provider's invoiced figure, printing the variance so pricing drift, missing
models in the price list, or untracked calls are visible.

Usage (from the repo root, with the repo venv active):

    source .venv/bin/activate
    python scripts/reconcile_ai_costs.py --from 2026-08-01 --to 2026-09-01 --invoice-usd 412.37
    python scripts/reconcile_ai_costs.py --from 2026-08-01 --to 2026-09-01 \
        --invoice-usd 412.37 --json-out docs/reconciliation-2026-08.json

Variance is ``(estimated - invoice) / invoice * 100``: positive means we
over-estimated, negative means the provider billed more than we tracked.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
API_SRC = ROOT / "services" / "api"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from app.config import settings  # noqa: E402
from app.models import AiCallEvent  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def variance_pct(estimated_usd: Decimal, invoice_usd: Decimal) -> Decimal | None:
    """Signed variance of the estimate vs the invoice, in percent."""
    if invoice_usd == 0:
        return None
    return ((estimated_usd - invoice_usd) / invoice_usd * 100).quantize(Decimal("0.01"))


async def compute_reconciliation(
    db: AsyncSession, from_date: date, to_date: date, invoice_usd: Decimal
) -> dict[str, Any]:
    """Sum estimated spend over [from_date, to_date) and compare to the invoice.

    Outcome rows carry no cost fields and are excluded by the NULL-safe SUM;
    ``uncosted_events`` counts rows with tokens but no price (model missing
    from ``app.ai_pricing``) — a reconciliation-quality signal.
    """
    start = datetime(from_date.year, from_date.month, from_date.day)
    end = datetime(to_date.year, to_date.month, to_date.day)
    row = (
        await db.execute(
            select(
                func.count(AiCallEvent.id),
                func.coalesce(func.sum(AiCallEvent.est_cost_usd), 0),
                func.coalesce(func.sum(AiCallEvent.cost_gbp), 0),
                func.count(AiCallEvent.id).filter(
                    AiCallEvent.est_cost_usd.is_(None),
                    AiCallEvent.gen_ai_usage_input_tokens.isnot(None),
                ),
            ).where(
                AiCallEvent.created_at >= start,
                AiCallEvent.created_at < end,
                AiCallEvent.feature != "outcome",
            )
        )
    ).one()
    events, est_usd, est_gbp, uncosted = row
    estimated_usd = Decimal(str(est_usd))
    summary: dict[str, Any] = {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "events": int(events),
        "uncosted_events": int(uncosted or 0),
        "estimated_cost_usd": str(estimated_usd.quantize(Decimal("0.000001"))),
        "estimated_cost_gbp": str(Decimal(str(est_gbp)).quantize(Decimal("0.0001"))),
        "invoice_usd": str(invoice_usd),
        "variance_pct": str(v)
        if (v := variance_pct(estimated_usd, invoice_usd)) is not None
        else None,
    }
    return summary


def format_summary(summary: dict[str, Any]) -> str:
    variance = summary["variance_pct"]
    variance_text = f"{variance}%" if variance is not None else "n/a (invoice is 0)"
    return (
        f"AI cost reconciliation {summary['from']} → {summary['to']}\n"
        f"  events:            {summary['events']} "
        f"({summary['uncosted_events']} with tokens but no price)\n"
        f"  estimated spend:   ${summary['estimated_cost_usd']} "
        f"(£{summary['estimated_cost_gbp']})\n"
        f"  provider invoice:  ${summary['invoice_usd']}\n"
        f"  variance:          {variance_text}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="from_date", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="to_date", type=date.fromisoformat, required=True)
    parser.add_argument("--invoice-usd", dest="invoice_usd", type=Decimal, required=True)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            summary = await compute_reconciliation(
                session, args.from_date, args.to_date, args.invoice_usd
            )
    finally:
        await engine.dispose()
    print(format_summary(summary))
    if args.json_out is not None:
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"  summary written to {args.json_out}")


if __name__ == "__main__":
    asyncio.run(main())
