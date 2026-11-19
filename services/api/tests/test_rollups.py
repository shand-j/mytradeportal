"""Tests for the nightly AI rollup fold, budget alerts, and anomaly alerts."""

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app import scheduler
from app.models import (
    AiAlertState,
    AiCallEvent,
    AiRollupFeatureDay,
    AiRollupOrgDay,
    AiRollupUserDay,
)
from app.scheduler import (
    _check_anomaly_alerts,
    _check_budget_alerts,
    _check_fair_use_alerts,
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


async def _org_day_row(db: AsyncSession, day: date, tenant_id: UUID) -> AiRollupOrgDay | None:
    row: AiRollupOrgDay | None = await db.scalar(
        select(AiRollupOrgDay).where(
            AiRollupOrgDay.date == day, AiRollupOrgDay.tenant_id == tenant_id
        )
    )
    return row


@pytest.mark.asyncio
async def test_org_day_fold_two_tenants_across_days(db: AsyncSession) -> None:
    """The org fold lands one row per tenant per day with cost sums and
    p50/p95/p99 latency (p99 >= p95 >= p50, p99 pinned to the max sample)."""
    day2 = DAY + timedelta(days=1)
    tenant_a, tenant_b = uuid4(), uuid4()
    user_a1, user_a2, user_b1 = uuid4(), uuid4(), uuid4()

    # Day 1: tenant A spends across two users (tenant B has no day-1 events).
    a_latencies = [0.5, 1.0, 1.5, 2.0, 4.0, 8.0, 16.0]
    for index, latency in enumerate(a_latencies):
        db.add(
            _event(
                tenant_id=tenant_a,
                user_id=user_a1 if index % 2 == 0 else user_a2,
                gen_ai_usage_input_tokens=100,
                gen_ai_usage_output_tokens=40,
                gen_ai_usage_cached_input_tokens=5,
                est_cost_usd=Decimal("0.002000"),
                cost_gbp=Decimal("0.0016"),
                latency_seconds=latency,
            )
        )
    # One retry and one outcome event fold into tenant A's day too.
    db.add(_event(tenant_id=tenant_a, user_id=user_a1, status="error"))
    db.add(
        _event(
            tenant_id=tenant_a,
            user_id=user_a1,
            feature="outcome",
            raw_payload={"outcome": "quote_sent"},
        )
    )
    # Platform-only event: never attributed to an org.
    db.add(_event(tenant_id=None, latency_seconds=9.9))
    # Day 2 (folded separately): tenant A one event, tenant B three events.
    db.add(
        _event(
            tenant_id=tenant_a,
            user_id=user_a1,
            created_at=datetime(day2.year, day2.month, day2.day, 9, 0),
            est_cost_usd=Decimal("0.001000"),
            cost_gbp=Decimal("0.0008"),
            latency_seconds=3.0,
        )
    )
    for latency in (1.0, 2.0, 9.0):
        db.add(
            _event(
                tenant_id=tenant_b,
                user_id=user_b1,
                created_at=datetime(day2.year, day2.month, day2.day, 11, 0),
                est_cost_usd=Decimal("0.003000"),
                cost_gbp=Decimal("0.0024"),
                latency_seconds=latency,
            )
        )
    await db.flush()

    summary1 = await run_rollup_for_day(db, DAY)
    assert summary1["org_day_rows"] == 1  # tenant A only, tenant B has no day-1 events
    summary2 = await run_rollup_for_day(db, day2)
    assert summary2["org_day_rows"] == 2

    # --- Day 1, tenant A: sums over 7 generations + 1 retry + 1 outcome. ---
    row_a1 = await _org_day_row(db, DAY, tenant_a)
    assert row_a1 is not None
    assert row_a1.users_active == 2  # two distinct users with spend events
    assert row_a1.generations == 7
    assert row_a1.retries == 1
    assert row_a1.tokens_input == 700
    assert row_a1.tokens_output == 280
    assert row_a1.tokens_cached == 35
    assert row_a1.est_cost_usd == Decimal("0.014000")
    assert row_a1.cost_gbp == Decimal("0.0112")
    assert row_a1.quotes_sent == 1
    assert row_a1.avg_keep_rate is None  # ai_draft_feedback not in the test schema
    # Nearest-rank over [0.5..16.0] (n=7): p50 → 2.0, p95 → 16.0, p99 → 16.0.
    assert row_a1.latency_p50 == 2.0
    assert row_a1.latency_p95 == 16.0
    assert row_a1.latency_p99 == 16.0
    assert row_a1.latency_p99 >= row_a1.latency_p95 >= row_a1.latency_p50
    assert row_a1.latency_p99 == max(a_latencies)

    # Day 1 has no tenant-B row: no events to attribute.
    assert await _org_day_row(db, DAY, tenant_b) is None

    # --- Day 2 rows fold independently per tenant. ---
    row_a2 = await _org_day_row(db, day2, tenant_a)
    assert row_a2 is not None
    assert row_a2.users_active == 1
    assert row_a2.cost_gbp == Decimal("0.0008")
    assert row_a2.latency_p50 == 3.0
    assert row_a2.latency_p99 == 3.0

    row_b2 = await _org_day_row(db, day2, tenant_b)
    assert row_b2 is not None
    assert row_b2.users_active == 1
    assert row_b2.generations == 3
    assert row_b2.est_cost_usd == Decimal("0.009000")
    assert row_b2.cost_gbp == Decimal("0.0072")
    # Nearest-rank over [1.0, 2.0, 9.0]: p50 → 2.0, p95 → 9.0, p99 → 9.0.
    assert row_b2.latency_p50 == 2.0
    assert row_b2.latency_p95 == 9.0
    assert row_b2.latency_p99 == 9.0
    assert row_b2.latency_p99 >= row_b2.latency_p95 >= row_b2.latency_p50

    # Re-folding a day converges: same summary, same re-fetched measures.
    assert (await run_rollup_for_day(db, DAY)) == summary1
    refolded = await _org_day_row(db, DAY, tenant_a)
    assert refolded is not None
    assert refolded.generations == row_a1.generations
    assert refolded.cost_gbp == row_a1.cost_gbp
    assert refolded.latency_p99 == row_a1.latency_p99
    assert refolded.users_active == row_a1.users_active


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


@pytest.mark.asyncio
async def test_fair_use_alert_fires_once_per_org_per_month(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scheduler, "AI_FAIR_USE_MONTHLY_THRESHOLD", 3)
    sent = _capture_alerts(monkeypatch)
    tenant_id, other_tenant = uuid4(), uuid4()
    for _ in range(3):
        db.add(_event(tenant_id=tenant_id))
    # Outcome rows carry no AI spend and must not count toward fair use.
    db.add(
        _event(
            tenant_id=tenant_id,
            feature="outcome",
            raw_payload={"outcome": "quote_sent"},
        )
    )
    # A different tenant below the threshold stays quiet.
    db.add(_event(tenant_id=other_tenant))
    await db.flush()

    fired = await _check_fair_use_alerts(db, DAY)
    assert fired == [str(tenant_id)]
    assert len(sent) == 1
    assert str(tenant_id) in sent[0][1]

    # Same month: no second alert for the same org.
    assert await _check_fair_use_alerts(db, DAY) == []
    assert len(sent) == 1

    states = (
        (await db.execute(select(AiAlertState).where(AiAlertState.period == "2026-09")))
        .scalars()
        .all()
    )
    assert {s.threshold for s in states} == {f"fair_use:{tenant_id}"}


@pytest.mark.asyncio
async def test_fair_use_below_threshold_no_alert(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scheduler, "AI_FAIR_USE_MONTHLY_THRESHOLD", 5)
    sent = _capture_alerts(monkeypatch)
    db.add(_event(tenant_id=uuid4()))
    db.add(_event(tenant_id=uuid4()))
    await db.flush()
    assert await _check_fair_use_alerts(db, DAY) == []
    assert sent == []


@pytest.mark.asyncio
async def test_rollup_failure_alert_fires_once_per_day(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_alerts(monkeypatch)
    await scheduler._alert_rollup_failure(RuntimeError("fold exploded"), db=db)
    await scheduler._alert_rollup_failure(RuntimeError("fold exploded"), db=db)
    assert len(sent) == 1
    subject, body = sent[0]
    assert "rollup" in subject.lower()
    assert "RuntimeError" in body

    today = datetime.utcnow().date().isoformat()
    state = await db.scalar(
        select(AiAlertState).where(
            AiAlertState.period == today, AiAlertState.threshold == "rollup_failed"
        )
    )
    assert state is not None


@pytest.mark.asyncio
async def test_rollup_loop_alerts_and_keeps_ticking_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unhandled tick exception alerts (via the helper) and the loop
    continues on schedule instead of dying."""
    alerts: list[Exception] = []

    async def recording_alert(exc: Exception, db: AsyncSession | None = None) -> None:
        alerts.append(exc)

    monkeypatch.setattr(scheduler, "_alert_rollup_failure", recording_alert)
    monkeypatch.setattr(scheduler, "ROLLUP_TICK_SECONDS", 0.05)
    monkeypatch.setattr(scheduler, "ROLLUP_RUN_HOUR_UTC", 0)
    monkeypatch.setattr(scheduler, "ROLLUP_RUN_MINUTE_UTC", 0)

    ticks = 0

    async def failing_tick() -> None:
        nonlocal ticks
        ticks += 1
        raise RuntimeError("fold exploded")

    monkeypatch.setattr(scheduler, "run_rollup_tick", failing_tick)

    stop = asyncio.Event()
    task = asyncio.create_task(scheduler.rollup_loop(stop))
    try:
        for _ in range(100):
            if ticks >= 2:
                break
            await asyncio.sleep(0.05)
        assert ticks >= 2, "loop stopped ticking after the first failure"
        assert alerts, "loop failure never triggered the alert"
        assert all(isinstance(exc, RuntimeError) for exc in alerts)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)
