"""Tests for the nightly AI rollup fold, budget alerts, and anomaly alerts."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app import scheduler
from app.models import AiAlertState, AiCallEvent, AiRollupFeatureDay, AiRollupUserDay
from app.scheduler import (
    _check_anomaly_alerts,
    _check_budget_alerts,
    fold_events,
    run_rollup_for_day,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

DAY = date(2026, 9, 11)


def _event(**kwargs: object) -> AiCallEvent:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "created_at": datetime(2026, 9, 11, 10, 0),
        "feature": "quote_draft",
        "status": "success",
        "attempt_no": 1,
        "raw_payload": {},
    }
    defaults.update(kwargs)
    return AiCallEvent(**defaults)


def _capture_alerts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    async def fake_send_alert(subject: str, text: str) -> dict[str, bool]:
        sent.append((subject, text))
        return {"email": True}

    monkeypatch.setattr(scheduler, "send_alert", fake_send_alert)
    return sent


async def _user_day_row(db: AsyncSession, day: date, feature: str) -> AiRollupUserDay | None:
    row: AiRollupUserDay | None = await db.scalar(
        select(AiRollupUserDay).where(
            AiRollupUserDay.date == day, AiRollupUserDay.feature == feature
        )
    )
    return row


async def _feature_day_row(db: AsyncSession, day: date, feature: str) -> AiRollupFeatureDay | None:
    row: AiRollupFeatureDay | None = await db.scalar(
        select(AiRollupFeatureDay).where(
            AiRollupFeatureDay.date == day, AiRollupFeatureDay.feature == feature
        )
    )
    return row


@pytest.mark.asyncio
async def test_fold_math_matches_hand_computed_fixture(db: AsyncSession) -> None:
    tenant_id, user_id = uuid4(), uuid4()
    db.add_all(
        [
            _event(
                tenant_id=tenant_id,
                user_id=user_id,
                gen_ai_usage_input_tokens=100,
                gen_ai_usage_output_tokens=50,
                gen_ai_usage_cached_input_tokens=10,
                est_cost_usd=Decimal("0.001000"),
                cost_gbp=Decimal("0.0008"),
                latency_seconds=1.0,
            ),
            _event(
                tenant_id=tenant_id,
                user_id=user_id,
                status="error",
                gen_ai_usage_input_tokens=200,
                est_cost_usd=Decimal("0.002000"),
                cost_gbp=Decimal("0.0016"),
                latency_seconds=2.0,
            ),
            # Success with no cost/token fields: coalesces to zero everywhere.
            _event(tenant_id=tenant_id, user_id=user_id, latency_seconds=3.0),
            # Outcome rows fold into their own feature='outcome' group.
            _event(
                tenant_id=tenant_id,
                user_id=user_id,
                feature="outcome",
                raw_payload={"outcome": "quote_sent"},
            ),
            # Platform-only event: never in the per-user table.
            _event(feature="embedding", tenant_id=None, gen_ai_usage_input_tokens=500),
        ]
    )
    await db.flush()

    summary = await run_rollup_for_day(db, DAY)
    assert summary["locked"] == 0
    assert summary["user_day_rows"] == 2  # quote_draft + outcome
    assert summary["feature_day_rows"] == 3  # + embedding

    row = await _user_day_row(db, DAY, "quote_draft")
    assert row is not None
    assert row.tenant_id == tenant_id
    assert row.user_id == user_id
    assert row.generations == 2
    assert row.retries == 1
    assert row.tokens_input == 300
    assert row.tokens_output == 50
    assert row.tokens_cached == 10
    assert row.est_cost_usd == Decimal("0.003000")
    assert row.cost_gbp == Decimal("0.0024")
    # Nearest-rank percentiles over [1.0, 2.0, 3.0].
    assert row.latency_p50 == 2.0
    assert row.latency_p95 == 3.0
    assert row.avg_keep_rate is None  # ai_draft_feedback not in the test schema
    assert row.quotes_sent == 0

    outcome_row = await _user_day_row(db, DAY, "outcome")
    assert outcome_row is not None
    assert outcome_row.generations == 0
    assert outcome_row.quotes_sent == 1
    assert outcome_row.est_cost_usd == Decimal("0.000000")

    feature_row = await _feature_day_row(db, DAY, "quote_draft")
    assert feature_row is not None
    assert feature_row.generations == 2
    assert feature_row.est_cost_usd == Decimal("0.003000")
    assert feature_row.latency_p95 == 3.0

    embedding_row = await _feature_day_row(db, DAY, "embedding")
    assert embedding_row is not None
    assert embedding_row.tokens_input == 500


@pytest.mark.asyncio
async def test_refold_is_idempotent(db: AsyncSession) -> None:
    tenant_id = uuid4()
    db.add_all(
        [
            _event(tenant_id=tenant_id, est_cost_usd=Decimal("0.001000")),
            _event(tenant_id=tenant_id, status="timeout"),
        ]
    )
    await db.flush()

    first = await run_rollup_for_day(db, DAY)
    second = await run_rollup_for_day(db, DAY)
    assert first == second

    count = await db.scalar(
        select(func.count(AiRollupUserDay.id)).where(AiRollupUserDay.date == DAY)
    )
    assert count == 1
    row = await _user_day_row(db, DAY, "quote_draft")
    assert row is not None
    assert row.generations == 1
    assert row.retries == 1


def test_fold_events_excludes_tenant_null_rows() -> None:
    events = [
        _event(tenant_id=None, feature="demo_quote"),
        _event(tenant_id=uuid4(), feature="quote_draft"),
    ]
    groups = fold_events(events)
    assert len(groups) == 1
    assert next(iter(groups))[2] == "quote_draft"


@pytest.mark.asyncio
async def test_budget_thresholds_fire_once_per_month(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scheduler, "AI_MONTHLY_BUDGET_GBP", "100")
    sent = _capture_alerts(monkeypatch)
    # £85 of a £100 budget: the 50% and 80% thresholds are crossed, 100% is not.
    db.add(
        AiRollupFeatureDay(date=date(2026, 9, 10), feature="quote_draft", cost_gbp=Decimal("85.00"))
    )
    await db.flush()

    fired = await _check_budget_alerts(db, DAY)
    assert fired == ["budget_50", "budget_80"]
    assert len(sent) == 2

    again = await _check_budget_alerts(db, DAY)
    assert again == []
    assert len(sent) == 2

    states = (
        (await db.execute(select(AiAlertState).where(AiAlertState.period == "2026-09")))
        .scalars()
        .all()
    )
    assert {s.threshold for s in states} == {"budget_50", "budget_80"}


@pytest.mark.asyncio
async def test_budget_alerts_off_without_config(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scheduler, "AI_MONTHLY_BUDGET_GBP", "")
    db.add(
        AiRollupFeatureDay(
            date=date(2026, 9, 10), feature="quote_draft", cost_gbp=Decimal("999.00")
        )
    )
    await db.flush()
    assert await _check_budget_alerts(db, DAY) == []


@pytest.mark.asyncio
async def test_cost_spike_anomaly_fires_once(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_alerts(monkeypatch)
    for offset in range(1, 8):
        db.add(
            AiRollupFeatureDay(
                date=DAY - timedelta(days=offset),
                feature="quote_draft",
                cost_gbp=Decimal("10.00"),
            )
        )
    # £40 vs a £10 trailing mean: 4x > 3x threshold.
    db.add(AiRollupFeatureDay(date=DAY, feature="quote_draft", cost_gbp=Decimal("40.00")))
    await db.flush()

    fired = await _check_anomaly_alerts(db, DAY)
    assert fired == ["cost_spike"]
    assert len(sent) == 1

    assert await _check_anomaly_alerts(db, DAY) == []
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_cost_spike_needs_three_trailing_days(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_alerts(monkeypatch)
    for offset in (1, 2):
        db.add(
            AiRollupFeatureDay(
                date=DAY - timedelta(days=offset),
                feature="quote_draft",
                cost_gbp=Decimal("10.00"),
            )
        )
    db.add(AiRollupFeatureDay(date=DAY, feature="quote_draft", cost_gbp=Decimal("100.00")))
    await db.flush()
    assert await _check_anomaly_alerts(db, DAY) == []
    assert sent == []


@pytest.mark.asyncio
async def test_latency_p95_spike_anomaly(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture_alerts(monkeypatch)
    tenant_id = uuid4()
    for offset in range(1, 8):
        day = DAY - timedelta(days=offset)
        db.add(
            _event(
                tenant_id=tenant_id,
                created_at=datetime(day.year, day.month, day.day, 12, 0),
                latency_seconds=1.0,
            )
        )
    # p95 of 3.2s vs a 1.0s trailing mean: > 2x threshold.
    db.add(_event(tenant_id=tenant_id, latency_seconds=3.2))
    await db.flush()

    fired = await _check_anomaly_alerts(db, DAY)
    assert fired == ["latency_p95_spike"]
    assert len(sent) == 1
