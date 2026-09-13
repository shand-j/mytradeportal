"""Hardening for the invisible fair-use guardrails on AI endpoints.

Flat pricing means AI is unmetered for customers; ``fair_use_guard`` is the
internal cost brake and must behave exactly:

- Burst: HTTP 429 + ``Retry-After`` when the tenant's current-hour
  ``ai_call_events`` count reaches ``AI_BURST_LIMIT_PER_HOUR`` — passing at
  limit-1, isolated per UTC-hour window and per tenant.
- Monthly: at exactly ``AI_FAIR_USE_MONTHLY_THRESHOLD`` the tenant's
  ``settings["ai_cheap_route"]`` flips on and exactly ONE staff alert fires
  per org per month (deduped via ``ai_alert_state``), resetting with the
  month; last month's events never count.
- Fail-open: any internal error (DB blip, alert failure) is swallowed — the
  guardrail can never take down an AI endpoint.
- The ``require_ai_allowance`` back-compat shim keeps
  ``app.routers.quotes``'s three AI call sites (``/quotes/generate``,
  ``/quotes/generate-async``, ``/quotes/{id}/refine``) wired and working.
"""

import inspect
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Annotated, get_args, get_type_hints
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from app import config as app_config
from app.dependencies import fair_use_guard, require_ai_allowance
from app.main import app
from app.models import AiAlertState, AiCallEvent, Tenant
from app.plans import current_period
from app.rls import set_tenant_in_session
from fastapi import Depends, HTTPException
from fastapi.params import Depends as DependsParam
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(loop_scope="function")
async def tenant(db: AsyncSession) -> Tenant:
    """A fresh tenant with its RLS context set on the shared session."""
    tenant = Tenant(slug=f"fair-{uuid4().hex[:8]}", name="Fair Use Test")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    return tenant


@pytest_asyncio.fixture(loop_scope="function")
async def other_tenant(db: AsyncSession, tenant: Tenant) -> Tenant:
    """A second tenant for per-tenant isolation checks."""
    other = Tenant(slug=f"fair-{uuid4().hex[:8]}", name="Fair Use Other")
    db.add(other)
    await db.flush()
    return other


async def _seed_ai_events(
    db: AsyncSession, tenant: Tenant, count: int, *, at: datetime | None = None
) -> None:
    created = at or datetime.utcnow()
    for _ in range(count):
        db.add(AiCallEvent(tenant_id=tenant.id, feature="quote_draft", created_at=created))
    await db.flush()


@pytest.fixture
def recorded_alerts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture staff alerts instead of sending them."""
    alerts: list[tuple[str, str]] = []

    async def fake_send_alert(subject: str, text: str) -> dict[str, bool]:
        alerts.append((subject, text))
        return {"email": True}

    monkeypatch.setattr("app.dependencies.send_alert", fake_send_alert)
    return alerts


# --- Burst limit ----------------------------------------------------------------


async def test_burst_429_at_exactly_the_limit(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 4)
    await _seed_ai_events(db, tenant, 4)

    with pytest.raises(HTTPException) as exc_info:
        await fair_use_guard(tenant, db)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "rate_limited"
    headers = exc_info.value.headers
    assert headers is not None
    retry_after = int(headers["Retry-After"])
    assert 0 < retry_after <= 3600


async def test_burst_passes_at_limit_minus_one(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 4)
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 10_000)
    await _seed_ai_events(db, tenant, 3)

    await fair_use_guard(tenant, db)  # passes: no exception raised


async def test_burst_window_isolation_ignores_previous_hours(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Events from earlier UTC hours never count towards the burst limit."""
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 2)
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 10_000)
    await _seed_ai_events(db, tenant, 6, at=datetime.utcnow() - timedelta(hours=1, minutes=1))

    await fair_use_guard(tenant, db)  # passes: no exception raised


async def test_burst_is_per_tenant(
    db: AsyncSession,
    tenant: Tenant,
    other_tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 2)
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 10_000)
    await _seed_ai_events(db, tenant, 2)
    await _seed_ai_events(db, other_tenant, 1)

    with pytest.raises(HTTPException) as exc_info:
        await fair_use_guard(tenant, db)
    assert exc_info.value.status_code == 429

    await fair_use_guard(other_tenant, db)  # other tenant unaffected


# --- Monthly threshold ------------------------------------------------------------


async def test_threshold_crossing_at_exactly_the_threshold(
    db: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    recorded_alerts: list[tuple[str, str]],
) -> None:
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 3)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 3)

    await fair_use_guard(tenant, db)

    assert tenant.settings["ai_cheap_route"] is True
    assert len(recorded_alerts) == 1
    subject, text = recorded_alerts[0]
    assert tenant.slug in subject
    assert str(app_config.AI_FAIR_USE_MONTHLY_THRESHOLD) in text


async def test_threshold_minus_one_stays_quiet(
    db: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    recorded_alerts: list[tuple[str, str]],
) -> None:
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 4)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 3)

    await fair_use_guard(tenant, db)

    assert "ai_cheap_route" not in tenant.settings
    assert recorded_alerts == []


async def test_repeated_crossings_same_month_alert_exactly_once(
    db: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    recorded_alerts: list[tuple[str, str]],
) -> None:
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 2)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 2)

    for _ in range(3):
        await fair_use_guard(tenant, db)

    assert len(recorded_alerts) == 1
    rows = (
        (
            await db.execute(
                select(AiAlertState).where(
                    AiAlertState.period == current_period(),
                    AiAlertState.threshold == f"fair_use:{tenant.id}",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_monthly_reset_fires_again_next_period(
    db: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    recorded_alerts: list[tuple[str, str]],
) -> None:
    """The per-month dedupe resets: after the period rolls over, a fresh
    crossing alerts again (and a second dedupe row lands under the new key)."""
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 2)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 2)

    await fair_use_guard(tenant, db)
    assert len(recorded_alerts) == 1

    next_period = "2999-12"  # any period != current_period()
    monkeypatch.setattr("app.dependencies.current_period", lambda: next_period)

    await fair_use_guard(tenant, db)
    assert len(recorded_alerts) == 2

    periods = {
        row.period
        for row in (
            (
                await db.execute(
                    select(AiAlertState).where(AiAlertState.threshold == f"fair_use:{tenant.id}")
                )
            )
            .scalars()
            .all()
        )
    }
    assert periods == {current_period(), next_period}


async def test_last_months_events_do_not_count(
    db: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    recorded_alerts: list[tuple[str, str]],
) -> None:
    """Monthly reset of the COUNT: a tenant that crossed last month but is
    quiet this month keeps the default (expensive) route."""
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 2)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    await _seed_ai_events(db, tenant, 9, at=month_start - timedelta(minutes=1))

    await fair_use_guard(tenant, db)

    assert "ai_cheap_route" not in tenant.settings
    assert recorded_alerts == []


async def test_threshold_is_per_tenant(
    db: AsyncSession,
    tenant: Tenant,
    other_tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    recorded_alerts: list[tuple[str, str]],
) -> None:
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 2)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 2)

    await fair_use_guard(other_tenant, db)  # quiet tenant: nothing happens
    assert "ai_cheap_route" not in other_tenant.settings

    await fair_use_guard(tenant, db)
    assert tenant.settings["ai_cheap_route"] is True
    assert len(recorded_alerts) == 1
    assert tenant.slug in recorded_alerts[0][0]


async def test_request_and_scheduler_paths_share_one_dedupe_key(
    db: AsyncSession,
    tenant: Tenant,
    other_tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    recorded_alerts: list[tuple[str, str]],
) -> None:
    """The request-path guard and the nightly rollup alert dedupe on the SAME
    ``fair_use:<tenant_id>`` key — whichever fires first suppresses the other,
    so an org never gets two alerts for the same month."""
    from app import scheduler

    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 2)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    monkeypatch.setattr(scheduler, "AI_FAIR_USE_MONTHLY_THRESHOLD", 2)
    scheduler_alerts: list[tuple[str, str]] = []

    async def fake_scheduler_alert(subject: str, text: str) -> dict[str, bool]:
        scheduler_alerts.append((subject, text))
        return {"email": True}

    monkeypatch.setattr(scheduler, "send_alert", fake_scheduler_alert)

    # Request path fires first for `tenant`; scheduler path for `other_tenant`.
    await _seed_ai_events(db, tenant, 2)
    await _seed_ai_events(db, other_tenant, 2)
    await fair_use_guard(tenant, db)
    assert len(recorded_alerts) == 1

    # Nightly run: only other_tenant may fire — tenant's dedupe row from the
    # request path must suppress the scheduler's alert for the same month.
    fired = await scheduler._check_fair_use_alerts(db, datetime.utcnow().date())
    assert fired == [str(other_tenant.id)]
    assert len(scheduler_alerts) == 1

    # Reverse direction: the scheduler's dedupe row suppresses the request
    # path for other_tenant (the cheap-route flip still applies).
    await fair_use_guard(other_tenant, db)
    assert other_tenant.settings["ai_cheap_route"] is True
    assert len(recorded_alerts) == 1


# --- Fail-open --------------------------------------------------------------------


async def test_db_error_inside_guard_fails_open(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB blip mid-guard must never take down an AI endpoint."""
    monkeypatch.setattr(db, "scalar", AsyncMock(side_effect=RuntimeError("connection reset")))

    await fair_use_guard(tenant, db)  # swallowed: no exception raised


async def test_alert_failure_fails_open_but_keeps_cheap_route(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alert dispatch blowing up is swallowed; the cheap-route flip (which
    happened before dispatch) still stands."""
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 1)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 1)
    monkeypatch.setattr(
        "app.dependencies.send_alert", AsyncMock(side_effect=RuntimeError("smtp down"))
    )

    await fair_use_guard(tenant, db)  # swallowed: no exception raised
    assert tenant.settings["ai_cheap_route"] is True


async def test_require_ai_allowance_also_fails_open(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "scalar", AsyncMock(side_effect=RuntimeError("connection reset")))

    await require_ai_allowance(tenant, db)  # swallowed: no exception raised


# --- The guard over the full HTTP stack --------------------------------------------


@pytest.fixture
def guarded_route() -> Iterator[str]:
    """Register a real GET endpoint protected by ``fair_use_guard``."""
    path = f"/__test_fair_use_{uuid4().hex[:8]}"

    @app.get(path)
    async def _guarded(
        _guard: Annotated[None, Depends(fair_use_guard)],
    ) -> dict[str, bool]:
        return {"ok": True}

    route = app.routes[-1]
    try:
        yield path
    finally:
        app.routes.remove(route)


async def test_guarded_endpoint_returns_429_with_retry_after_header(
    admin_client: AsyncClient,
    db: AsyncSession,
    guarded_route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The burst 429 surfaces over HTTP with a usable Retry-After header."""
    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    tenant_row = await db.get(Tenant, tenant_id)
    assert tenant_row is not None

    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 1)

    ok = await admin_client.get(guarded_route)
    assert ok.status_code == 200, ok.text  # limit-1 (zero events): passes

    await _seed_ai_events(db, tenant_row, 1)
    limited = await admin_client.get(guarded_route)
    assert limited.status_code == 429, limited.text
    retry_after = int(limited.headers["Retry-After"])
    assert 0 < retry_after <= 3600


# --- require_ai_allowance shim: import-level wiring ---------------------------------


def test_quotes_router_imports_and_ai_call_sites_stay_wired() -> None:
    """The shim keeps ``app.routers.quotes`` importable, and all three AI
    endpoints (``/generate``, ``/generate-async``, ``/{id}/refine``) still
    declare the allowance dependency — which now means the fair-use guard."""
    from app.dependencies import AiAllowanceDep  # noqa: F401  (import must work)
    from app.routers import quotes

    for handler in (quotes.generate_quote, quotes.generate_quote_async, quotes.refine_quote):
        params = inspect.signature(handler).parameters
        assert "allowance" in params, f"{handler.__name__} lost its allowance dependency"
        # The dependency is declared via Annotated metadata (AiAllowanceDep),
        # not a parameter default.
        hints = get_type_hints(handler, include_extras=True)
        metadata = get_args(hints["allowance"])
        depends = next((m for m in metadata if isinstance(m, DependsParam)), None)
        assert depends is not None, f"{handler.__name__} allowance is not a Depends"
        assert depends.dependency is require_ai_allowance


async def test_require_ai_allowance_delegates_to_fair_use_guard(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shim applies the guard and nothing else (returns None)."""
    calls: list[None] = []

    async def fake_guard(tenant_arg: Tenant, db_arg: AsyncSession) -> None:
        calls.append(None)

    monkeypatch.setattr("app.dependencies.fair_use_guard", fake_guard)

    await require_ai_allowance(tenant, db)  # returns None; handlers never consume it
    assert len(calls) == 1
