"""Tests for W2-A entitlements: plan catalog, AI usage counters, allowance enforcement."""

from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from app.dependencies import require_ai_allowance
from app.models import AIUsageCounter, Subscription, Tenant
from app.plans import (
    BILLABLE_AI_FEATURES,
    PLANS,
    current_period,
    get_plan,
    increment_ai_usage,
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


async def _seed_usage(
    db: AsyncSession, tenant: Tenant, count: int, period: str | None = None
) -> None:
    db.add(
        AIUsageCounter(
            tenant_id=tenant.id,
            period=period or current_period(),
            ai_actions=count,
        )
    )
    await db.flush()


def _enable_entitlements(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.ENTITLEMENTS_ENABLED", True)


# --- Plan catalog ---------------------------------------------------------


def test_plan_catalog_matches_confirmed_pricing() -> None:
    by_key = {plan.key: plan for plan in PLANS}
    assert set(by_key) == {"sole_trader", "pro", "team"}

    sole = by_key["sole_trader"]
    assert (sole.monthly_price_gbp, sole.annual_price_gbp) == (25, 250)
    assert sole.ai_allowance_monthly == 30
    assert sole.overage_behavior == "block"

    pro = by_key["pro"]
    assert (pro.monthly_price_gbp, pro.annual_price_gbp) == (39, 390)
    assert pro.ai_allowance_monthly == 100
    assert pro.overage_behavior == "metered"
    assert pro.featured is True

    team = by_key["team"]
    assert (team.monthly_price_gbp, team.annual_price_gbp) == (29, 290)
    assert team.ai_allowance_monthly == 100
    assert team.overage_behavior == "metered"
    assert team.min_seats == 3
    assert team.pooled_allowance is True

    # Env var NAMES are referenced, never actual Paddle IDs.
    for plan in PLANS:
        assert plan.monthly_price_env.startswith("PADDLE_PRICE_ID_")
        assert plan.annual_price_env.startswith("PADDLE_PRICE_ID_")
        assert "pri_" not in plan.monthly_price_env


def test_legacy_plan_key_mapping() -> None:
    assert resolve_plan_key("starter") == "sole_trader"
    assert resolve_plan_key("pro") == "pro"
    assert resolve_plan_key("business") == "team"
    assert get_plan("starter").key == "sole_trader"
    assert get_plan("business").key == "team"
    with pytest.raises(KeyError):
        get_plan("enterprise")


# --- Usage counter ----------------------------------------------------------


async def test_increment_ai_usage_counts_only_billable_features(
    db: AsyncSession, tenant: Tenant
) -> None:
    assert frozenset({"quote_draft", "quote_refine", "triage_followup"}) == BILLABLE_AI_FEATURES

    assert await increment_ai_usage(db, tenant.id, "quote_draft") == 1
    assert await increment_ai_usage(db, tenant.id, "quote_refine") == 2
    assert await increment_ai_usage(db, tenant.id, "triage_followup") == 3

    # Embeddings and demo quotes are infrastructure, not billable actions.
    assert await increment_ai_usage(db, tenant.id, "embedding") is None
    assert await increment_ai_usage(db, tenant.id, "demo_quote") is None

    await db.flush()
    counter = (
        await db.execute(select(AIUsageCounter).where(AIUsageCounter.tenant_id == tenant.id))
    ).scalar_one()
    assert counter.ai_actions == 3
    assert counter.period == current_period()


async def test_increment_ai_usage_period_rollover(db: AsyncSession, tenant: Tenant) -> None:
    old = await increment_ai_usage(db, tenant.id, "quote_draft", at=datetime(2020, 1, 15))
    assert old == 1
    new = await increment_ai_usage(db, tenant.id, "quote_draft")
    assert new == 1  # a new month starts a fresh counter row

    rows = (
        (
            await db.execute(
                select(AIUsageCounter)
                .where(AIUsageCounter.tenant_id == tenant.id)
                .order_by(AIUsageCounter.period)
            )
        )
        .scalars()
        .all()
    )
    assert [(row.period, row.ai_actions) for row in rows] == [
        ("2020-01", 1),
        (current_period(), 1),
    ]


# --- Enforcement dependency -------------------------------------------------


async def test_allowance_warning_at_80_percent(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_entitlements(monkeypatch)
    db.add(Subscription(tenant_id=tenant.id, plan_key="pro", status="active"))
    await _seed_usage(db, tenant, 80)  # 80/100 = exactly 80%
    await db.flush()

    info = await require_ai_allowance(tenant, db)
    assert info.allowed is True
    assert info.warning is not None
    assert info.used == 80
    assert info.allowance == 100
    assert info.over_limit is False


async def test_block_plan_raises_402_at_100_percent(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_entitlements(monkeypatch)
    db.add(Subscription(tenant_id=tenant.id, plan_key="sole_trader", status="active"))
    await _seed_usage(db, tenant, 30)
    await db.flush()

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_allowance(tenant, db)
    assert exc_info.value.status_code == 402
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail == {
        "detail": "ai_allowance_exceeded",
        "allowance": 30,
        "used": 30,
    }


async def test_metered_plan_allows_overage_and_flags_it(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_entitlements(monkeypatch)
    db.add(Subscription(tenant_id=tenant.id, plan_key="pro", status="active"))
    await _seed_usage(db, tenant, 100)
    await db.flush()

    info = await require_ai_allowance(tenant, db)
    assert info.allowed is True
    assert info.over_limit is True
    assert info.warning is not None


async def test_no_subscription_defaults_to_sole_trader(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_entitlements(monkeypatch)
    info = await require_ai_allowance(tenant, db)
    assert info.plan.key == "sole_trader"
    assert info.allowance == 30
    assert info.allowed is True


async def test_legacy_subscription_plan_key_enforces_mapped_tier(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy ``starter`` subscription inherits sole_trader's 30-action block."""
    _enable_entitlements(monkeypatch)
    db.add(Subscription(tenant_id=tenant.id, plan_key="starter", status="active"))
    await _seed_usage(db, tenant, 30)
    await db.flush()

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_allowance(tenant, db)
    assert exc_info.value.status_code == 402


async def test_kill_switch_off_is_noop(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENTITLEMENTS_ENABLED=false (the default) → pass-through, even over limit."""
    monkeypatch.setattr("app.config.ENTITLEMENTS_ENABLED", False)
    db.add(Subscription(tenant_id=tenant.id, plan_key="sole_trader", status="active"))
    await _seed_usage(db, tenant, 500)
    await db.flush()

    info = await require_ai_allowance(tenant, db)
    assert info.allowed is True
    assert info.warning is None
    assert info.over_limit is False


# --- Plans endpoint ---------------------------------------------------------


async def test_plans_endpoint_returns_tier_catalog(client: AsyncClient) -> None:
    response = await client.get("/billing/plans")
    assert response.status_code == 200, response.text
    plans = response.json()
    assert [p["key"] for p in plans] == ["sole_trader", "pro", "team"]

    for plan in plans:
        assert plan["monthly_price_env"].startswith("PADDLE_PRICE_ID_")
        assert plan["annual_price_env"].startswith("PADDLE_PRICE_ID_")
        assert plan["overage_price_pence"] == 6
        assert plan["trial_days"] == 14
        assert plan["trial_extension_days"] == 30
        assert plan["trial_extension_sent_ai_quotes"] == 3

    by_key = {p["key"]: p for p in plans}
    assert by_key["sole_trader"]["ai_allowance_monthly"] == 30
    assert by_key["sole_trader"]["overage_behavior"] == "block"
    assert by_key["pro"]["featured"] is True
    assert by_key["pro"]["monthly_price_gbp"] == 39
    assert by_key["team"]["min_seats"] == 3
    assert by_key["team"]["pooled_allowance"] is True
    assert by_key["team"]["monthly_price_gbp"] == 29
