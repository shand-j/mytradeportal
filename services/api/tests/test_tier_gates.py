"""Capability-matrix hardening for the flat-tier gate.

Exhaustive coverage of ``app.plans``'s capability vocabulary x every tier:

- The catalog is cumulative with no leaks: sole_trader is exactly the base
  set, pro = base + pro extras, team = pro + team extras.
- ``require_tier_feature`` passes for entitled tiers and 403s with a
  structured ``feature_not_in_plan`` payload plus the correct cheapest-tier
  upgrade hint for every (tier, feature) combination that is not entitled.
- A tenant with no subscription row defaults to sole_trader.
- Legacy plan keys (starter/business) resolve and gate like their modern
  equivalents.
- The gate is exercised over the full HTTP stack (auth, tenant resolution,
  RLS, paywall middleware) by wiring it onto a real endpoint path via
  ``app.dependency_overrides``/route registration, the same pattern the
  existing tests use for ``get_db``.
- Regression guard: the removed hybrid quota model
  (``increment_ai_usage``/``get_ai_usage``/``AllowanceInfo``/
  ``BILLABLE_AI_FEATURES``/``ENTITLEMENTS_ENABLED``) cannot creep back into
  ``plans.py`` / ``config.py`` without failing this file.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import pytest
import pytest_asyncio
from app import config as app_config
from app import plans as plans_module
from app.dependencies import require_tier_feature
from app.main import app
from app.models import Subscription, Tenant
from app.plans import (
    PLAN_CATALOG,
    PRO_EXTRA_FEATURES,
    SOLE_TRADER_FEATURES,
    TEAM_EXTRA_FEATURES,
    lowest_plan_with_feature,
)
from app.rls import set_tenant_in_session
from fastapi import Depends, HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

BASE = set(SOLE_TRADER_FEATURES)
PRO_EXTRAS = set(PRO_EXTRA_FEATURES)
TEAM_EXTRAS = set(TEAM_EXTRA_FEATURES)
VOCABULARY = BASE | PRO_EXTRAS | TEAM_EXTRAS

# Expected cumulative entitlement per tier key.
TIER_FEATURES: dict[str, set[str]] = {
    "sole_trader": BASE,
    "pro": BASE | PRO_EXTRAS,
    "team": BASE | PRO_EXTRAS | TEAM_EXTRAS,
}


@pytest_asyncio.fixture(loop_scope="function")
async def tenant(db: AsyncSession) -> Tenant:
    """A fresh tenant with its RLS context set on the shared session."""
    tenant = Tenant(slug=f"gate-{uuid4().hex[:8]}", name="Tier Gate Test")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    return tenant


# --- Catalog shape: cumulative, no leaks --------------------------------------


def test_capability_vocabulary_partitions_cleanly() -> None:
    """Base, pro extras and team extras are disjoint; their union is the
    whole gating vocabulary every tier is drawn from."""
    assert BASE.isdisjoint(PRO_EXTRAS)
    assert BASE.isdisjoint(TEAM_EXTRAS)
    assert PRO_EXTRAS.isdisjoint(TEAM_EXTRAS)
    assert BASE and PRO_EXTRAS and TEAM_EXTRAS


def test_catalog_feature_sets_are_cumulative_without_leaks() -> None:
    by_key = {plan.key: plan for plan in PLAN_CATALOG}
    assert set(by_key) == set(TIER_FEATURES)
    for tier_key, expected in TIER_FEATURES.items():
        assert by_key[tier_key].features == frozenset(expected), (
            f"{tier_key} features drifted from the cumulative matrix"
        )
    # No feature escapes the declared vocabulary onto any tier.
    for plan in PLAN_CATALOG:
        assert plan.features <= frozenset(VOCABULARY)


# --- require_tier_feature: the full matrix -------------------------------------


@pytest.mark.parametrize("tier", sorted(TIER_FEATURES))
@pytest.mark.parametrize("feature", sorted(VOCABULARY))
async def test_gate_matrix_every_feature_every_tier(
    db: AsyncSession, tenant: Tenant, tier: str, feature: str
) -> None:
    """For each (tier, feature): entitled → passes; otherwise 403 with the
    structured payload and the cheapest-tier upgrade hint."""
    db.add(Subscription(tenant_id=tenant.id, plan_key=tier, status="active"))
    await db.flush()

    gate = require_tier_feature(feature)
    if feature in TIER_FEATURES[tier]:
        assert await gate(tenant, db) is tenant
        return

    with pytest.raises(HTTPException) as exc_info:
        await gate(tenant, db)
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["detail"] == "feature_not_in_plan"
    assert detail["feature"] == feature
    assert detail["current_plan"] == tier
    cheapest = lowest_plan_with_feature(feature)
    assert cheapest is not None  # every vocabulary feature exists on some tier
    assert cheapest.name in detail["upgrade_hint"]


async def test_gate_hint_names_pro_for_pro_only_and_team_for_team_only(
    db: AsyncSession, tenant: Tenant
) -> None:
    """Sole trader on a pro-only feature is steered to Pro; on a team-only
    feature, to Team — never to a dearer tier than necessary."""
    db.add(Subscription(tenant_id=tenant.id, plan_key="sole_trader", status="active"))
    await db.flush()

    for feature in sorted(PRO_EXTRAS):
        with pytest.raises(HTTPException) as exc_info:
            await require_tier_feature(feature)(tenant, db)
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Pro" in detail["upgrade_hint"]
        assert "Team" not in detail["upgrade_hint"]

    for feature in sorted(TEAM_EXTRAS):
        with pytest.raises(HTTPException) as exc_info:
            await require_tier_feature(feature)(tenant, db)
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Team" in detail["upgrade_hint"]


async def test_gate_tenant_without_subscription_defaults_to_sole_trader(
    db: AsyncSession, tenant: Tenant
) -> None:
    """No subscription row → sole_trader entitlements, not an error."""
    for feature in sorted(BASE):
        assert await require_tier_feature(feature)(tenant, db) is tenant

    for feature in sorted(VOCABULARY - BASE):
        with pytest.raises(HTTPException) as exc_info:
            await require_tier_feature(feature)(tenant, db)
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail["current_plan"] == "sole_trader"


@pytest.mark.parametrize(
    ("legacy_key", "expected_tier"),
    [("starter", "sole_trader"), ("pro", "pro"), ("business", "team")],
)
async def test_gate_resolves_legacy_plan_keys(
    db: AsyncSession, tenant: Tenant, legacy_key: str, expected_tier: str
) -> None:
    """Beta-era plan keys gate exactly like their modern tier equivalents."""
    db.add(Subscription(tenant_id=tenant.id, plan_key=legacy_key, status="active"))
    await db.flush()

    entitled = TIER_FEATURES[expected_tier]
    for feature in sorted(entitled):
        assert await require_tier_feature(feature)(tenant, db) is tenant
    for feature in sorted(VOCABULARY - entitled):
        with pytest.raises(HTTPException) as exc_info:
            await require_tier_feature(feature)(tenant, db)
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        # The 403 payload reports the RESOLVED tier, not the legacy key.
        assert detail["current_plan"] == expected_tier


# --- The gate on a real endpoint path (full HTTP stack) ------------------------


@pytest.fixture
def gated_route() -> Iterator[str]:
    """Register a real GET endpoint gated on ``drawing_analysis`` (pro+).

    Exercises the gate through auth, tenant resolution, RLS and the paywall
    middleware rather than by calling the dependency in isolation. The route
    is removed after the test so the shared app stays clean.
    """
    path = f"/__test_tier_gate_{uuid4().hex[:8]}"

    @app.get(path)
    async def _gated(
        tenant: Annotated[Tenant, Depends(require_tier_feature("drawing_analysis"))],
    ) -> dict[str, str]:
        return {"tenant": tenant.slug}

    route = app.routes[-1]
    try:
        yield path
    finally:
        app.routes.remove(route)


async def test_gated_endpoint_403_without_subscription_then_200_on_pro(
    admin_client: AsyncClient, db: AsyncSession, gated_route: str
) -> None:
    """No subscription row (paywall lets it through) → gate 403s as
    sole_trader; upgrading the row to pro flips the same request to 200."""
    denied = await admin_client.get(gated_route)
    assert denied.status_code == 403, denied.text
    body = denied.json()["detail"]
    assert body["detail"] == "feature_not_in_plan"
    assert body["feature"] == "drawing_analysis"
    assert body["current_plan"] == "sole_trader"
    assert "Pro" in body["upgrade_hint"]

    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    db.add(Subscription(tenant_id=tenant_id, plan_key="pro", status="active"))
    await db.flush()

    allowed = await admin_client.get(gated_route)
    assert allowed.status_code == 200, allowed.text


async def test_gated_endpoint_403_for_sole_trader_row(
    admin_client: AsyncClient, db: AsyncSession, gated_route: str
) -> None:
    """An explicit sole_trader subscription is still 403 on a pro-only gate —
    and the paywall must not interfere (row is active, so only the gate can
    block)."""
    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    db.add(Subscription(tenant_id=tenant_id, plan_key="sole_trader", status="active"))
    await db.flush()

    response = await admin_client.get(gated_route)
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["detail"] == "feature_not_in_plan"


# --- Regression guard: the hybrid quota model must not creep back --------------


_APP_DIR = Path(__file__).resolve().parents[1] / "app"

_BANNED_PLANS_SYMBOLS = (
    "increment_ai_usage",
    "get_ai_usage",
    "AllowanceInfo",
    "BILLABLE_AI_FEATURES",
)


def test_plans_module_exposes_no_quota_artifacts() -> None:
    """grep-level + import-level: plans.py carries no usage-metering API."""
    source = (_APP_DIR / "plans.py").read_text()
    for symbol in _BANNED_PLANS_SYMBOLS:
        assert symbol not in source, f"{symbol} reappeared in plans.py"
        assert not hasattr(plans_module, symbol), f"plans.{symbol} is importable again"


def test_config_has_no_entitlements_flag() -> None:
    source = (_APP_DIR / "config.py").read_text()
    assert "ENTITLEMENTS_ENABLED" not in source
    assert not hasattr(app_config, "ENTITLEMENTS_ENABLED")
