"""Subscription / billing endpoints for the tenant paywall.

Flat pricing model: one subscription per business, three flat tiers, unlimited
users, AI unmetered on every tier. There is no seat, quantity or overage
logic anywhere in this module. The 14-day trial is handled by Paddle /
``app.trial``. This module owns the checkout-URL creation and the
subscription read model; state mutations happen exclusively via webhooks
(:mod:`app.routers.webhooks`).
"""

import os
from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import Subscription, Tenant
from app.paddle_client import (
    await_transaction_subscription_id,
    create_cardless_trial_transaction,
    create_customer_address,
    create_customer_portal_session,
    create_subscription_transaction,
    get_or_create_customer,
    get_payment_method_update_transaction,
    get_price,
    update_subscription,
    update_subscription_custom_data,
)
from app.plans import PLAN_CATALOG, get_plan, plan_to_public_dict
from app.rls import set_tenant_in_session
from app.routers.webhooks import _upsert_subscription
from app.schemas import (
    BillingCheckoutCreate,
    BillingCheckoutRead,
    BillingPlanChangeCreate,
    SubscriptionRead,
)

router = APIRouter(prefix="/billing", tags=["Billing"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = structlog.get_logger("api.billing")


_CHECKOUT_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Trade Portal — Checkout</title>
<script src="https://cdn.paddle.com/paddle/v2/paddle.js"></script>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #0f172a;
         max-width: 560px; margin: 0 auto; padding: 24px; text-align: center; }
  .muted { color: #64748b; font-size: 14px; }
  .return-btn { display: none; margin: 24px auto 0; padding: 14px 28px;
    background: #2563EB; color: #fff; border-radius: 10px; text-decoration: none;
    font-weight: 600; font-size: 16px; }
</style>
</head>
<body>
<h1 id="status">Loading secure checkout…</h1>
<p class="muted" id="hint">Secure payment processed by Paddle.</p>
<a class="return-btn" id="return-btn" href="mtp://">Return to the app</a>
<script>
  var PADDLE_TOKEN = "__PADDLE_CLIENT_TOKEN__";
  var PADDLE_ENV = "__PADDLE_ENV__";
  var txn = new URLSearchParams(location.search).get("_ptxn");
  function fail(msg) {
    document.getElementById("status").textContent = msg;
    document.getElementById("hint").textContent =
      "Close this page and try again from the app.";
  }
  if (!txn) {
    fail("Missing checkout transaction.");
  } else {
    // paddle.js v2 initialization: the page loads /paddle/v2/paddle.js, whose
    // entry point is Paddle.Initialize (Paddle.Setup is the retired v1 API —
    // initializing v1-style leaves the checkout session half-initialized, the
    // transaction-checkout request 403s, and cardless-trial transactions are
    // rejected with "only supported by one-page checkout variant" even though
    // settings.variant is one-page).
    var init = {
      token: PADDLE_TOKEN,
      eventCallback: function (event) {
        if (event.name === "checkout.completed") {
          document.getElementById("status").textContent = "You're all set!";
          document.getElementById("hint").textContent =
            "Your plan is active.";
          // Deep-link back into the app (mtp:// scheme) so the user lands on
          // the dashboard instead of being stranded in the browser.
          document.getElementById("return-btn").style.display = "inline-block";
          window.location.href = "mtp://";
        } else if (event.name === "checkout.error") {
          fail("Checkout couldn't load. Please try again.");
        }
      }
    };
    if (PADDLE_ENV === "sandbox") { init.environment = "sandbox"; }
    Paddle.Initialize(init);
    Paddle.Checkout.open({ transactionId: txn, settings: { variant: "one-page" } });
  }
</script>
</body>
</html>
"""


@router.get("/checkout-page", include_in_schema=False)
async def checkout_page() -> HTMLResponse:
    """Hosted Paddle.js page the mobile app opens for subscription checkout.

    Paddle Billing has no fully hosted checkout page: transactions return
    ``checkout.url`` = your default payment link + ``?_ptxn=<txn>``, and the
    page at that URL must run Paddle.js to render the overlay. This endpoint
    is that page; the mobile app passes its absolute URL as ``success_url``
    when creating the checkout. Public by design — the only secret in the
    URL is the transaction id the caller just received.
    """
    if not settings.paddle_client_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Checkout is not configured",
        )
    html = _CHECKOUT_PAGE.replace("__PADDLE_CLIENT_TOKEN__", settings.paddle_client_token)
    html = html.replace("__PADDLE_ENV__", "sandbox" if settings.paddle_sandbox else "production")
    return HTMLResponse(html)


def _legacy_price_id_for_plan(plan_key: str) -> str:
    """Beta-era single-price env vars, keyed on the resolved current tier."""
    legacy: dict[str, str] = {
        "sole_trader": settings.paddle_price_id_starter,
        "pro": settings.paddle_price_id_pro,
        "team": settings.paddle_price_id_business,
    }
    return legacy.get(plan_key, "")


def _price_id_for_plan(plan_key: str, interval: str = "month") -> str:
    """Resolve the Paddle price id for a plan key and billing interval.

    Reads the per-interval env vars declared on the plan catalog
    (``PADDLE_PRICE_ID_{SOLE_TRADER,PRO,TEAM}_{MONTH,YEAR}`` — the settings
    object predates them, so they are read from the process environment
    directly), falling back to the legacy beta-era vars
    (``PADDLE_PRICE_ID_STARTER``/``PRO``/``BUSINESS``) so existing checkouts
    keep working until the new catalog IDs are wired. Legacy plan keys
    (``starter``/``business``) resolve through the plan catalog.
    """
    try:
        plan = get_plan(plan_key)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or unconfigured plan: {plan_key}",
        ) from None
    env_name = plan.monthly_price_env if interval == "month" else plan.annual_price_env
    price_id = os.environ.get(env_name, "").strip() or _legacy_price_id_for_plan(plan.key)
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or unconfigured plan: {plan_key}",
        )
    return price_id


async def _get_or_create_subscription(
    db: AsyncSession, tenant_id: UUID, plan_key: str
) -> Subscription:
    existing = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if existing is None:
        existing = Subscription(tenant_id=tenant_id, plan_key=plan_key, status="incomplete")
        db.add(existing)
        await db.flush()
    else:
        existing.plan_key = plan_key
    return existing


async def _price_is_cardless_trial(price_id: str) -> bool:
    """True when the Paddle price carries a trial that needs no payment method.

    Paddle rejects a rendered checkout for such prices ("Cardless trial
    transaction is not linked to a subscription"), so these go through the
    server-side cardless-trial flow instead of a standard transaction.
    """
    price = await get_price(price_id)
    trial_period = price.get("trial_period") or {}
    return bool(trial_period) and trial_period.get("requires_payment_method") is False


async def _cardless_trial_checkout(
    *,
    price_id: str,
    tenant_id: UUID,
    plan_key: str,
    subscription: Subscription,
    customer_id: str,
    tenant_row: Tenant | None,
) -> dict[str, str]:
    """Hosted checkout for a cardless-trial plan.

    Paddle never renders a signup checkout for a cardless-trial price. The
    supported lifecycle (per Paddle's cardless-trials docs):

    - A live-but-unpaid subscription already exists in Paddle (``trialing``, or
      ``past_due`` while dunning) → hand the client the subscription-linked
      payment-method-update transaction (zero-value; must be opened with the
      one-page Paddle.js variant, which the checkout page does). The stored
      payment method takes over billing at trial end.
    - No usable Paddle subscription yet (local trial only, or a canceled one
      being reactivated) → create the subscription server-side (a ``billed``
      transaction auto-completes and Paddle creates the trialing subscription),
      stamp it with our ``tenant_id`` custom_data so webhook events key onto
      our mirror row, then build the payment-method-update checkout for it.

    Returns the same ``{transaction_id, checkout_url}`` contract as a standard
    checkout; the transaction id is the one the checkout page opens.
    """
    paddle_subscription_id = subscription.paddle_subscription_id
    if paddle_subscription_id and subscription.status in ("trialing", "past_due"):
        return await get_payment_method_update_transaction(paddle_subscription_id)

    postcode = (tenant_row.settings or {}).get("postcode") if tenant_row else None
    address_id = await create_customer_address(
        customer_id,
        postal_code=str(postcode) if postcode else None,
    )
    transaction_id = await create_cardless_trial_transaction(
        price_id=price_id,
        tenant_id=str(tenant_id),
        plan_key=plan_key,
        customer_id=customer_id,
        address_id=address_id,
    )
    paddle_subscription_id = await await_transaction_subscription_id(transaction_id)
    await update_subscription_custom_data(
        paddle_subscription_id,
        {"tenant_id": str(tenant_id), "plan_key": plan_key},
    )
    subscription.paddle_subscription_id = paddle_subscription_id
    subscription.paddle_customer_id = customer_id
    return await get_payment_method_update_transaction(paddle_subscription_id)


@router.get("/plans")
async def list_plans() -> list[dict[str, Any]]:
    """Return the subscription tier catalog for clients (mobile onboarding).

    Public by design — the onboarding plan step renders before checkout and
    must never be blocked by auth/tenant state. Each tier carries its key,
    display name, flat monthly/annual GBP list prices (per business —
    unlimited users on every tier), the env var NAMES that hold the Paddle
    price IDs (the IDs themselves stay server-side), the capability list, the
    featured flag, and trial terms. There are deliberately no AI-usage
    numbers: AI is unmetered on every tier. Mobile renders from this and
    falls back to a static copy of the same numbers if the fetch fails.
    """
    return [plan_to_public_dict(plan) for plan in PLAN_CATALOG]


@router.post("/checkout")
async def create_checkout(
    data: BillingCheckoutCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> BillingCheckoutRead:
    """Create a Paddle checkout URL for the requested plan.

    One flat subscription per business: there is no seat or quantity logic —
    the Paddle price itself is the whole tier. The URL is Paddle-hosted; the
    mobile app opens it in the system browser and Paddle bounces back to
    ``success_url`` (or the app default) on completion. Subscription state is
    written by the webhook, not here.

    Prices with a cardless trial (``requires_payment_method: false``) cannot
    use a rendered signup checkout — Paddle rejects it at render time. For
    those, the subscription is created (or continued) server-side and the
    returned URL is a subscription-linked payment-method-update checkout
    (see :func:`_cardless_trial_checkout`).
    """
    price_id = _price_id_for_plan(data.plan_key, data.interval)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    await set_tenant_in_session(db, tenant.id)

    subscription = await _get_or_create_subscription(db, tenant.id, data.plan_key)

    tenant_row = await db.get(Tenant, tenant.id)
    customer_email = tenant_row.email if tenant_row and tenant_row.email else current_user.email

    try:
        # Bind the checkout to a Paddle customer so the hosted page prefills
        # the account email and keeps it non-editable.
        customer_id = await get_or_create_customer(
            customer_email, name=current_user.full_name or None
        )
        if await _price_is_cardless_trial(price_id):
            # Prices whose trial needs no card can't go through a rendered
            # signup checkout at all — create/continue the subscription
            # server-side and hand back the payment-method-update checkout.
            checkout = await _cardless_trial_checkout(
                price_id=price_id,
                tenant_id=tenant.id,
                plan_key=data.plan_key,
                subscription=subscription,
                customer_id=customer_id,
                tenant_row=tenant_row,
            )
        else:
            checkout = await create_subscription_transaction(
                price_id=price_id,
                tenant_id=str(tenant.id),
                plan_key=data.plan_key,
                customer_email=customer_email,
                success_url=data.success_url,
                discount_id=settings.paddle_beta_discount_id or None,
                customer_id=customer_id,
            )
    except Exception as exc:
        logger.error(
            "billing_checkout_failed",
            tenant_id=str(tenant.id),
            plan_key=data.plan_key,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider is unavailable. Try again shortly.",
        ) from exc

    subscription.paddle_transaction_id = checkout["transaction_id"]
    subscription.paddle_price_id = price_id
    await db.commit()

    logger.info(
        "billing_checkout_created",
        tenant_id=str(tenant.id),
        plan_key=data.plan_key,
        transaction_id=checkout["transaction_id"],
    )
    return BillingCheckoutRead(
        transaction_id=checkout["transaction_id"],
        checkout_url=checkout["checkout_url"],
    )


@router.post("/plan-change")
async def change_plan(
    data: BillingPlanChangeCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> SubscriptionRead:
    """Change the tenant's plan mid-cycle with immediate proration.

    One flat subscription per business, so a plan change is a single-item
    replace on the Paddle subscription (the new tier's price at the chosen
    interval), billed ``prorated_immediately``: Paddle charges or credits the
    difference for the rest of the current period and the new plan applies
    now. The response entity is mirrored through the same
    :func:`app.routers.webhooks._upsert_subscription` path the webhooks use,
    so the plan key / tier entitlements re-derive from the new price id and
    stay consistent with the paywall gate. If the prorated charge fails
    Paddle keeps the old plan (``prevent_change``) and this surfaces as 502.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    tenant_id = tenant.id  # capture before any rollback expires the ORM object
    await set_tenant_in_session(db, tenant_id)
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if sub is None or not sub.paddle_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Paddle subscription for this business",
        )
    price_id = _price_id_for_plan(data.plan_key, data.interval)

    try:
        updated = await update_subscription(sub.paddle_subscription_id, price_id)
    except Exception as exc:
        logger.error(
            "billing_plan_change_failed",
            tenant_id=str(tenant.id),
            plan_key=data.plan_key,
            paddle_subscription_id=sub.paddle_subscription_id,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider is unavailable. Try again shortly.",
        ) from exc

    # Mirror through the webhook upsert so plan/status/period re-derive from
    # the price id exactly as they do for a subscription.updated event.
    await _upsert_subscription("subscription.updated", updated)

    # The upsert commits on its own engine session; this request session's
    # snapshot predates it. Roll back (nothing of ours to keep) and re-read.
    await db.rollback()
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if sub is None:  # pragma: no cover - defensive; the upsert just wrote it
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Subscription failed to sync. Try again shortly.",
        )
    logger.info(
        "billing_plan_change_applied",
        tenant_id=str(tenant_id),
        plan_key=sub.plan_key,
        paddle_subscription_id=sub.paddle_subscription_id,
    )
    return SubscriptionRead.model_validate(sub)


@router.get("/subscription")
async def get_subscription(
    tenant: TenantDep,
    db: DbDep,
) -> SubscriptionRead | None:
    """Return the tenant's current subscription state (or ``null`` if none)."""
    await set_tenant_in_session(db, tenant.id)
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    if sub is None:
        return None
    return SubscriptionRead.model_validate(sub)


@router.post("/portal-session")
async def create_portal_session(
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> dict[str, str]:
    """Mint a Paddle customer-portal URL for the tenant's subscription.

    The mobile app opens the returned URL in the system browser so the user
    can manage their payment method, download Paddle invoices, or cancel.
    Only the short-lived overview URL crosses the wire.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    await set_tenant_in_session(db, tenant.id)
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    if sub is None or not sub.paddle_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Paddle customer is linked to this subscription yet",
        )
    try:
        portal_url = await create_customer_portal_session(sub.paddle_customer_id)
    except Exception as exc:
        logger.error(
            "billing_portal_session_failed",
            tenant_id=str(tenant.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider is unavailable. Try again shortly.",
        ) from exc
    logger.info("billing_portal_session_created", tenant_id=str(tenant.id))
    return {"portal_url": portal_url}


# Re-exported for tests / other modules that want the same "still-good" gate.
ACTIVE_STATUSES = frozenset({"trialing", "active", "past_due"})

# Past-due grace: while a failed payment is in dunning (Paddle retrying in
# the background, our dunning emails going out) the tenant keeps app access.
# The grace is anchored on the failed period's end (the date the payment came
# due) and after it expires the C22 paywall re-engages (402 until resolved).
PAST_DUE_GRACE_DAYS = 7


def is_subscription_active(subscription: Subscription | None) -> bool:
    """Beta gate: any status where we still let the tenant use the app.

    Excludes ``paused`` and ``canceled``. ``past_due`` passes only within
    :data:`PAST_DUE_GRACE_DAYS` of the failed period's end date — grace while
    Paddle/our dunning chases the payment, then the paywall re-engages. A
    past-due row with no known period end keeps the permissive beta default
    (access allowed) rather than kicking a tenant on incomplete data. Not
    currently enforced anywhere because beta = track only.
    """
    if subscription is None:
        return False
    if subscription.status not in ACTIVE_STATUSES:
        return False
    if subscription.status == "past_due":
        if subscription.current_period_end is None:
            return True
        return datetime.utcnow() <= subscription.current_period_end + timedelta(
            days=PAST_DUE_GRACE_DAYS
        )
    if subscription.trial_ends_at is not None and subscription.status == "trialing":
        return subscription.trial_ends_at > datetime.utcnow()
    return True
