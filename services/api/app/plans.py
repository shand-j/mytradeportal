"""Plan catalog — the single source of truth for tiers, prices and AI allowances.

Both the API (``GET /billing/plans``) and the mobile onboarding flow read this
catalog. Actual Paddle price IDs live in environment variables and are never
invented or exposed here — each tier only references the env var NAMES
(``monthly_price_env`` / ``annual_price_env``) that ops must set when the W2-B
Paddle catalog work lands.

Legacy keys: subscriptions created during beta carry ``plan_key`` values
``starter | pro | business``. ``resolve_plan_key`` maps them onto the current
catalog (starter→sole_trader, pro→pro, business→team) so existing rows keep
working unchanged.

Trial: 14 days, full features, no card (``TRIAL_DAYS``). Sending 3 AI quotes
during the trial extends it to 30 days from that moment (``TRIAL_EXTENSION_*``)
— implemented in ``app/trial.py``; the constants live here so every consumer
agrees on the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import AIUsageCounter

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

OverageBehavior = Literal["block", "metered"]

TRIAL_DAYS = 14
TRIAL_EXTENSION_DAYS = 30
TRIAL_EXTENSION_SENT_AI_QUOTES = 3
OVERAGE_PRICE_PENCE = 6

DEFAULT_PLAN_KEY = "sole_trader"

# Features that count against the monthly AI allowance. Embeddings and the
# public marketing demo are deliberately excluded (infrastructure cost, not
# per-customer value).
BILLABLE_AI_FEATURES: frozenset[str] = frozenset({"quote_draft", "quote_refine", "triage_followup"})


@dataclass(frozen=True)
class Plan:
    """A subscription tier."""

    key: str  # sole_trader | pro | team
    name: str  # display name
    # Env var NAMES holding the Paddle price IDs (values stay server-side).
    monthly_price_env: str
    annual_price_env: str
    # Public list prices in GBP, per user/seat. Display only — Paddle is the
    # billing source of truth.
    monthly_price_gbp: int
    annual_price_gbp: int
    # Included AI actions per month. For team plans this is per seat and the
    # allowance pools across seats (pooled_allowance).
    ai_allowance_monthly: int
    overage_behavior: OverageBehavior  # block = hard stop at 100%, metered = billed
    min_seats: int
    pooled_allowance: bool
    featured: bool  # rendered as "Most popular" by clients


PLANS: tuple[Plan, ...] = (
    Plan(
        key="sole_trader",
        name="Sole Trader",
        monthly_price_env="PADDLE_PRICE_ID_SOLE_TRADER_MONTH",
        annual_price_env="PADDLE_PRICE_ID_SOLE_TRADER_YEAR",
        monthly_price_gbp=25,
        annual_price_gbp=250,
        ai_allowance_monthly=30,
        overage_behavior="block",
        min_seats=1,
        pooled_allowance=False,
        featured=False,
    ),
    Plan(
        key="pro",
        name="Pro",
        monthly_price_env="PADDLE_PRICE_ID_PRO_MONTH",
        annual_price_env="PADDLE_PRICE_ID_PRO_YEAR",
        monthly_price_gbp=39,
        annual_price_gbp=390,
        ai_allowance_monthly=100,
        overage_behavior="metered",
        min_seats=1,
        pooled_allowance=False,
        featured=True,
    ),
    Plan(
        key="team",
        name="Team",
        monthly_price_env="PADDLE_PRICE_ID_TEAM_MONTH",
        annual_price_env="PADDLE_PRICE_ID_TEAM_YEAR",
        monthly_price_gbp=29,
        annual_price_gbp=290,
        ai_allowance_monthly=100,
        overage_behavior="metered",
        min_seats=3,
        pooled_allowance=True,
        featured=False,
    ),
)

# Existing subscriptions carry these plan_key values; map them onto PLANS.
LEGACY_PLAN_KEY_MAP: dict[str, str] = {
    "starter": "sole_trader",
    "pro": "pro",
    "business": "team",
}

_PLANS_BY_KEY: dict[str, Plan] = {plan.key: plan for plan in PLANS}


def resolve_plan_key(key: str) -> str:
    """Map a (possibly legacy) subscription plan_key onto a current tier key."""
    return LEGACY_PLAN_KEY_MAP.get(key, key)


def get_plan(key: str) -> Plan:
    """Return the catalog entry for a current or legacy plan key."""
    plan = _PLANS_BY_KEY.get(resolve_plan_key(key))
    if plan is None:
        raise KeyError(f"Unknown plan key: {key}")
    return plan


def plan_to_public_dict(plan: Plan) -> dict[str, Any]:
    """Serialise a tier for ``GET /billing/plans``.

    Price env var NAMES are included so ops and clients can tell which
    variable configures which tier; the Paddle IDs themselves never leave the
    server. GBP list prices are public marketing copy, so they are safe to
    expose.
    """
    return {
        "key": plan.key,
        "name": plan.name,
        "monthly_price_env": plan.monthly_price_env,
        "annual_price_env": plan.annual_price_env,
        "monthly_price_gbp": plan.monthly_price_gbp,
        "annual_price_gbp": plan.annual_price_gbp,
        "ai_allowance_monthly": plan.ai_allowance_monthly,
        "overage_behavior": plan.overage_behavior,
        "overage_price_pence": OVERAGE_PRICE_PENCE,
        "min_seats": plan.min_seats,
        "pooled_allowance": plan.pooled_allowance,
        "featured": plan.featured,
        "trial_days": TRIAL_DAYS,
        "trial_extension_days": TRIAL_EXTENSION_DAYS,
        "trial_extension_sent_ai_quotes": TRIAL_EXTENSION_SENT_AI_QUOTES,
    }


@dataclass(frozen=True)
class AllowanceInfo:
    """Result of the ``require_ai_allowance`` entitlement check.

    ``over_limit`` is True on metered plans once the included allowance is
    exhausted — the telemetry writer uses it to flag overage rows for billing.
    """

    plan: Plan
    used: int
    allowance: int
    allowed: bool
    warning: str | None
    over_limit: bool


def current_period(at: datetime | None = None) -> str:
    """Return the billing period key (``YYYY-MM``, UTC) for a moment in time."""
    return (at or datetime.utcnow()).strftime("%Y-%m")


async def get_ai_usage(db: AsyncSession, tenant_id: UUID, period: str | None = None) -> int:
    """Return the tenant's billable AI action count for a period (default: current)."""
    result = await db.execute(
        select(func.coalesce(AIUsageCounter.ai_actions, 0)).where(
            AIUsageCounter.tenant_id == tenant_id,
            AIUsageCounter.period == (period or current_period()),
        )
    )
    value = result.scalar_one_or_none()
    return int(value) if value is not None else 0


async def increment_ai_usage(
    db: AsyncSession,
    tenant_id: UUID,
    feature: str,
    *,
    at: datetime | None = None,
) -> int | None:
    """Increment the tenant's monthly AI usage counter for a billable feature.

    Returns the new count, or ``None`` when the feature is not billable
    (embeddings, demo quotes) and the call is a no-op. Atomic via
    INSERT ... ON CONFLICT so concurrent increments never lose counts; a new
    calendar month simply starts a fresh ``period`` row.
    """
    if feature not in BILLABLE_AI_FEATURES:
        return None
    period = current_period(at)
    stmt = (
        pg_insert(AIUsageCounter)
        .values(
            tenant_id=tenant_id,
            period=period,
            ai_actions=1,
        )
        .on_conflict_do_update(
            constraint="uq_ai_usage_counters_tenant_period",
            set_={
                "ai_actions": AIUsageCounter.ai_actions + 1,
                "updated_at": datetime.utcnow(),
            },
        )
        .returning(AIUsageCounter.ai_actions)
    )
    result = await db.execute(stmt)
    return int(result.scalar_one())
