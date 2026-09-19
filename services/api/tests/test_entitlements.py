"""Tests for flat-plan tiers: catalog, capability gates and fair-use guardrails.

The hybrid quota/allowance model (block/metered, overage billing, usage
counters) was replaced by flat tiers with unlimited users and unmetered AI.
What remains to test:

- The flat catalog itself (prices, capabilities, legacy key mapping).
- ``require_tier_feature`` — the only customer-visible enforcement (403 with
  an upgrade hint when a capability is not in the tenant's tier).
- ``fair_use_guard`` — the invisible cost guardrails: per-hour burst 429 and
  the monthly threshold that flips ``ai_cheap_route`` and fires exactly one
  staff alert per org per month.
- ``GET /billing/plans`` — no AI-usage numbers anywhere in the payload.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app import config as app_config
from app.dependencies import fair_use_guard, require_tier_feature
from app.models import AiAlertState, AiCallEvent, Subscription, Tenant
from app.plans import (
    PLAN_CATALOG,
    current_period,
    get_plan,
    lowest_plan_with_feature,
    resolve_plan_key,
)
from app.rls import set_tenant_in_session
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(loop_scope="function")
async def tenant(db: AsyncSession) -> Tenant:
    """A fresh tenant with its RLS context set on the shared session."""
    tenant = Tenant(slug=f"ent-{uuid4().hex[:8]}", name="Entitlements Test")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    return tenant


async def _seed_ai_events(
    db: AsyncSession, tenant: Tenant, count: int, *, at: datetime | None = None
) -> None:
    created = at or datetime.utcnow()
    for _ in range(count):
        db.add(AiCallEvent(tenant_id=tenant.id, feature="quote_draft", created_at=created))
    await db.flush()


# --- Plan catalog ---------------------------------------------------------


def test_plan_catalog_matches_flat_pricing() -> None:
    by_key = {plan.key: plan for plan in PLAN_CATALOG}
    assert set(by_key) == {"sole_trader", "pro", "team"}

    assert (by_key["sole_trader"].monthly_price_gbp, by_key["sole_trader"].annual_price_gbp) == (
        25,
        250,
    )
    assert (by_key["pro"].monthly_price_gbp, by_key["pro"].annual_price_gbp) == (39, 390)
    assert (by_key["team"].monthly_price_gbp, by_key["team"].annual_price_gbp) == (69, 690)
    assert by_key["pro"].featured is True

    # Env var NAMES are referenced, never actual Paddle IDs.
    for plan in PLAN_CATALOG:
        assert plan.monthly_price_env.startswith("PADDLE_PRICE_ID_")
        assert plan.annual_price_env.startswith("PADDLE_PRICE_ID_")
        assert "pri_" not in plan.monthly_price_env


def test_plan_catalog_tiers_differ_by_capability_only() -> None:
    sole, pro, team = (get_plan(key) for key in ("sole_trader", "pro", "team"))

    base = {
        "portal",
        "ai_quote_draft",
        "chase_sequences",
        "online_payments",
        "accounting_sync",
        "data_export",
        "customer_portal",
        "intake_brief",
        "sms_reminders",
    }
    assert sole.features == frozenset(base)
    assert pro.features == frozenset(
        base
        | {
            "drawing_analysis",
            "customer_chat_assistant",
            "certificates",
            "deposits",
            "optional_line_items",
            "offline_mode",
            "priority_models",
        }
    )
    assert team.features == frozenset(
        pro.features
        | {"multi_user_scheduling", "roles_permissions", "shared_portal", "team_reporting"}
    )

    # No quota artifacts anywhere on the dataclass.
    for plan in PLAN_CATALOG:
        assert not hasattr(plan, "ai_allowance_monthly")
        assert not hasattr(plan, "overage_behavior")
        assert not hasattr(plan, "min_seats")
        assert not hasattr(plan, "pooled_allowance")


def test_legacy_plan_key_mapping() -> None:
    assert resolve_plan_key("starter") == "sole_trader"
    assert resolve_plan_key("pro") == "pro"
    assert resolve_plan_key("business") == "team"
    assert get_plan("starter").key == "sole_trader"
    assert get_plan("business").key == "team"
    with pytest.raises(KeyError):
        get_plan("enterprise")


def test_lowest_plan_with_feature_powers_upgrade_hints() -> None:
    assert lowest_plan_with_feature("portal").key == "sole_trader"  # type: ignore[union-attr]
    assert lowest_plan_with_feature("drawing_analysis").key == "pro"  # type: ignore[union-attr]
    assert lowest_plan_with_feature("roles_permissions").key == "team"  # type: ignore[union-attr]
    assert lowest_plan_with_feature("not_a_feature") is None


# --- Tier feature gate ------------------------------------------------------


async def test_tier_feature_gate_allows_pro_capability_on_pro(
    db: AsyncSession, tenant: Tenant
) -> None:
    db.add(Subscription(tenant_id=tenant.id, plan_key="pro", status="active"))
    await db.flush()

    gate = require_tier_feature("drawing_analysis")
    assert await gate(tenant, db) is tenant


async def test_tier_feature_gate_403_for_sole_trader_on_pro_capability(
    db: AsyncSession, tenant: Tenant
) -> None:
    db.add(Subscription(tenant_id=tenant.id, plan_key="sole_trader", status="active"))
    await db.flush()

    gate = require_tier_feature("drawing_analysis")
    with pytest.raises(HTTPException) as exc_info:
        await gate(tenant, db)
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["detail"] == "feature_not_in_plan"
    assert detail["feature"] == "drawing_analysis"
    assert detail["current_plan"] == "sole_trader"
    assert "Pro" in detail["upgrade_hint"]


async def test_tier_feature_gate_defaults_to_sole_trader_without_subscription(
    db: AsyncSession, tenant: Tenant
) -> None:
    gate = require_tier_feature("multi_user_scheduling")
    with pytest.raises(HTTPException) as exc_info:
        await gate(tenant, db)
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert "Team" in detail["upgrade_hint"]

    # Base capabilities pass without any subscription row.
    base_gate = require_tier_feature("ai_quote_draft")
    assert await base_gate(tenant, db) is tenant


async def test_tier_feature_gate_resolves_legacy_plan_keys(
    db: AsyncSession, tenant: Tenant
) -> None:
    """A legacy ``business`` subscription inherits the team capability set."""
    db.add(Subscription(tenant_id=tenant.id, plan_key="business", status="active"))
    await db.flush()

    gate = require_tier_feature("team_reporting")
    assert await gate(tenant, db) is tenant


# --- Fair-use guardrail -----------------------------------------------------


async def test_fair_use_burst_limit_returns_429_with_retry_after(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 3)
    await _seed_ai_events(db, tenant, 3)

    with pytest.raises(HTTPException) as exc_info:
        await fair_use_guard(tenant, db)
    assert exc_info.value.status_code == 429
    headers = exc_info.value.headers
    assert headers is not None
    retry_after = int(headers["Retry-After"])
    assert 0 < retry_after <= 3600

    # Under the limit: passes.
    other = Tenant(slug=f"ent-{uuid4().hex[:8]}", name="Other")
    db.add(other)
    await db.flush()
    await _seed_ai_events(db, other, 2)
    await fair_use_guard(other, db)  # passes: no exception raised


async def test_fair_use_burst_limit_ignores_last_hours_events(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 2)
    await _seed_ai_events(db, tenant, 5, at=datetime.utcnow() - timedelta(hours=2))

    await fair_use_guard(tenant, db)  # passes: no exception raised


async def test_fair_use_threshold_sets_cheap_route_and_alerts_once(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 5)
    # Keep the burst limit out of the way — this test is about the monthly path.
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 5)

    alerts: list[tuple[str, str]] = []

    async def fake_send_alert(subject: str, text: str) -> dict[str, bool]:
        alerts.append((subject, text))
        return {"email": True}

    monkeypatch.setattr("app.dependencies.send_alert", fake_send_alert)

    await fair_use_guard(tenant, db)
    assert tenant.settings["ai_cheap_route"] is True
    assert len(alerts) == 1
    assert tenant.slug in alerts[0][0]

    # The dedupe row landed, keyed per org per month.
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

    # Second crossing in the same month: flag stays set, no second alert.
    await _seed_ai_events(db, tenant, 5)
    await fair_use_guard(tenant, db)
    assert len(alerts) == 1


async def test_fair_use_below_threshold_is_quiet(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config, "AI_FAIR_USE_MONTHLY_THRESHOLD", 100)
    monkeypatch.setattr(app_config, "AI_BURST_LIMIT_PER_HOUR", 10_000)
    await _seed_ai_events(db, tenant, 3)

    async def fail_alert(subject: str, text: str) -> dict[str, bool]:
        raise AssertionError("alert must not fire below the threshold")

    monkeypatch.setattr("app.dependencies.send_alert", fail_alert)

    await fair_use_guard(tenant, db)
    assert "ai_cheap_route" not in tenant.settings


# --- Plans endpoint ---------------------------------------------------------


async def test_plans_endpoint_returns_flat_tier_catalog(client: AsyncClient) -> None:
    response = await client.get("/billing/plans")
    assert response.status_code == 200, response.text
    plans = response.json()
    assert [p["key"] for p in plans] == ["sole_trader", "pro", "team"]

    for plan in plans:
        assert plan["monthly_price_env"].startswith("PADDLE_PRICE_ID_")
        assert plan["annual_price_env"].startswith("PADDLE_PRICE_ID_")
        assert plan["trial_days"] == 14
        assert plan["trial_extension_days"] == 30
        assert plan["trial_extension_sent_ai_quotes"] == 3
        assert isinstance(plan["features"], list) and plan["features"]
        # No AI-usage/quota numbers anywhere in the API response.
        for key in plan:
            assert "allowance" not in key
            assert "overage" not in key

    by_key = {p["key"]: p for p in plans}
    assert by_key["sole_trader"]["seats"] == 1
    assert by_key["pro"]["seats"] == 5
    assert by_key["team"]["seats"] == 15
    assert by_key["sole_trader"]["monthly_price_gbp"] == 25
    assert by_key["sole_trader"]["annual_price_gbp"] == 250
    assert by_key["pro"]["monthly_price_gbp"] == 39
    assert by_key["pro"]["annual_price_gbp"] == 390
    assert by_key["team"]["monthly_price_gbp"] == 69
    assert by_key["team"]["annual_price_gbp"] == 690
    assert by_key["pro"]["featured"] is True
    assert "drawing_analysis" in by_key["pro"]["features"]
    assert "drawing_analysis" not in by_key["sole_trader"]["features"]
    assert "multi_user_scheduling" in by_key["team"]["features"]
