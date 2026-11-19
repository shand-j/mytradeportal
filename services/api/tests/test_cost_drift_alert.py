"""Tests for the monthly AI cost-drift alert (#60).

Automatic companion to the manual ``scripts/reconcile_ai_costs.py`` run: on
the month-boundary rollup tick the scheduler compares the just-closed month's
platform-estimated spend (summed from ``ai_rollup_feature_day``) against the
provider invoice in ``AI_MONTHLY_INVOICE_USD`` (converted at the stored
USD→GBP rate) and fires one alert per month when |variance| > 10%.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from app import scheduler
from app.models import AiAlertState, AiRollupFeatureDay, FxRate
from app.scheduler import _check_cost_drift_alerts
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_rollups import _capture_alerts

pytestmark = pytest.mark.asyncio

DAY = date(2026, 9, 30)  # last day of September 2026
FX_DATE = date(2026, 9, 30)
FX_RATE = Decimal("0.800000")  # $100 invoice = £80


async def _seed_month(db: AsyncSession, cost_gbp: str) -> None:
    db.add(AiRollupFeatureDay(date=DAY, feature="quote_draft", cost_gbp=Decimal(cost_gbp)))
    db.add(FxRate(rate_date=FX_DATE, usd_gbp=FX_RATE))
    await db.flush()


async def test_cost_drift_skipped_when_invoice_unset(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No AI_MONTHLY_INVOICE_USD: the check is skipped entirely, no alert."""
    monkeypatch.setattr(scheduler, "AI_MONTHLY_INVOICE_USD", "")
    sent = _capture_alerts(monkeypatch)
    await _seed_month(db, "92.0000")

    assert await _check_cost_drift_alerts(db, DAY) == []
    assert sent == []
    states = (await db.execute(select(AiAlertState))).scalars().all()
    assert states == []


async def test_cost_drift_within_threshold_stays_silent(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5% variance ($100 invoice vs £84 estimated at 0.80): no alert."""
    monkeypatch.setattr(scheduler, "AI_MONTHLY_INVOICE_USD", "100")
    sent = _capture_alerts(monkeypatch)
    await _seed_month(db, "84.0000")

    assert await _check_cost_drift_alerts(db, DAY) == []
    assert sent == []


async def test_cost_drift_over_threshold_fires_once_per_month(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """15% variance ($100 invoice vs £92 estimated at 0.80): exactly one
    alert; a second evaluation in the same month is deduped."""
    monkeypatch.setattr(scheduler, "AI_MONTHLY_INVOICE_USD", "100")
    sent = _capture_alerts(monkeypatch)
    await _seed_month(db, "92.0000")

    assert await _check_cost_drift_alerts(db, DAY) == ["cost_drift"]
    assert len(sent) == 1
    subject, body = sent[0]
    assert "AI cost drift" in subject
    assert "15.0%" in subject
    assert "£92.00" in body
    assert "$100" in body

    # Same-month repeat: deduped via ai_alert_state.
    assert await _check_cost_drift_alerts(db, DAY) == []
    assert len(sent) == 1

    states = (
        (await db.execute(select(AiAlertState).where(AiAlertState.period == "2026-09")))
        .scalars()
        .all()
    )
    assert [state.threshold for state in states] == ["cost_drift"]


async def test_rollup_tick_fires_drift_only_on_month_boundary(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drift check runs on the tick where the month has just rolled over
    (yesterday = month's last day) and not on a mid-month tick."""
    monkeypatch.setattr(scheduler, "AI_MONTHLY_INVOICE_USD", "100")
    sent = _capture_alerts(monkeypatch)
    await _seed_month(db, "92.0000")

    # 1 October 02:30 UTC → yesterday 30 September: month just closed.
    boundary_summary = await scheduler._run_rollup_tick(db, datetime(2026, 10, 1, 2, 30))
    assert boundary_summary["cost_drift_alerts"] == ["cost_drift"]
    assert len(sent) == 1

    # 16 September 02:30 UTC → yesterday 15 September: mid-month, no check.
    mid_month_summary = await scheduler._run_rollup_tick(db, datetime(2026, 9, 16, 2, 30))
    assert mid_month_summary.get("cost_drift_alerts", []) == []
    assert len(sent) == 1
