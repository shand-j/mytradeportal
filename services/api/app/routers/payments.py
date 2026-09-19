"""Stripe Connect payment endpoints (customer → tradie card payments, ADR-003).

Staff-only, tenant-scoped. Covers Express onboarding (connect/status/return),
the AccountSession endpoint for embedded in-app onboarding
(connect/session), the tenant-level accept-card default, and listing recorded
payments for an invoice. Online card checkout itself is created from the public document
endpoint (``app.routers.public_docs``) and settled via
``app.routers.stripe_webhooks``.

Paddle is NOT involved anywhere here — it remains for the platform's own SaaS
subscription only. Unconfigured Stripe (empty ``STRIPE_SECRET_KEY``) yields a
clean 503 ``payments_not_configured``; Stripe-side failures during onboarding
(e.g. the platform not enrolled in Connect, or the Accounts v2 preview being
unavailable) yield 503 ``payments_unavailable`` with a ``connect_failed`` log
event — never a 500.
"""

from typing import Annotated, Any, cast
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config, stripe_client
from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import StripeAccount, Tenant
from app.rls import set_tenant_in_session
from app.routers.invoices import _get_invoice
from app.schemas import PaymentRead

router = APIRouter(prefix="/payments", tags=["Payments"])
logger = structlog.get_logger("api.payments")
DbDep = Annotated[AsyncSession, Depends(get_db)]


class PaymentStatusRead(BaseModel):
    stripe_configured: bool
    connected: bool
    stripe_account_id: str | None
    details_submitted: bool
    charges_enabled: bool
    payouts_enabled: bool
    onboarding_complete: bool
    accept_card_default: bool


class ConnectRequest(BaseModel):
    return_url: str | None = None
    refresh_url: str | None = None


class ConnectRead(BaseModel):
    onboarding_url: str


class ConnectSessionRead(BaseModel):
    client_secret: str
    expires_at: int
    stripe_account_id: str
    publishable_key: str


class PaymentSettingsUpdate(BaseModel):
    accept_card_default: bool


def tenant_accept_card_default(tenant: Tenant) -> bool:
    """Tenant-level default for offering card payment on new invoices.

    Lives in the tenant settings JSON (``settings["payments"]
    ["accept_card_default"]``) — deliberately not a tenants column. Defaults
    to off until the tradie opts in.
    """
    payments = (tenant.settings or {}).get("payments") or {}
    return bool(payments.get("accept_card_default", False))


def invoice_accepts_card(invoice_accept_card_payments: bool | None, tenant: Tenant) -> bool:
    """Resolve the per-invoice override against the tenant default."""
    if invoice_accept_card_payments is not None:
        return invoice_accept_card_payments
    return tenant_accept_card_default(tenant)


async def _get_stripe_account(db: AsyncSession, tenant_id: UUID) -> StripeAccount | None:
    return cast(
        "StripeAccount | None",
        await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id)),
    )


def _onboarding_urls(data: ConnectRequest) -> tuple[str, str]:
    """Return/refresh URLs for the hosted Express onboarding flow.

    Defaults point at the back-office payments settings page derived from
    ``APP_PUBLIC_URL``; clients may pass explicit deep links instead.
    """
    base = settings.app_public_url.rstrip("/")
    return_url = data.return_url or (f"{base}/settings/payments?stripe=return" if base else "")
    refresh_url = data.refresh_url or (f"{base}/settings/payments?stripe=refresh" if base else "")
    if not return_url or not refresh_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="return_url and refresh_url are required when APP_PUBLIC_URL is unset",
        )
    return return_url, refresh_url


async def _sync_account_from_stripe(db: AsyncSession, account: StripeAccount) -> StripeAccount:
    """Refresh the mirrored capability flags from Stripe (source of truth)."""
    remote = await stripe_client.retrieve_account(account.stripe_account_id)
    account.details_submitted = bool(remote["details_submitted"])
    account.charges_enabled = bool(remote["charges_enabled"])
    account.payouts_enabled = bool(remote["payouts_enabled"])
    account.onboarding_complete = account.charges_enabled and account.payouts_enabled
    await db.flush()
    return account


def _tenant_entity_type(tenant: Tenant) -> str | None:
    """Map the tenant's business structure onto the Accounts v2 identity enum.

    Read from the dedicated column first, falling back to the onboarding
    wizard's business_identity step (the column isn't populated from the
    wizard yet). Returns None when unknown — entity type is never guessed,
    because it steers Stripe's whole KYC path.
    """
    structure = tenant.structure or (
        (tenant.onboarding_progress or {}).get("business_identity") or {}
    ).get("value", {}).get("structure")
    if structure == "sole_trader":
        return "individual"
    if structure in ("ltd", "llp"):
        return "company"
    return None


async def _provision_account(
    db: AsyncSession,
    tenant: Tenant,
    current_user: Any,
) -> StripeAccount:
    """Return the tenant's connected account, creating it (with pre-fill) if absent.

    Pre-fills everything onboarding already knows — contact email, phone,
    trading name, postcode, entity type — so Stripe skips those steps. Any
    Stripe-side failure (platform not enrolled in Connect, Accounts v2
    preview unavailable) becomes a 503 ``payments_unavailable`` with a
    ``connect_failed`` log event, never a 500 and never a half-written row.
    """
    account = await _get_stripe_account(db, tenant.id)
    if account is not None:
        return account
    try:
        created = await stripe_client.create_connected_account_v2(
            email=current_user.email if current_user is not None else tenant.email or None,
            display_name=tenant.name,
            tenant_id=str(tenant.id),
            phone=tenant.phone or None,
            postcode=tenant.postcode,
            entity_type=_tenant_entity_type(tenant),
        )
    except stripe_client.PaymentsNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_not_configured",
        ) from exc
    except Exception as exc:
        if not stripe_client.is_stripe_error(exc):
            raise
        logger.error(
            "connect_failed",
            tenant_id=str(tenant.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_unavailable",
        ) from exc
    account = StripeAccount(
        tenant_id=tenant.id,
        stripe_account_id=str(created["id"]),
    )
    db.add(account)
    await db.flush()
    return account


def _status_read(account: StripeAccount | None, tenant: Tenant) -> PaymentStatusRead:
    return PaymentStatusRead(
        stripe_configured=stripe_client.is_configured(),
        connected=account is not None,
        stripe_account_id=account.stripe_account_id if account else None,
        details_submitted=account.details_submitted if account else False,
        charges_enabled=account.charges_enabled if account else False,
        payouts_enabled=account.payouts_enabled if account else False,
        onboarding_complete=account.onboarding_complete if account else False,
        accept_card_default=tenant_accept_card_default(tenant),
    )


@router.get("/status")
async def get_payment_status(tenant: TenantDep, db: DbDep) -> PaymentStatusRead:
    """Payment connection status for the current tenant.

    When an account exists the mirrored flags are first synced from Stripe
    (the source of truth), so the app always reads fresh state after the
    tradie returns from onboarding — no manual refresh step. A Stripe outage
    degrades to the last mirrored flags rather than failing the read.
    """
    await set_tenant_in_session(db, tenant.id)
    account = await _get_stripe_account(db, tenant.id)
    if account is not None and stripe_client.is_configured():
        try:
            await _sync_account_from_stripe(db, account)
            await db.commit()
        except Exception:
            logger.warning("stripe_status_sync_failed", tenant_id=str(tenant.id))
    return _status_read(account, tenant)


@router.post("/connect")
async def connect_stripe_account(
    data: ConnectRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ConnectRead:
    """Create (or reuse) the tenant's Express account and return its onboarding URL.

    The account is provisioned through the Accounts v2 API as a recipient
    account (see ``stripe_client.create_connected_account_v2``); the hosted
    onboarding link itself is still a v1 Account Link, which Stripe supports
    for v2 account IDs.
    """
    if not stripe_client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_not_configured",
        )
    await set_tenant_in_session(db, tenant.id)
    return_url, refresh_url = _onboarding_urls(data)

    account = await _provision_account(db, tenant, current_user)

    try:
        onboarding_url = await stripe_client.create_account_link(
            account.stripe_account_id,
            return_url=return_url,
            refresh_url=refresh_url,
        )
    except Exception as exc:
        if not stripe_client.is_stripe_error(exc):
            raise
        logger.error(
            "connect_failed",
            tenant_id=str(tenant.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_unavailable",
        ) from exc
    await db.commit()
    return ConnectRead(onboarding_url=onboarding_url)


@router.post("/connect/session")
async def create_connect_session(
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ConnectSessionRead:
    """Create an AccountSession for Stripe's embedded onboarding component.

    This is the backend half of fully in-app Connect onboarding: the client
    (RN SDK / Stripe.js embedded components) mounts the account-onboarding
    component with this client secret instead of bouncing to a hosted
    AccountLink URL. The tenant's connected account is provisioned first when
    absent, reusing the same Accounts v2 recipient configuration as
    ``/payments/connect``.
    """
    if not stripe_client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_not_configured",
        )
    await set_tenant_in_session(db, tenant.id)
    account = await _provision_account(db, tenant, current_user)

    try:
        session = await stripe_client.create_account_session(account.stripe_account_id)
    except Exception as exc:
        if not stripe_client.is_stripe_error(exc):
            raise
        logger.error(
            "connect_failed",
            tenant_id=str(tenant.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_unavailable",
        ) from exc
    await db.commit()
    return ConnectSessionRead(
        client_secret=str(session["client_secret"]),
        expires_at=int(session["expires_at"]),
        stripe_account_id=account.stripe_account_id,
        publishable_key=config.STRIPE_PUBLISHABLE_KEY,
    )


@router.get("/onboarding-return", response_class=HTMLResponse)
async def onboarding_return(tenant: TenantDep, db: DbDep) -> HTMLResponse:
    """Sync the account flags after hosted onboarding and confirm completion.

    Stripe redirects the tradie's browser here once the hosted flow ends; the
    return URL configured at connect time carries them back into the app. The
    response is a minimal HTML interstitial so a stray browser tab still lands
    somewhere sensible.
    """
    if not stripe_client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_not_configured",
        )
    await set_tenant_in_session(db, tenant.id)
    account = await _get_stripe_account(db, tenant.id)
    if account is not None:
        try:
            await _sync_account_from_stripe(db, account)
        except Exception:
            logger.warning("stripe_onboarding_sync_failed", tenant_id=str(tenant.id))
        await db.commit()
    complete = account is not None and account.onboarding_complete
    heading = "Card payments are ready" if complete else "Almost there"
    body = (
        "You can take card payments on invoices now — you can close this window."
        if complete
        else "Stripe still needs a few details before you can take card payments."
    )
    return HTMLResponse(
        f"<!doctype html><html><head><title>{heading}</title></head>"
        f"<body><h1>{heading}</h1><p>{body}</p></body></html>"
    )


@router.patch("/settings")
async def update_payment_settings(
    data: PaymentSettingsUpdate,
    tenant: TenantDep,
    db: DbDep,
) -> PaymentStatusRead:
    """Set the tenant-level default for offering card payment on invoices."""
    await set_tenant_in_session(db, tenant.id)
    row = await db.get(Tenant, tenant.id)
    if row is None:  # TenantDep guarantees the row exists; mypy can't know.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    merged: dict[str, Any] = dict(row.settings or {})
    payments = dict(merged.get("payments") or {})
    payments["accept_card_default"] = data.accept_card_default
    merged["payments"] = payments
    row.settings = merged
    await db.commit()
    account = await _get_stripe_account(db, tenant.id)
    return _status_read(account, row)


@router.get("/invoice/{invoice_id}")
async def list_invoice_payments(
    invoice_id: UUID,
    tenant: TenantDep,
    db: DbDep,
) -> list[PaymentRead]:
    """List payments for an invoice."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    return [PaymentRead.model_validate(p) for p in invoice.payments]
