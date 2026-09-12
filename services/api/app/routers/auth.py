"""Authentication endpoints for the back-office UI and native clients."""

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import select, update

from app.dependencies import (
    ActiveUserDep,
    DbDep,
    _extract_tenant_slug,
    get_current_tenant,
    resolve_tenant,
)
from app.email import send_email
from app.email_templates import password_reset as password_reset_template
from app.limiter import limiter
from app.models import Customer, PasswordResetToken, Tenant, User
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
    UserLogin,
    UserRead,
)
from app.security import (
    clear_auth_cookie,
    create_access_token,
    get_password_hash,
    set_auth_cookie,
    verify_password,
)
from app.supabase import (
    admin_create_user,
    admin_update_password,
    is_supabase_configured,
    sign_in_with_password,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = structlog.get_logger("api.auth")

# Reset tokens are single-use and short-lived; 30 minutes is long enough for
# email delivery + the customer clicking through, and short enough to bound
# damage if the email is intercepted.
_PASSWORD_RESET_TTL_MINUTES = 30
_RESET_TOKEN_BYTES = 32


def _hash_reset_token(token: str) -> str:
    """SHA-256 the raw token; the DB only ever stores this hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def _build_reset_url(request: Request, raw_token: str) -> str:
    """Build the emailed reset link against the public landing site.

    ``PASSWORD_RESET_BASE_URL`` (env) must point at the marketing site
    (``https://www.mytradeportal.co.uk`` in production) — app users cannot
    reset on the back-office app or the Django admin that ``APP_PUBLIC_URL``
    may target. Falls back to ``APP_PUBLIC_URL``, then the API's own origin,
    so local dev keeps working without extra config.
    """
    from app.config import settings as _settings

    base = (
        os.environ.get("PASSWORD_RESET_BASE_URL", "").strip()
        or _settings.app_public_url
        or str(request.base_url).rstrip("/")
    ).rstrip("/")
    return f"{base}/reset-password?token={raw_token}"


async def _invalidate_reset_tokens(db: DbDep, owner_type: str, owner_id: UUID) -> None:
    """Mark every outstanding token for the account as used.

    Called when a fresh token is issued (only the newest emailed link stays
    valid) and again after a successful reset (defence in depth).
    """
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.owner_type == owner_type,
            PasswordResetToken.owner_id == owner_id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=datetime.utcnow())
    )


def _has_explicit_tenant_context(request: Request, data: UserLogin) -> bool:
    """Return True when the caller supplied a tenant slug or Host subdomain."""
    if data.tenant_slug:
        return True
    host = request.headers.get("host")
    if not host:
        return False
    host = host.split(":")[0]
    if host in ("localhost", "127.0.0.1", "::1"):
        return False
    parts = host.split(".")
    return len(parts) >= 2 and parts[0] not in ("www", "api", "admin")


async def _resolve_login_tenant(
    request: Request, data: UserLogin, db: DbDep
) -> tuple[Tenant, User | None]:
    """Resolve the tenant for a login request and optionally pre-load the user.

    - Explicit ``tenant_slug`` or Host subdomain: resolve that tenant.
    - Bare domain (e.g. ``localhost:8000``) with no tenant context: look the user
      up by email across all tenants and resolve their tenant. This is required
      for native mobile login where the app does not yet know the tenant slug.
    """
    if data.tenant_slug:
        return await resolve_tenant(db, data.tenant_slug), None

    host = request.headers.get("host")
    has_subdomain = bool(host) and _extract_tenant_slug(host) is not None
    if has_subdomain:
        return await get_current_tenant(request, db=db), None

    # Bare-domain fallback: locate the user by email, then derive the tenant.
    # This lookup runs before any tenant context exists, so it must bypass RLS
    # — otherwise the users table reads as empty and every bare-domain login
    # (e.g. the mobile app, which doesn't know the tenant slug yet) 401s.
    # Transaction-scoped bypass (no connection leak). No enumeration risk: the
    # response is the same 401 whether or not the email exists, and the caller
    # still has to present a valid password. Duplicates (repeat onboarding
    # attempts) resolve to the newest account.
    await bypass_rls_for_transaction(db)
    user_result = await db.execute(
        select(User).where(User.email == data.email).order_by(User.created_at.desc())
    )
    user = user_result.scalars().first()
    if user is not None:
        tenant = await db.get(Tenant, user.tenant_id)
        if tenant is not None and tenant.is_active:
            return tenant, user

    # Last resort: default tenant (preserves existing web login behaviour).
    return await get_current_tenant(request, db=db), None


async def _authenticate(request: Request, data: UserLogin, db: DbDep) -> tuple[Tenant, User]:
    """Resolve the tenant and verify credentials, or raise 401.

    Shared by the cookie-based ``/login`` (web) and token-based ``/token``
    (native) endpoints so both apply identical tenant resolution and
    Supabase/bcrypt credential checks.
    """
    tenant, user = await _resolve_login_tenant(request, data, db)
    await set_tenant_in_session(db, tenant.id)

    if user is None:
        user_result = await db.execute(
            select(User).where(User.email == data.email, User.tenant_id == tenant.id)
        )
        user = user_result.scalar_one_or_none()

    authenticated = False
    supabase_enabled = is_supabase_configured()

    if supabase_enabled and user is not None and user.supabase_uid:
        # Supabase-provisioned account: hosted auth is authoritative. A clean
        # rejection returns None (401 below); an outage falls back to the local
        # hash so migrated users are not locked out by a Supabase blip.
        try:
            sb_response = await sign_in_with_password(data.email, data.password)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("supabase_auth_unavailable", error_type=type(exc).__name__)
            sb_response = None
            if user.password_hash is not None:
                authenticated = verify_password(data.password, user.password_hash)
        else:
            authenticated = sb_response is not None
    elif user is not None and user.password_hash is not None:
        # Not yet provisioned in Supabase (or Supabase not configured): local
        # bcrypt. On success with Supabase configured, migrate seamlessly by
        # provisioning the hosted account with the password just verified.
        authenticated = verify_password(data.password, user.password_hash)
        if authenticated and supabase_enabled and not user.supabase_uid:
            try:
                sb_user = admin_create_user(
                    user.email,
                    data.password,
                    full_name=user.full_name,
                    role=user.role,
                    tenant_id=str(user.tenant_id),
                )
                user.supabase_uid = sb_user.get("id")
                await db.commit()
                logger.info("supabase_user_migrated", user_id=str(user.id))
            except Exception as exc:
                # Migration must never break a valid login; next login retries.
                logger.warning(
                    "supabase_migration_failed",
                    user_id=str(user.id),
                    error_type=type(exc).__name__,
                )

    if not authenticated or user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return tenant, user


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: UserLogin,
    response: Response,
    db: DbDep,
) -> UserRead:
    """Authenticate a staff user and set an HTTP-only session cookie (web).

    Rate limited to 5 attempts per minute per source IP to slow credential
    stuffing. When ``tenant_slug`` is provided it takes precedence over
    Host-subdomain resolution, so login works on bare domains.
    """
    _, user = await _authenticate(request, data, db)
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    set_auth_cookie(response, token)
    return UserRead.model_validate(user)


@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def token(
    request: Request,
    data: UserLogin,
    db: DbDep,
) -> TokenResponse:
    """Authenticate and return a Bearer token for native (iOS) clients.

    Same credential and tenant checks as ``/login`` but returns the JWT in the
    body instead of a cookie. Clients send it as ``Authorization: Bearer`` and
    ``X-Tenant-ID`` on subsequent requests.
    """
    tenant, user = await _authenticate(request, data, db)
    access = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    return TokenResponse(
        access_token=access,
        tenant_slug=tenant.slug,
        user=UserRead.model_validate(user),
    )


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Clear the session cookie."""
    clear_auth_cookie(response)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserRead)
async def me(current_user: ActiveUserDep) -> UserRead:
    """Return the currently authenticated user."""
    return UserRead.model_validate(current_user)


@router.get("/tenant-status")
async def tenant_status(current_user: ActiveUserDep, db: DbDep) -> dict[str, Any]:
    """Subscription gate check for the authenticated staff user's tenant.

    This is the tenant-status half of the app-access paywall (the other half
    is :class:`app.middleware.SubscriptionPaywallMiddleware`, which returns
    402 on staff endpoints for lapsed tenants). The mobile/web app calls this
    at session load to decide between routing to the dashboard or the
    paywall.

    Beta-friendly semantics (mirrors the middleware):
    - No subscription row → legacy beta tenant, comped: access "active".
    - ``beta_comped`` in tenant settings → explicitly comped: "active".
    - Row present → live states (trialing within trial, active, past_due
      dunning grace) pass; incomplete/paused/canceled/expired-trial get
      ``access="payment_required"`` and the app shows the paywall.
    """
    from app.models import Subscription
    from app.routers.billing import is_subscription_active

    await set_tenant_in_session(db, current_user.tenant_id)
    tenant = await db.get(Tenant, current_user.tenant_id)
    subscription = await db.scalar(
        select(Subscription).where(Subscription.tenant_id == current_user.tenant_id)
    )

    settings_comped = bool(tenant.settings.get("beta_comped")) if tenant else False
    beta_comped = settings_comped or subscription is None
    access = "active" if beta_comped or is_subscription_active(subscription) else "payment_required"

    return {
        "tenant_id": str(current_user.tenant_id),
        "tenant_slug": tenant.slug if tenant else None,
        "tenant_name": tenant.name if tenant else None,
        "tenant_status": tenant.status if tenant else None,
        "subscription_status": subscription.status if subscription else None,
        "trial_ends_at": (
            subscription.trial_ends_at.isoformat()
            if subscription and subscription.trial_ends_at
            else None
        ),
        "access": access,
        "beta_comped": beta_comped,
    }


@router.post("/password-reset/request")
@limiter.limit("5/hour")
async def password_reset_request(
    request: Request,
    data: PasswordResetRequest,
    db: DbDep,
) -> dict[str, str]:
    """Issue a single-use reset token for the given email.

    Responds with the same generic message whether or not the email exists,
    so this endpoint cannot be used to enumerate accounts. When email delivery
    is not yet wired the token is logged for out-of-band delivery.
    """
    generic = {"detail": ("If an account exists for that email, a reset link has been sent.")}

    email = data.email.lower().strip()
    await bypass_rls_for_transaction(db)
    user = await db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    customer = None
    owner_type = "staff"
    owner_id = None
    tenant_id = None
    if user is not None:
        owner_id = user.id
        tenant_id = user.tenant_id
    else:
        customer = await db.scalar(select(Customer).where(Customer.email == email))
        if customer is not None:
            owner_type = "customer"
            owner_id = customer.id
            tenant_id = customer.tenant_id

    if owner_id is None or tenant_id is None:
        # Do not disclose whether the email exists.
        logger.info("password_reset_no_account", email_hash=_hash_reset_token(email))
        return generic

    # Only the newest emailed link stays valid — retire any earlier tokens.
    await _invalidate_reset_tokens(db, owner_type, owner_id)

    raw = secrets.token_urlsafe(_RESET_TOKEN_BYTES)
    record = PasswordResetToken(
        tenant_id=tenant_id,
        owner_type=owner_type,
        owner_id=owner_id,
        token_hash=_hash_reset_token(raw),
        expires_at=datetime.utcnow() + timedelta(minutes=_PASSWORD_RESET_TTL_MINUTES),
    )
    db.add(record)
    await db.commit()

    display_name: str | None = None
    if user is not None:
        display_name = user.full_name.split()[0] if user.full_name else None
    elif customer is not None:
        display_name = customer.full_name.split()[0] if customer.full_name else None

    reset_url = _build_reset_url(request, raw)
    subject, html, text = password_reset_template(name=display_name, reset_url=reset_url)
    # Transactional security mail goes out platform-branded from the no-reply
    # sender (see ``_resend_from``); it must not impersonate the tenant or
    # invite replies to the tenant's inbox.
    try:
        await send_email(
            to_email=email,
            subject=subject,
            html_body=html,
            text_body=text,
        )
        logger.info(
            "password_reset_email_sent",
            owner_type=owner_type,
            tenant_id=str(tenant_id),
            expires_at=record.expires_at.isoformat(),
        )
    except Exception as exc:
        # Delivery failures must not leak account existence, and the token
        # is already committed so ops can hand-deliver from the log if the
        # email transport is down.
        logger.error(
            "password_reset_email_failed",
            email_event="password_reset",
            template="password_reset",
            recipient=email,
            owner_type=owner_type,
            tenant_id=str(tenant_id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
    return generic


@router.get("/password-reset/inspect")
@limiter.limit("30/hour")
async def password_reset_inspect(
    request: Request,
    db: DbDep,
    token: str = Query(min_length=32, max_length=128),
) -> dict[str, str]:
    """Return the account email for a valid reset token.

    The landing-site reset page calls this on load so the user can see whose
    password they are resetting before choosing a new one. Reading the token
    does **not** consume it — only ``/password-reset/confirm`` does.
    """
    await bypass_rls_for_transaction(db)
    record = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_reset_token(token))
    )
    if record is None or record.used_at is not None or record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
        )

    email: str | None = None
    if record.owner_type == "staff":
        owner = await db.get(User, record.owner_id)
        email = owner.email if owner is not None else None
    else:
        owner_customer = await db.get(Customer, record.owner_id)
        email = owner_customer.email if owner_customer is not None else None
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
        )
    return {"email": email, "expires_at": record.expires_at.isoformat()}


@router.post("/password-reset/confirm")
@limiter.limit("10/hour")
async def password_reset_confirm(
    request: Request,
    data: PasswordResetConfirm,
    db: DbDep,
) -> dict[str, str]:
    """Set a new password using the token issued by ``/password-reset/request``."""
    await bypass_rls_for_transaction(db)
    token_hash = _hash_reset_token(data.token)
    record = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if record is None or record.used_at is not None or record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
        )

    new_hash = get_password_hash(data.new_password)
    if record.owner_type == "staff":
        user = await db.get(User, record.owner_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account missing")
        user.password_hash = new_hash
        if user.supabase_uid and is_supabase_configured():
            try:
                admin_update_password(user.supabase_uid, data.new_password)
            except Exception as exc:
                # Keep the account consistent: if the hosted update failed,
                # drop the link so login stays on bcrypt with the fresh hash
                # (the next successful login re-migrates with it).
                logger.warning(
                    "supabase_password_sync_failed",
                    user_id=str(user.id),
                    error_type=type(exc).__name__,
                )
                user.supabase_uid = None
    else:
        customer = await db.get(Customer, record.owner_id)
        if customer is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account missing")
        customer.password_hash = new_hash

    record.used_at = datetime.utcnow()
    # Defence in depth: retire any other outstanding tokens for the account.
    await _invalidate_reset_tokens(db, record.owner_type, record.owner_id)
    await db.commit()
    logger.info(
        "password_reset_completed",
        owner_type=record.owner_type,
        tenant_id=str(record.tenant_id),
    )
    return {"detail": "Password updated"}
