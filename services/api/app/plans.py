"""Plan catalog — the single source of truth for tiers, prices and capabilities.

Flat pricing model (locked decision): one subscription per business, AI
unmetered on every tier. There are NO credits, quotas, allowances or overage
charges anywhere in this catalog — tiers differ by capability plus a seat
count (``Plan.seats``) that caps how many staff users (active + pending
invites) a tenant may have; ``POST /users/invite`` enforces it. Fair-use
guardrails (burst limit, cheap-route threshold) live in
``app.dependencies.fair_use_guard`` and are invisible to customers.

Both the API (``GET /billing/plans``) and the mobile onboarding flow read this
catalog. Actual Paddle price IDs live in environment variables and are never
invented or exposed here — each tier only references the env var NAMES
(``monthly_price_env`` / ``annual_price_env``) that ops must set.

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
from typing import Any

TRIAL_DAYS = 14
TRIAL_EXTENSION_DAYS = 30
TRIAL_EXTENSION_SENT_AI_QUOTES = 3

DEFAULT_PLAN_KEY = "sole_trader"

# Capability vocabulary. A feature name is a stable string a router can gate
# on via ``app.dependencies.require_tier_feature``. Tiers are cumulative:
# pro = sole_trader + extras, team = pro + extras.
SOLE_TRADER_FEATURES: frozenset[str] = frozenset(
    {
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
)

PRO_EXTRA_FEATURES: frozenset[str] = frozenset(
    {
        "drawing_analysis",
        "customer_chat_assistant",
        "certificates",
        "deposits",
        "optional_line_items",
        "offline_mode",
        "priority_models",
    }
)

TEAM_EXTRA_FEATURES: frozenset[str] = frozenset(
    {
        "multi_user_scheduling",
        "roles_permissions",
        "shared_portal",
        "team_reporting",
    }
)


@dataclass(frozen=True)
class Plan:
    """A flat subscription tier: one price per business, capped staff seats."""

    key: str  # sole_trader | pro | team
    name: str  # display name
    # Env var NAMES holding the Paddle price IDs (values stay server-side).
    monthly_price_env: str
    annual_price_env: str
    # Public list prices in GBP per business (flat — not per seat). Display
    # only; Paddle is the billing source of truth.
    monthly_price_gbp: int
    annual_price_gbp: int
    # Staff seats: max active users + pending invites on the tenant.
    seats: int
    # Capability set — the only other thing that differs between tiers.
    features: frozenset[str]
    featured: bool  # rendered as "Most popular" by clients


PLAN_CATALOG: tuple[Plan, ...] = (
    Plan(
        key="sole_trader",
        name="Sole Trader",
        monthly_price_env="PADDLE_PRICE_ID_SOLE_TRADER_MONTH",
        annual_price_env="PADDLE_PRICE_ID_SOLE_TRADER_YEAR",
        monthly_price_gbp=25,
        annual_price_gbp=250,
        seats=1,
        features=SOLE_TRADER_FEATURES,
        featured=False,
    ),
    Plan(
        key="pro",
        name="Pro",
        monthly_price_env="PADDLE_PRICE_ID_PRO_MONTH",
        annual_price_env="PADDLE_PRICE_ID_PRO_YEAR",
        monthly_price_gbp=39,
        annual_price_gbp=390,
        seats=5,
        features=SOLE_TRADER_FEATURES | PRO_EXTRA_FEATURES,
        featured=True,
    ),
    Plan(
        key="team",
        name="Team",
        monthly_price_env="PADDLE_PRICE_ID_TEAM_MONTH",
        annual_price_env="PADDLE_PRICE_ID_TEAM_YEAR",
        monthly_price_gbp=69,
        annual_price_gbp=690,
        seats=15,
        features=SOLE_TRADER_FEATURES | PRO_EXTRA_FEATURES | TEAM_EXTRA_FEATURES,
        featured=False,
    ),
)

# Existing subscriptions carry these plan_key values; map them onto the catalog.
LEGACY_PLAN_KEY_MAP: dict[str, str] = {
    "starter": "sole_trader",
    "pro": "pro",
    "business": "team",
}

_PLANS_BY_KEY: dict[str, Plan] = {plan.key: plan for plan in PLAN_CATALOG}


def resolve_plan_key(key: str) -> str:
    """Map a (possibly legacy) subscription plan_key onto a current tier key."""
    return LEGACY_PLAN_KEY_MAP.get(key, key)


def get_plan(key: str) -> Plan:
    """Return the catalog entry for a current or legacy plan key."""
    plan = _PLANS_BY_KEY.get(resolve_plan_key(key))
    if plan is None:
        raise KeyError(f"Unknown plan key: {key}")
    return plan


def lowest_plan_with_feature(feature: str) -> Plan | None:
    """Return the cheapest tier that includes a capability (for upgrade hints)."""
    for plan in PLAN_CATALOG:  # catalog is ordered cheapest → most expensive
        if feature in plan.features:
            return plan
    return None


def next_plan_with_more_seats(plan: Plan) -> Plan | None:
    """Return the cheapest tier with more seats than ``plan`` (upgrade hint)."""
    for candidate in PLAN_CATALOG:  # catalog is ordered cheapest → most expensive
        if candidate.seats > plan.seats:
            return candidate
    return None


def plan_to_public_dict(plan: Plan) -> dict[str, Any]:
    """Serialise a tier for ``GET /billing/plans``.

    Price env var NAMES are included so ops and clients can tell which
    variable configures which tier; the Paddle IDs themselves never leave the
    server. GBP list prices are public marketing copy, so they are safe to
    expose. There are deliberately no AI-usage numbers anywhere in this
    payload — AI is unmetered on every tier.
    """
    return {
        "key": plan.key,
        "name": plan.name,
        "monthly_price_env": plan.monthly_price_env,
        "annual_price_env": plan.annual_price_env,
        "monthly_price_gbp": plan.monthly_price_gbp,
        "annual_price_gbp": plan.annual_price_gbp,
        "features": sorted(plan.features),
        "seats": plan.seats,
        "featured": plan.featured,
        "trial_days": TRIAL_DAYS,
        "trial_extension_days": TRIAL_EXTENSION_DAYS,
        "trial_extension_sent_ai_quotes": TRIAL_EXTENSION_SENT_AI_QUOTES,
    }


def current_period(at: datetime | None = None) -> str:
    """Return the monthly period key (``YYYY-MM``, UTC) for a moment in time.

    Used by the fair-use guardrail to scope its per-month alert dedupe.
    """
    return (at or datetime.utcnow()).strftime("%Y-%m")
