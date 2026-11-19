"""Hardening tests for the observability wave.

Covers, with every external system mocked (no live LLM, Langfuse, Slack, or
email):

* **Fail-open proof** — a logging backend that fails mid-request never breaks
  the caller: the tracked operation's result/exception propagates exactly as
  if telemetry did not exist, and no partial event rows survive.
* **Actor/channel propagation** — ``actor_type`` (staff/customer/system) and
  ``entry_channel`` round-trip through ``AiCallTracker``/``record_ai_event``
  and through the three wired call sites (communications intake chat,
  ``quote_automation``, the anonymous demo), plus Langfuse tag emission.
* **Alert boundaries** — budget (49.9/50, 79.9/80, 99.9/100%), cost anomaly
  (exactly 3x vs 3.01x trailing mean), latency anomaly (exactly 2x), and
  fair-use month rollover; each fires once per period.
* **Rollup resilience** — refolds converge to identical rows, advisory-lock
  contention is a clean no-op, and the rollup-failure alert dedupes even when
  the database itself is down (in-process fallback).
* **Data export** — cross-tenant isolation over a full multi-tenant fixture,
  recursive secret scanning, shape/serialisation stability, and the hourly
  rate limit.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app import ai_telemetry, scheduler
from app.ai_telemetry import (
    ACTOR_CUSTOMER,
    ACTOR_STAFF,
    ACTOR_SYSTEM,
    AiCallContext,
    AiCallTracker,
    record_ai_event,
)
from app.config import settings
from app.limiter import limiter
from app.models import (
    AiAlertState,
    AiCallEvent,
    AiRollupFeatureDay,
    AiRollupOrgDay,
    AiRollupUserDay,
    Contact,
    Customer,
    Invoice,
    QuoteRequest,
    Tenant,
)
from app.quote_automation import start_ai_triage
from app.rls import set_tenant_in_session
from app.scheduler import _check_anomaly_alerts, _check_budget_alerts, run_rollup_for_day
from app.security import create_access_token
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.test_data_export import _seed_tenant_records
from tests.test_rollups import _capture_alerts, _event

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

DAY = date(2026, 9, 11)


# ---------------------------------------------------------------------------
# 1. Fail-open proof
# ---------------------------------------------------------------------------


async def _exploding_flush(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("forced flush failure")


async def _count_events(db: AsyncSession, trace_id: str) -> int:
    count = await db.scalar(
        select(func.count(AiCallEvent.id)).where(AiCallEvent.trace_id == trace_id)
    )
    return int(count or 0)


async def test_record_ai_event_flush_failure_leaves_no_partial_row(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flush that explodes inside the telemetry SAVEPOINT returns None,
    leaves the caller's transaction fully usable, and drops the event
    entirely (no partial row)."""
    trace_id = f"fo-{uuid4().hex}"
    monkeypatch.setattr(db, "flush", _exploding_flush)
    result = await record_ai_event(db, feature="quote_draft", tenant_id=uuid4(), trace_id=trace_id)
    assert result is None
    monkeypatch.undo()

    # The business transaction is untouched by the telemetry failure.
    assert (await db.execute(text("SELECT 1"))).scalar() == 1
    assert await _count_events(db, trace_id) == 0
    # And a later, healthy write on the same session still lands.
    ok = await record_ai_event(
        db, feature="outcome", trace_id=trace_id, raw_payload={"outcome": "quote_sent"}
    )
    assert ok is not None
    assert await _count_events(db, trace_id) == 1


async def test_tracker_fail_open_business_result_unaffected(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the logging backend raising, the tracked block's result is
    returned exactly as if telemetry did not exist."""
    trace_id = f"fo-tracker-{uuid4().hex}"
    monkeypatch.setattr(db, "flush", _exploding_flush)
    ctx = AiCallContext(feature="quote_draft", db=db, tenant_id=uuid4(), trace_id=trace_id)
    async with AiCallTracker(ctx, model="gpt-4o-mini") as tracker:
        tracker.set_usage({"prompt_tokens": 10, "completion_tokens": 5})
        business_result = {"lines": 3}
    assert business_result == {"lines": 3}
    assert ctx.event_id is None
    monkeypatch.undo()

    assert (await db.execute(text("SELECT 1"))).scalar() == 1
    assert await _count_events(db, trace_id) == 0


async def test_tracker_fail_open_business_exception_propagates(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller sees ITS OWN exception (ValueError), never the telemetry
    failure — if fail-open were broken the RuntimeError would surface here."""
    trace_id = f"fo-exc-{uuid4().hex}"
    monkeypatch.setattr(db, "flush", _exploding_flush)
    ctx = AiCallContext(feature="quote_draft", db=db, tenant_id=uuid4(), trace_id=trace_id)
    with pytest.raises(ValueError, match="business boom"):
        async with AiCallTracker(ctx, model="gpt-4o-mini"):
            raise ValueError("business boom")
    assert ctx.event_id is None
    monkeypatch.undo()

    assert (await db.execute(text("SELECT 1"))).scalar() == 1
    assert await _count_events(db, trace_id) == 0


# ---------------------------------------------------------------------------
# 2. Actor/channel propagation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor_type", [ACTOR_STAFF, ACTOR_CUSTOMER, ACTOR_SYSTEM])
async def test_record_ai_event_actor_channel_round_trip(db: AsyncSession, actor_type: str) -> None:
    """All three actor types plus entry_channel persist on the row."""
    event_id = await record_ai_event(
        db,
        feature="quote_draft",
        tenant_id=uuid4(),
        actor_type=actor_type,
        entry_channel="qr_van",
    )
    assert event_id is not None
    event = await db.get(AiCallEvent, event_id)
    assert event is not None
    assert event.actor_type == actor_type
    assert event.entry_channel == "qr_van"


@pytest.mark.parametrize("actor_type", [ACTOR_STAFF, ACTOR_CUSTOMER, ACTOR_SYSTEM])
async def test_tracker_actor_channel_round_trip(db: AsyncSession, actor_type: str) -> None:
    """The tracker forwards actor_type/entry_channel from the context."""
    ctx = AiCallContext(
        feature="quote_draft",
        db=db,
        tenant_id=uuid4(),
        actor_type=actor_type,
        entry_channel="web_form",
        trace_id=f"actor-{uuid4().hex}",
    )
    async with AiCallTracker(ctx, model="gpt-4o-mini") as tracker:
        tracker.set_usage({"prompt_tokens": 5, "completion_tokens": 1})
    assert ctx.event_id is not None
    event = await db.get(AiCallEvent, ctx.event_id)
    assert event is not None
    assert event.actor_type == actor_type
    assert event.entry_channel == "web_form"


async def _make_lead_for_actor_tests(
    db: AsyncSession,
) -> tuple[Tenant, Customer, QuoteRequest]:
    """Tenant + contact + customer account + quote request linked to the customer."""
    tenant = Tenant(slug=f"actor-{uuid4().hex[:8]}", name="Actor Ltd")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Carol Customer", email="carol@example.com")
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email="carol@example.com",
        full_name="Carol Customer",
    )
    db.add(customer)
    quote_request = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        customer_id=customer.id,
        source="web_form",
        raw_text="Fuse board keeps tripping",
        structured_data={"category": "consumer_unit"},
    )
    db.add(quote_request)
    await db.flush()
    return tenant, customer, quote_request


def _capture_followup(captured: dict[str, Any]) -> AsyncMock:
    async def _fake_followup(
        description: str, prior_messages: list[dict[str, str]], **kwargs: Any
    ) -> dict[str, Any]:
        captured.update(kwargs)
        return {"confidence": 90, "complete": True, "message": "Thank you.", "extracted": {}}

    return AsyncMock(side_effect=_fake_followup)


async def test_intake_chat_customer_token_records_customer_actor(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Wired call site: the intake chat driven by a CUSTOMER token builds its
    telemetry context with actor_type=customer (and no entry channel)."""
    tenant, customer, quote_request = await _make_lead_for_actor_tests(db)
    captured: dict[str, Any] = {}
    token = create_access_token(
        user_id=customer.id,
        tenant_id=tenant.id,
        role="customer",
        email=customer.email,
        subject_type="customer",
    )
    with patch("app.routers.communications.generate_followup", new=_capture_followup(captured)):
        response = await client.post(
            f"/communications/{quote_request.id}/ai-followup",
            headers={"X-Tenant-ID": str(tenant.id), "Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200, response.text
    telemetry = captured["telemetry"]
    assert isinstance(telemetry, AiCallContext)
    assert telemetry.feature == "triage_followup"
    assert telemetry.actor_type == ACTOR_CUSTOMER
    assert telemetry.user_id is None  # customers are not staff users
    assert telemetry.entry_channel is None
    assert telemetry.tenant_id == tenant.id
    assert telemetry.quote_request_id == quote_request.id


async def test_intake_chat_staff_records_staff_actor(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Wired call site: staff opening the same chat keep the staff default,
    with their user id attached."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Lead Owner", email="lead@example.com")
    db.add(contact)
    await db.flush()
    quote_request = QuoteRequest(
        tenant_id=tenant_id,
        contact_id=contact.id,
        source="web_form",
        raw_text="Need my fuse board replaced",
        structured_data={"category": "consumer_unit"},
    )
    db.add(quote_request)
    await db.flush()

    captured: dict[str, Any] = {}
    with patch("app.routers.communications.generate_followup", new=_capture_followup(captured)):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")
    assert response.status_code == 200, response.text
    telemetry = captured["telemetry"]
    assert telemetry.actor_type == ACTOR_STAFF
    assert telemetry.user_id is not None
    assert telemetry.entry_channel is None


async def test_quote_automation_triage_uses_system_actor(db: AsyncSession) -> None:
    """Wired call site: the event-triggered triage opener in quote_automation
    tags its telemetry actor_type=system (no human initiated the call)."""
    tenant, _customer, quote_request = await _make_lead_for_actor_tests(db)
    captured: dict[str, Any] = {}
    with patch("app.rag.generate_followup", new=_capture_followup(captured)):
        await start_ai_triage(db, tenant, quote_request.id, quote_confidence=0.3)
    telemetry = captured["telemetry"]
    assert isinstance(telemetry, AiCallContext)
    assert telemetry.feature == "triage_followup"
    assert telemetry.actor_type == ACTOR_SYSTEM
    assert telemetry.tenant_id == tenant.id
    assert telemetry.quote_request_id == quote_request.id


# --- Langfuse emission -------------------------------------------------------


class _FakeLangfuse:
    """Captures trace()/generation() calls; can be told to explode."""

    def __init__(self, *, explode: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._explode = explode

    def trace(self, **kwargs: Any) -> _FakeLangfuse:
        if self._explode:
            raise RuntimeError("langfuse down")
        self.calls.append(("trace", kwargs))
        return self

    def generation(self, **kwargs: Any) -> None:
        self.calls.append(("generation", kwargs))


async def test_langfuse_noop_without_keys(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unconfigured Langfuse: _get_langfuse() returns None and the write is
    a silent no-op that still records the event."""
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(ai_telemetry, "_langfuse_client", None)
    monkeypatch.setattr(ai_telemetry, "_langfuse_unavailable", False)
    assert ai_telemetry._get_langfuse() is None

    event_id = await record_ai_event(
        db, feature="quote_draft", model="gpt-4o-mini", input_tokens=10, output_tokens=2
    )
    assert event_id is not None


async def test_langfuse_emission_carries_actor_channel_tags(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured client receives actor/channel tags and the prompt text
    (Langfuse only — the prompt never lands in the Postgres row)."""
    fake = _FakeLangfuse()
    monkeypatch.setattr(ai_telemetry, "_get_langfuse", lambda: fake)
    trace_id = f"lf-{uuid4().hex}"
    event_id = await record_ai_event(
        db,
        feature="triage_followup",
        tenant_id=uuid4(),
        actor_type=ACTOR_CUSTOMER,
        entry_channel="qr_van",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=20,
        trace_id=trace_id,
        prompt_version="triage_v1",
        prompt_text="SECRET PROMPT TEXT",
    )
    assert event_id is not None

    trace_calls = [kwargs for kind, kwargs in fake.calls if kind == "trace"]
    assert len(trace_calls) == 1
    assert trace_calls[0]["name"] == "triage_followup"
    assert trace_calls[0]["tags"] == ["actor_type:customer", "entry_channel:qr_van"]
    assert trace_calls[0]["metadata"]["trace_id"] == trace_id
    assert trace_calls[0]["metadata"]["prompt_version"] == "triage_v1"

    generation_calls = [kwargs for kind, kwargs in fake.calls if kind == "generation"]
    assert len(generation_calls) == 1
    assert generation_calls[0]["input"] == "SECRET PROMPT TEXT"
    assert generation_calls[0]["usage"] == {"input": 100, "output": 20}

    # Prompt text stays out of the durable row.
    event = await db.get(AiCallEvent, event_id)
    assert event is not None
    assert "SECRET" not in str(event.raw_payload)


async def test_langfuse_emission_omits_channel_tag_when_unset(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeLangfuse()
    monkeypatch.setattr(ai_telemetry, "_get_langfuse", lambda: fake)
    event_id = await record_ai_event(
        db, feature="quote_draft", model="gpt-4o-mini", input_tokens=1, output_tokens=1
    )
    assert event_id is not None
    trace_calls = [kwargs for kind, kwargs in fake.calls if kind == "trace"]
    assert trace_calls[0]["tags"] == ["actor_type:staff"]


async def test_langfuse_emit_failure_still_records(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Langfuse outage must never eat the event or raise into the caller."""
    fake = _FakeLangfuse(explode=True)
    monkeypatch.setattr(ai_telemetry, "_get_langfuse", lambda: fake)
    event_id = await record_ai_event(
        db, feature="quote_draft", model="gpt-4o-mini", input_tokens=1, output_tokens=1
    )
    assert event_id is not None
    assert await db.get(AiCallEvent, event_id) is not None


# ---------------------------------------------------------------------------
# 3. Fair-use alert: month rollover
# ---------------------------------------------------------------------------


async def test_fair_use_alert_refires_after_month_rollover(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dedupe is per (org, month): silent on repeat within a month, refires
    when the same org crosses the threshold again next month."""
    monkeypatch.setattr(scheduler, "AI_FAIR_USE_MONTHLY_THRESHOLD", 3)
    sent = _capture_alerts(monkeypatch)
    tenant_id = uuid4()
    for _ in range(3):
        db.add(_event(tenant_id=tenant_id, created_at=datetime(2026, 9, 10, 9, 0)))
    await db.flush()

    assert await scheduler._check_fair_use_alerts(db, date(2026, 9, 15)) == [str(tenant_id)]
    assert len(sent) == 1

    # Same month, more usage: still exactly one alert.
    db.add(_event(tenant_id=tenant_id, created_at=datetime(2026, 9, 16, 9, 0)))
    await db.flush()
    assert await scheduler._check_fair_use_alerts(db, date(2026, 9, 20)) == []
    assert len(sent) == 1

    # October: the same org crossing the threshold again refires under the
    # new period.
    for _ in range(3):
        db.add(_event(tenant_id=tenant_id, created_at=datetime(2026, 10, 2, 9, 0)))
    await db.flush()
    assert await scheduler._check_fair_use_alerts(db, date(2026, 10, 3)) == [str(tenant_id)]
    assert len(sent) == 2

    states = (
        (
            await db.execute(
                select(AiAlertState).where(AiAlertState.threshold == f"fair_use:{tenant_id}")
            )
        )
        .scalars()
        .all()
    )
    assert {state.period for state in states} == {"2026-09", "2026-10"}


# ---------------------------------------------------------------------------
# 4. Rollup resilience
# ---------------------------------------------------------------------------


async def _rollup_snapshot(
    db: AsyncSession, day: date
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    """Full-content snapshot of all three rollup tables for one day."""
    user_rows = (
        (await db.execute(select(AiRollupUserDay).where(AiRollupUserDay.date == day)))
        .scalars()
        .all()
    )
    feature_rows = (
        (await db.execute(select(AiRollupFeatureDay).where(AiRollupFeatureDay.date == day)))
        .scalars()
        .all()
    )
    org_rows = (
        (await db.execute(select(AiRollupOrgDay).where(AiRollupOrgDay.date == day))).scalars().all()
    )
    user_packed = sorted(
        (
            str(row.tenant_id),
            str(row.user_id),
            row.feature,
            row.generations,
            row.retries,
            row.tokens_input,
            row.tokens_output,
            row.tokens_cached,
            str(row.est_cost_usd),
            str(row.cost_gbp),
            row.latency_p50,
            row.latency_p95,
            row.quotes_sent,
        )
        for row in user_rows
    )
    feature_packed = sorted(
        (
            row.feature,
            row.generations,
            row.retries,
            row.tokens_input,
            row.tokens_output,
            row.tokens_cached,
            str(row.est_cost_usd),
            str(row.cost_gbp),
            row.latency_p50,
            row.latency_p95,
            row.quotes_sent,
        )
        for row in feature_rows
    )
    org_packed = sorted(
        (
            str(row.tenant_id),
            row.users_active,
            row.generations,
            row.retries,
            str(row.est_cost_usd),
            str(row.cost_gbp),
            row.latency_p50,
            row.latency_p95,
            row.latency_p99,
            row.quotes_sent,
        )
        for row in org_rows
    )
    return user_packed, feature_packed, org_packed


async def test_refold_converges_to_identical_rows(db: AsyncSession) -> None:
    """Re-running the same day's fold produces byte-identical rollup rows —
    no duplicates, no drift."""
    tenant_id, user_id = uuid4(), uuid4()
    db.add_all(
        [
            _event(
                tenant_id=tenant_id,
                user_id=user_id,
                gen_ai_usage_input_tokens=100,
                est_cost_usd=Decimal("0.001000"),
                cost_gbp=Decimal("0.0008"),
                latency_seconds=1.5,
            ),
            _event(tenant_id=tenant_id, user_id=user_id, status="error"),
            _event(
                tenant_id=tenant_id,
                feature="outcome",
                raw_payload={"outcome": "quote_sent"},
            ),
        ]
    )
    await db.flush()

    first_summary = await run_rollup_for_day(db, DAY)
    first_snapshot = await _rollup_snapshot(db, DAY)
    assert first_summary == {
        "user_day_rows": 2,
        "feature_day_rows": 2,
        "org_day_rows": 1,
        "locked": 0,
    }

    second_summary = await run_rollup_for_day(db, DAY)
    second_snapshot = await _rollup_snapshot(db, DAY)
    assert second_summary == first_summary
    assert second_snapshot == first_snapshot

    # A third fold with no new events still converges.
    third_summary = await run_rollup_for_day(db, DAY)
    third_snapshot = await _rollup_snapshot(db, DAY)
    assert third_summary == first_summary
    assert third_snapshot == first_snapshot


async def test_rollup_advisory_lock_contention_is_clean_noop(
    db: AsyncSession, test_database_url: str
) -> None:
    """While another replica holds the rollup lock the fold is a no-op that
    writes nothing and corrupts nothing; once released the fold runs."""
    db.add(_event(tenant_id=uuid4()))
    await db.flush()

    engine = create_async_engine(test_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as holder:
            await holder.begin()
            acquired = (
                await holder.execute(
                    text("SELECT pg_try_advisory_xact_lock(:namespace, hashtext(:key))"),
                    {"namespace": scheduler._ROLLUP_LOCK_NAMESPACE, "key": "ai_rollup"},
                )
            ).scalar()
            assert acquired is True  # the holder really owns the lock

            summary = await run_rollup_for_day(db, DAY)
            assert summary == {
                "user_day_rows": 0,
                "feature_day_rows": 0,
                "org_day_rows": 0,
                "locked": 1,
            }
            assert (
                await db.scalar(
                    select(func.count(AiRollupUserDay.id)).where(AiRollupUserDay.date == DAY)
                )
            ) == 0
            assert (
                await db.scalar(
                    select(func.count(AiRollupFeatureDay.id)).where(AiRollupFeatureDay.date == DAY)
                )
            ) == 0
            assert (
                await db.scalar(
                    select(func.count(AiRollupOrgDay.id)).where(AiRollupOrgDay.date == DAY)
                )
            ) == 0
            # The skipped fold left the session fully usable.
            assert (await db.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await engine.dispose()

    # Lock released: the fold now runs and lands its rows.
    summary = await run_rollup_for_day(db, DAY)
    assert summary["locked"] == 0
    assert summary["user_day_rows"] == 1


async def test_rollup_failure_alert_inprocess_fallback_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the database itself is down the ai_alert_state write cannot land;
    the in-process fallback must still bound the alert to one send per day."""
    sent = _capture_alerts(monkeypatch)
    monkeypatch.setattr(scheduler, "_rollup_failure_alerted_in_process", set())

    def _broken_session_factory() -> Any:
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _broken_session_factory)

    await scheduler._alert_rollup_failure(RuntimeError("fold exploded"))
    await scheduler._alert_rollup_failure(RuntimeError("fold exploded"))
    await scheduler._alert_rollup_failure(RuntimeError("fold exploded"))
    assert len(sent) == 1
    subject, body = sent[0]
    assert "rollup" in subject.lower()
    assert "RuntimeError" in body


# ---------------------------------------------------------------------------
# 5. Budget / anomaly alert boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spent", "expected"),
    [
        ("49.90", []),
        ("50.00", ["budget_50"]),
        ("79.90", ["budget_50"]),
        ("80.00", ["budget_50", "budget_80"]),
        ("99.90", ["budget_50", "budget_80"]),
        ("100.00", ["budget_50", "budget_80", "budget_100"]),
    ],
)
async def test_budget_alert_boundary_exactness(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    spent: str,
    expected: list[str],
) -> None:
    """Exactly at a threshold the alert fires; a penny below it stays silent.
    Each crossed threshold fires exactly once per month."""
    monkeypatch.setattr(scheduler, "AI_MONTHLY_BUDGET_GBP", "100")
    sent = _capture_alerts(monkeypatch)
    db.add(
        AiRollupFeatureDay(date=date(2026, 9, 10), feature="quote_draft", cost_gbp=Decimal(spent))
    )
    await db.flush()

    fired = await _check_budget_alerts(db, DAY)
    assert fired == expected
    assert len(sent) == len(expected)

    # Repeat evaluation in the same month sends nothing further.
    assert await _check_budget_alerts(db, DAY) == []
    assert len(sent) == len(expected)

    states = (
        (await db.execute(select(AiAlertState).where(AiAlertState.period == "2026-09")))
        .scalars()
        .all()
    )
    assert {state.threshold for state in states} == set(expected)


async def _seed_trailing_costs(db: AsyncSession, daily: str) -> None:
    for offset in range(1, 8):
        db.add(
            AiRollupFeatureDay(
                date=DAY - timedelta(days=offset),
                feature="quote_draft",
                cost_gbp=Decimal(daily),
            )
        )


async def test_cost_spike_exactly_3x_trailing_mean_stays_silent(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spike rule is strictly-greater-than: exactly 3x the trailing mean
    is NOT an anomaly."""
    sent = _capture_alerts(monkeypatch)
    await _seed_trailing_costs(db, "10.00")
    db.add(AiRollupFeatureDay(date=DAY, feature="quote_draft", cost_gbp=Decimal("30.00")))
    await db.flush()
    assert await _check_anomaly_alerts(db, DAY) == []
    assert sent == []


async def test_cost_spike_just_over_3x_fires_once(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_alerts(monkeypatch)
    await _seed_trailing_costs(db, "10.00")
    db.add(AiRollupFeatureDay(date=DAY, feature="quote_draft", cost_gbp=Decimal("30.01")))
    await db.flush()

    assert await _check_anomaly_alerts(db, DAY) == ["cost_spike"]
    assert len(sent) == 1

    assert await _check_anomaly_alerts(db, DAY) == []
    assert len(sent) == 1


async def test_latency_spike_exactly_2x_stays_silent(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same strictly-greater boundary for the p95 latency rule: exactly 2x
    the trailing mean does not page anyone."""
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
    db.add(_event(tenant_id=tenant_id, latency_seconds=2.0))
    await db.flush()
    assert await _check_anomaly_alerts(db, DAY) == []
    assert sent == []


# ---------------------------------------------------------------------------
# 6. Data export: isolation, secrets, shape, serialisation, rate limit
# ---------------------------------------------------------------------------

_SECRET_KEYS = {"password_hash", "magic_link_token", "paddle_checkout_id", "paddle_transaction_id"}
_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _walk(node: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    """Yield (path, value) for every node in a JSON-shaped structure."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _walk(item, f"{path}[{index}]")


def _leaf_key(path: str) -> str:
    """The dict key a walk path ends at (list indices stripped)."""
    return path.rsplit(".", 1)[-1].split("[")[0]


async def test_export_never_contains_other_tenant_rows_anywhere(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Tenant A's export contains zero tenant-B ids or markers — checked
    recursively over the whole payload, not just the top-level lists."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    own_ids = await _seed_tenant_records(db, tenant_id)

    other = Tenant(slug=f"other-{uuid4().hex[:8]}", name="Other Electrical")
    db.add(other)
    await db.flush()
    await set_tenant_in_session(db, other.id)
    other_ids = await _seed_tenant_records(db, other.id)
    other_contact = await db.get(Contact, other_ids["contact_id"])
    assert other_contact is not None
    other_contact.name = "Bob Stranger"
    other_contact.email = "bob.stranger@other.example.com"
    await db.commit()
    await set_tenant_in_session(db, tenant_id)

    response = await admin_client.get("/export/my-data")
    assert response.status_code == 200
    payload = response.json()

    other_id_strings = {str(value) for value in other_ids.values()}
    own_id_strings = {str(value) for value in own_ids.values()}
    seen_strings: set[str] = set()
    for path, node in _walk(payload):
        if isinstance(node, str):
            seen_strings.add(node)
            assert node not in other_id_strings, f"tenant-B id leaked at {path}"
            assert node != "bob.stranger@other.example.com", f"tenant-B email leaked at {path}"
            assert node != "Bob Stranger", f"tenant-B name leaked at {path}"
    # Sanity: tenant A's own rows ARE present (the assertions above are not
    # vacuously passing over an empty export).
    assert own_id_strings & seen_strings == own_id_strings
    assert payload["tenant"]["id"] == str(tenant_id)


async def test_export_never_leaks_secrets_recursively(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Credentials and payment-provider ids appear nowhere in the export —
    recursive key scan AND value scan for the actual secret strings."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    ids = await _seed_tenant_records(db, tenant_id)

    secrets = {
        "password_hash": "scrypt$supersecret-hash",
        "magic_link_token": "ml-secret-token-value",
        "paddle_checkout_id": "chk_secret_123",
        "paddle_transaction_id": "txn_secret_456",
    }
    customer = await db.get(Customer, ids["customer_id"])
    assert customer is not None
    customer.password_hash = secrets["password_hash"]
    customer.magic_link_token = secrets["magic_link_token"]
    invoice = await db.get(Invoice, ids["invoice_id"])
    assert invoice is not None
    invoice.paddle_checkout_id = secrets["paddle_checkout_id"]
    invoice.paddle_transaction_id = secrets["paddle_transaction_id"]
    await db.commit()

    response = await admin_client.get("/export/my-data")
    assert response.status_code == 200
    payload = response.json()

    for path, node in _walk(payload):
        leaf = _leaf_key(path)
        assert leaf not in _SECRET_KEYS, f"secret key exported at {path}"
        assert "paddle" not in leaf.lower(), f"paddle reference exported at {path}"
        assert "token" not in leaf.lower() or leaf == "tokens", f"token-like key at {path}"
        if isinstance(node, str):
            for secret in secrets.values():
                assert secret not in node, f"secret value leaked at {path}"


async def test_export_nested_shape_is_stable(admin_client: AsyncClient, db: AsyncSession) -> None:
    """The exact key set of every exported object is a stable contract."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_tenant_records(db, tenant_id)
    response = await admin_client.get("/export/my-data")
    assert response.status_code == 200
    payload = response.json()

    assert set(payload["tenant"]) == {
        "id",
        "slug",
        "code",
        "name",
        "status",
        "structure",
        "year_established",
        "companies_house_number",
        "nations_served",
        "vat_registered",
        "vat_number",
        "vat_scheme",
        "quote_defaults",
        "branding",
        "settings",
        "created_at",
        "updated_at",
    }
    assert set(payload["contacts"][0]) == {
        "id",
        "name",
        "email",
        "phone",
        "address",
        "postcode",
        "notes",
        "preferred_contact_method",
        "property_type",
        "bedrooms",
        "parking_notes",
        "access_notes",
        "badge_overrides",
        "is_blocked",
        "blocked_at",
        "blocked_reason",
        "created_at",
        "updated_at",
    }
    assert set(payload["customers"][0]) == {
        "id",
        "contact_id",
        "email",
        "full_name",
        "phone",
        "address",
        "postcode",
        "property_profile",
        "is_active",
        "marketing_consent",
        "preferred_contact_method",
        "parking_notes",
        "access_notes",
        "created_at",
        "updated_at",
    }
    quote = payload["quotes"][0]
    assert set(quote) == {
        "id",
        "contact_id",
        "title",
        "description",
        "status",
        "subtotal",
        "vat_rate",
        "vat_amount",
        "total",
        "rounding_adjustment",
        "valid_until",
        "approved_at",
        "sent_at",
        "accepted_dates",
        "ai_metadata",
        "extra_data",
        "line_items",
        "created_at",
        "updated_at",
    }
    assert set(quote["line_items"][0]) == {
        "id",
        "description",
        "quantity",
        "unit",
        "unit_price",
        "total",
        "ai_generated",
        "created_at",
        "updated_at",
    }
    assert set(payload["jobs"][0]) == {
        "id",
        "contact_id",
        "quote_id",
        "title",
        "description",
        "status",
        "scheduled_start",
        "scheduled_end",
        "completed_at",
        "assigned_user_id",
        "address",
        "postcode",
        "lat",
        "lng",
        "notes",
        "created_at",
        "updated_at",
    }
    invoice = payload["invoices"][0]
    assert set(invoice) == {
        "id",
        "contact_id",
        "job_id",
        "quote_id",
        "invoice_number",
        "status",
        "issue_date",
        "due_date",
        "subtotal",
        "vat_rate",
        "vat_amount",
        "total",
        "rounding_adjustment",
        "paid_at",
        "notes",
        "line_items",
        "created_at",
        "updated_at",
    }
    assert set(invoice["line_items"][0]) == {
        "id",
        "description",
        "quantity",
        "unit_price",
        "total",
        "created_at",
        "updated_at",
    }
    assert set(payload["communications"][0]) == {
        "id",
        "contact_id",
        "quote_request_id",
        "channel",
        "direction",
        "sender_role",
        "subject",
        "body",
        "status",
        "created_at",
        "updated_at",
    }


async def test_export_serialisation_is_stable(admin_client: AsyncClient, db: AsyncSession) -> None:
    """Decimals are plain strings (no float rounding); datetimes are ISO-8601
    with a Z suffix, everywhere in the document."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_tenant_records(db, tenant_id)
    response = await admin_client.get("/export/my-data")
    assert response.status_code == 200
    payload = response.json()

    quote = payload["quotes"][0]
    assert quote["subtotal"] == "500.00"
    assert quote["vat_rate"] == "0.20"
    assert quote["total"] == "600.00"
    line = quote["line_items"][0]
    # Line-item money columns carry more decimal places; the contract is that
    # they serialise as exact Decimal strings, never rounded floats.
    for value in (line["quantity"], line["unit_price"], line["total"]):
        assert isinstance(value, str)
        assert "e" not in value.lower()
    assert Decimal(line["quantity"]) == Decimal("1.00")
    assert Decimal(line["unit_price"]) == Decimal("500.00")
    assert Decimal(line["total"]) == Decimal("500.00")

    assert _ISO_Z.match(payload["generated_at"])
    saw_timestamp = False
    for path, node in _walk(payload):
        leaf = _leaf_key(path)
        if leaf.endswith(("_at", "_date")) and node is not None:
            assert isinstance(node, str), f"{path} is not a string"
            assert _ISO_Z.match(node), f"{path} is not ISO-8601 Z: {node!r}"
            saw_timestamp = True
    assert saw_timestamp


@pytest.fixture()
def _enable_rate_limiter() -> Iterator[None]:
    """Re-enable the limiter and clear its buckets (mirrors test_rate_limit.py)."""
    previous = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()
        limiter.enabled = previous


async def test_export_rate_limited_after_hourly_cap(
    admin_client: AsyncClient, db: AsyncSession, _enable_rate_limiter: None
) -> None:
    """The 6/hour per-tenant cap: six exports pass, the seventh is a 429."""
    statuses = []
    for _ in range(7):
        response = await admin_client.get("/export/my-data")
        statuses.append(response.status_code)
    assert statuses == [200, 200, 200, 200, 200, 200, 429]
