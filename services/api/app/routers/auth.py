"""Authentication endpoints for the back-office UI and native clients."""

import hashlib
import secrets
from datetime import datetime, timedelta

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

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
from app.rls import bypass_rls_in_session, set_tenant_in_session
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
from app.supabase import is_supabase_configured, sign_in_with_password

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
    user_result = await db.execute(select(User).where(User.email == data.email))
    user = user_result.scalar_one_or_none()
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
    supabase_unreachable = False
    if supabase_enabled:
        try:
            sb_response = await sign_in_with_password(data.email, data.password)
        except (httpx.HTTPError, OSError) as exc:
            # Supabase outage must not 500 the login. Fall back to local bcrypt
            # for users that have a password hash. Bad credentials still 401:
            # a clean Supabase rejection returns None, not an exception.
            logger.warning("supabase_auth_unavailable", error_type=type(exc).__name__)
            sb_response = None
            supabase_unreachable = True
        if sb_response is not None:
            sb_user = sb_response.get("user", {})
            sb_uid = sb_user.get("id")
            # Prefer matching by Supabase UID; fall back to email+tenant.
            if user is None and sb_uid:
                user_result = await db.execute(
                    select(User).where(User.supabase_uid == sb_uid, User.tenant_id == tenant.id)
                )
                user = user_result.scalar_one_or_none()
            authenticated = True

    # Local bcrypt auth is used when Supabase auth is disabled, or when it is
    # unreachable and the user has a local password hash to fall back to.
    if (
        (not supabase_enabled or supabase_unreachable)
        and not authenticated
        and user is not None
        and user.password_hash is not None
    ):
        authenticated = verify_password(data.password, user.password_hash)

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
    await bypass_rls_in_session(db)
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

    from app.config import settings as _settings

    app_origin = (
        _settings.app_public_url.rstrip("/")
        if _settings.app_public_url
        else str(request.base_url).rstrip("/")
    )
    reset_url = f"{app_origin}/reset-password?token={raw}"
    subject, html, text = password_reset_template(name=display_name, reset_url=reset_url)
    tenant_row = await db.get(Tenant, tenant_id)
    from_name = tenant_row.name if tenant_row is not None else None
    reply_to = tenant_row.email if tenant_row is not None and tenant_row.email else None
    try:
        await send_email(
            to_email=email,
            subject=subject,
            html_body=html,
            text_body=text,
            from_name=from_name,
            reply_to=reply_to,
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
            owner_type=owner_type,
            tenant_id=str(tenant_id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
    return generic


@router.post("/password-reset/confirm")
@limiter.limit("10/hour")
async def password_reset_confirm(
    request: Request,
    data: PasswordResetConfirm,
    db: DbDep,
) -> dict[str, str]:
    """Set a new password using the token issued by ``/password-reset/request``."""
    await bypass_rls_in_session(db)
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
    else:
        customer = await db.get(Customer, record.owner_id)
        if customer is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account missing")
        customer.password_hash = new_hash

    record.used_at = datetime.utcnow()
    await db.commit()
    logger.info(
        "password_reset_completed",
        owner_type=record.owner_type,
        tenant_id=str(record.tenant_id),
    )
    return {"detail": "Password updated"}
