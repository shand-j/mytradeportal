"""Subscription / billing endpoints for the tenant paywall.

Beta scope: one active subscription per tenant, three plans, 14-day trial
handled by Paddle. This module owns the checkout-URL creation and the
subscription read model; state mutations happen exclusively via webhooks
(:mod:`app.routers.webhooks`).
"""

from datetime import datetime
from typing import Annotated
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
from app.paddle_client import create_subscription_transaction
from app.rls import set_tenant_in_session
from app.schemas import BillingCheckoutCreate, BillingCheckoutRead, SubscriptionRead

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
</style>
</head>
<body>
<h1 id="status">Loading secure checkout…</h1>
<p class="muted" id="hint">Secure payment processed by Paddle.</p>
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
    if (PADDLE_ENV === "sandbox") { Paddle.Environment.set("sandbox"); }
    Paddle.Setup({
      token: PADDLE_TOKEN,
      eventCallback: function (event) {
        if (event.name === "checkout.completed") {
          document.getElementById("status").textContent = "You're all set!";
          document.getElementById("hint").textContent =
            "Your plan is active. You can close this page and return to the app.";
        } else if (event.name === "checkout.error") {
          fail("Checkout couldn't load. Please try again.");
        }
      }
    });
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


def _price_id_for_plan(plan_key: str) -> str:
    mapping: dict[str, str] = {
        "starter": settings.paddle_price_id_starter,
        "pro": settings.paddle_price_id_pro,
        "business": settings.paddle_price_id_business,
    }
    price_id = mapping.get(plan_key)
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


@router.post("/checkout")
async def create_checkout(
    data: BillingCheckoutCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> BillingCheckoutRead:
    """Create a Paddle checkout URL for the requested plan.

    The URL is Paddle-hosted; the mobile app opens it in the system browser
    and Paddle bounces back to ``success_url`` (or the app default) on
    completion. Subscription state is written by the webhook, not here.
    """
    price_id = _price_id_for_plan(data.plan_key)
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
        checkout = await create_subscription_transaction(
            price_id=price_id,
            tenant_id=str(tenant.id),
            plan_key=data.plan_key,
            customer_email=customer_email,
            success_url=data.success_url,
            discount_id=settings.paddle_beta_discount_id or None,
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


# Re-exported for tests / other modules that want the same "still-good" gate.
ACTIVE_STATUSES = frozenset({"trialing", "active", "past_due"})


def is_subscription_active(subscription: Subscription | None) -> bool:
    """Beta gate: any status where we still let the tenant use the app.

    Excludes ``paused`` and ``canceled``. Past-due gets grace so we don't kick
    tenants during Paddle's dunning window. Not currently enforced anywhere
    because beta = track only.
    """
    if subscription is None:
        return False
    if subscription.status not in ACTIVE_STATUSES:
        return False
    if subscription.trial_ends_at is not None and subscription.status == "trialing":
        return subscription.trial_ends_at > datetime.utcnow()
    return True
