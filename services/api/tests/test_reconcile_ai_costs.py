"""Tests for scripts/reconcile_ai_costs.py (estimated vs invoiced spend)."""

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from app.models import AiCallEvent
from sqlalchemy.ext.asyncio import AsyncSession

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from reconcile_ai_costs import compute_reconciliation, variance_pct  # noqa: E402


def test_variance_pct_over_estimate() -> None:
    assert variance_pct(Decimal("110"), Decimal("100")) == Decimal("10.00")


def test_variance_pct_under_estimate() -> None:
    assert variance_pct(Decimal("90"), Decimal("100")) == Decimal("-10.00")


def test_variance_pct_zero_invoice_is_none() -> None:
    assert variance_pct(Decimal("5"), Decimal("0")) is None


@pytest.mark.asyncio
async def test_compute_reconciliation_sums_and_variance(db: AsyncSession) -> None:
    in_range = datetime(2026, 8, 15, 12, 0)
    db.add_all(
        [
            AiCallEvent(
                id=uuid4(),
                created_at=in_range,
                feature="quote_draft",
                status="success",
                attempt_no=1,
                est_cost_usd=Decimal("0.500000"),
                cost_gbp=Decimal("0.3950"),
                raw_payload={},
            ),
            AiCallEvent(
                id=uuid4(),
                created_at=in_range,
                feature="quote_refine",
                status="success",
                attempt_no=1,
                est_cost_usd=Decimal("0.250000"),
                cost_gbp=Decimal("0.1975"),
                raw_payload={},
            ),
            # Tokens but no price (model missing from the price list).
            AiCallEvent(
                id=uuid4(),
                created_at=in_range,
                feature="quote_draft",
                status="success",
                attempt_no=1,
                gen_ai_usage_input_tokens=100,
                raw_payload={},
            ),
            # Outcome rows carry no cost and must not count.
            AiCallEvent(
                id=uuid4(),
                created_at=in_range,
                feature="outcome",
                status="success",
                attempt_no=1,
                raw_payload={"outcome": "quote_sent"},
            ),
            # Outside the window.
            AiCallEvent(
                id=uuid4(),
                created_at=datetime(2026, 9, 5, 12, 0),
                feature="quote_draft",
                status="success",
                attempt_no=1,
                est_cost_usd=Decimal("9.990000"),
                raw_payload={},
            ),
        ]
    )
    await db.flush()

    summary = await compute_reconciliation(db, date(2026, 8, 1), date(2026, 9, 1), Decimal("1.00"))
    assert summary["events"] == 3
    assert summary["uncosted_events"] == 1
    assert summary["estimated_cost_usd"] == "0.750000"
    assert summary["estimated_cost_gbp"] == "0.5925"
    assert summary["invoice_usd"] == "1.00"
    assert summary["variance_pct"] == "-25.00"
