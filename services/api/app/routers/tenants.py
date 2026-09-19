"""Tenant management endpoints."""

from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, UploadFile, status
from mtp_shared import get_settings
from pydantic import EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import Actions, write_audit_log
from app.database import get_db
from app.dependencies import ActiveUserDep, TenantDep
from app.limiter import limiter
from app.models import Subscription, Tenant, User
from app.plans import DEFAULT_PLAN_KEY, TRIAL_DAYS
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.schemas import (
    EmailAvailabilityRead,
    TenantBootstrapRead,
    TenantCreate,
    TenantRead,
    TenantUpdate,
    UserRead,
)
from app.security import get_password_hash
from app.supabase import admin_create_user, is_supabase_configured
from app.utils.tenant_code import generate_unique_tenant_code

logger = structlog.get_logger("api.tenants")
router = APIRouter(prefix="/tenants", tags=["Tenants"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
_settings = get_settings()

# Slugs that can never be tenant subdomains on the portal base domain —
# they are platform-owned surfaces (api, app, auth, ...) or would confuse
# routing/branding.
RESERVED_SLUGS = frozenset(
    {
        "www",
        "api",
        "admin",
        "app",
        "mail",
        "email",
        "support",
        "help",
        "portal",
        "my",
        "status",
        "blog",
        "demo",
        "staging",
        "auth",
        "billing",
        "pay",
    }
)


def _require_setup_token(provided: str | None) -> None:
    """Reject tenant-creation requests that do not carry the setup token.

    In production the ``SETUP_TOKEN`` env var MUST be configured and the
    caller MUST send a matching ``X-Setup-Token`` header. In development the
    endpoint stays open so seed scripts and local bootstrap continue to work,
    but it logs a warning if no token is provided.
    """
    expected = _settings.setup_token
    if _settings.environment == "production":
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tenant creation is disabled: SETUP_TOKEN not configured",
            )
        if not provided or provided != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid setup token",
            )
        return
    # Non-production: if a token is configured, still require it; otherwise allow.
    if expected and (not provided or provided != expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid setup token",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    db: DbDep,
    x_setup_token: Annotated[str | None, Header(alias="X-Setup-Token")] = None,
) -> TenantBootstrapRead:
    """Create a new tenant (electrical business).

    Requires the ``X-Setup-Token`` header in production. This endpoint is
    intended for bootstrap and the super-admin onboarding flow only.

    When ``admin_email``/``admin_password``/``admin_name`` are provided, the
    tenant's first admin user is created atomically in the same transaction
    so a fresh tenant is immediately able to log in.
    """
    _require_setup_token(x_setup_token)
    if data.slug.lower() in RESERVED_SLUGS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{data.slug}' is reserved and cannot be used for a business",
        )
    existing = await db.execute(select(Tenant).where(Tenant.slug == data.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant slug already exists",
        )

    # One account per staff email: onboarding retries used to mint a fresh
    # tenant per attempt (random slug), stacking duplicate businesses for the
    # same person. The app guides the user to log in + resume instead.
    # Case-insensitive: the same person typing their email with different
    # casing must hit the same guard (and the same account on login).
    if data.admin_email:
        await bypass_rls_for_transaction(db)
        existing_user = await db.scalar(
            select(User).where(func.lower(User.email) == str(data.admin_email).lower())
        )
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

    tenant_code = await generate_unique_tenant_code(db)
    tenant = Tenant(slug=data.slug, code=tenant_code, name=data.name)
    # The public-config "Email us" chip and quote/invoice Reply-To read
    # settings.email; without this default no client ever populated it
    # (issue #143). The onboarding "Work email" doubles as the business
    # contact email until the tenant sets a different one in Settings.
    contact_email = data.email or data.admin_email
    tenant_settings: dict[str, Any] = {}
    for key, value in (
        ("phone", data.phone),
        ("address", data.address),
        ("postcode", data.postcode),
        ("email", str(contact_email) if contact_email else None),
    ):
        if value:
            tenant_settings[key] = value
    if tenant_settings:
        tenant.settings = tenant_settings
    db.add(tenant)
    await db.flush()

    # No-card trial: every new tenant starts on a full-feature trial with no
    # Paddle interaction. When the tenant later completes Paddle checkout,
    # ``_get_or_create_subscription`` (checkout) and ``_upsert_subscription``
    # (webhook) both key on tenant_id and update THIS row in place — plan_key
    # is corrected to the chosen plan at checkout time. ``subscriptions`` is
    # not RLS-scoped, so no tenant declaration is needed for this insert.
    db.add(
        Subscription(
            tenant_id=tenant.id,
            plan_key=DEFAULT_PLAN_KEY,
            status="trialing",
            trial_ends_at=datetime.utcnow() + timedelta(days=TRIAL_DAYS),
            provider_payload={"source": "signup_trial"},
        )
    )

    admin_user: User | None = None
    if data.admin_email and data.admin_password and data.admin_name:
        # The users table is tenant-scoped under RLS; declare which tenant
        # this session operates on before inserting the first user.
        await set_tenant_in_session(db, tenant.id)

        password_hash: str | None = None
        supabase_uid: str | None = None
        if is_supabase_configured():
            try:
                sb_user = admin_create_user(
                    data.admin_email,
                    data.admin_password,
                    full_name=data.admin_name,
                    role="admin",
                    tenant_id=str(tenant.id),
                )
            except httpx.HTTPError as exc:
                # Network-level failure talking to Supabase Auth.
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication provider is unavailable; please try again shortly",
                ) from exc
            except RuntimeError as exc:
                # Supabase rejected the signup (e.g. password policy, malformed
                # payload). Without this guard the exception surfaced as a bare
                # 500 during onboarding plan selection.
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Could not create the login account with the authentication provider",
                ) from exc
            supabase_uid = sb_user.get("id")
        else:
            password_hash = get_password_hash(data.admin_password)

        admin_user = User(
            tenant_id=tenant.id,
            email=data.admin_email,
            full_name=data.admin_name,
            role="admin",
            password_hash=password_hash,
            supabase_uid=supabase_uid,
            is_active=True,
        )
        db.add(admin_user)
        await db.flush()

    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=admin_user,
        action=Actions.TENANT_CREATED,
        entity_type="tenant",
        entity_id=tenant.id,
        payload={
            "slug": tenant.slug,
            "admin_email": admin_user.email if admin_user is not None else None,
        },
    )
    await db.commit()
    await db.refresh(tenant)
    result = TenantBootstrapRead.model_validate(tenant)
    if admin_user is not None:
        result.admin_user = UserRead.model_validate(admin_user)
    return result


@router.get("/email-availability")
@limiter.limit("10/minute")
async def check_email_availability(
    request: Request,
    db: DbDep,
    email: Annotated[EmailStr, Query()],
    x_setup_token: Annotated[str | None, Header(alias="X-Setup-Token")] = None,
) -> EmailAvailabilityRead:
    """Pre-flight check so onboarding's email step can flag a duplicate account
    immediately instead of failing at the final registration step.

    Carries the same setup-token guard as tenant creation so the endpoint is
    not an open account-enumeration oracle, and is rate limited per source IP.
    The lookup is case-insensitive, matching the login and tenant-creation
    guards.
    """
    _require_setup_token(x_setup_token)
    await bypass_rls_for_transaction(db)
    existing_user = await db.scalar(
        select(User).where(func.lower(User.email) == str(email).lower())
    )
    return EmailAvailabilityRead(email=str(email), available=existing_user is None)


@router.get("/me")
async def get_current_tenant(tenant: TenantDep) -> TenantRead:
    """Return the tenant identified by the X-Tenant-ID header."""
    return TenantRead.model_validate(tenant)


@router.patch("/me")
async def update_current_tenant(
    data: TenantUpdate,
    tenant: TenantDep,
    current_user: ActiveUserDep,
    db: DbDep,
) -> TenantRead:
    """Update the current tenant's name and settings (user must belong to tenant)."""
    if current_user.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this tenant",
        )

    update_data = data.model_dump(exclude_unset=True, by_alias=False)

    # Flatten top-level settings fields into the JSONB settings dict.
    settings_fields = {
        "email",
        "phone",
        "website",
        "address",
        "postcode",
        "logo_url",
        "primary_color",
        "secondary_color",
        "hourly_labour_rate",
        "daily_labour_rate",
        "mate_daily_rate",
        "mate_percent",
        "markup_percentage",
        "min_margin_percent",
        "price_tolerance_percent",
        "minimum_charge",
        "vat_rate",
        "plan_tier",
        "google_place_id",
        "review_url",
        "quotes_per_week",
        "avg_minutes_per_quote",
    }
    settings_update: dict[str, object] = {}
    for key in settings_fields:
        if key in update_data:
            settings_update[key] = update_data.pop(key)
    if update_data.get("settings"):
        settings_update = {**update_data.pop("settings"), **settings_update}

    if settings_update:
        tenant.settings = {**tenant.settings, **settings_update}

    if "name" in update_data:
        tenant.name = update_data.pop("name")

    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.TENANT_UPDATED,
        entity_type="tenant",
        entity_id=tenant.id,
        payload={"changed_fields": sorted(set(data.model_dump(exclude_unset=True).keys()))},
    )
    await db.commit()
    await db.refresh(tenant)
    return TenantRead.model_validate(tenant)


# Tenant logo constraints. Logos render on public portal/landing pages via
# GET /businesses/{slug}/logo, so they are small images only — 2 MB is
# generous for a logo and keeps the public route cheap to serve.
_LOGO_MAX_BYTES = 2 * 1024 * 1024
_LOGO_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _logo_public_url(request: Request, slug: str) -> str:
    """Absolute URL of the public logo route, for embedding in settings.

    Portal/landing pages and the app render ``logo_url`` as an ``<img>`` src
    from origins other than the API's, so a relative path would not resolve.
    ``PUBLIC_API_BASE_URL`` overrides; otherwise the request origin (the API's
    own host, via proxy headers) is correct — the logo is served by this
    service.
    """
    from app.config import PUBLIC_API_BASE_URL

    base = (PUBLIC_API_BASE_URL or str(request.base_url)).rstrip("/")
    return f"{base}/businesses/{slug}/logo"


def _store_logo(tenant_id: UUID, content_type: str, content: bytes) -> str:
    """Store logo bytes in MinIO under the tenant's ``branding/`` prefix."""
    from app.config import settings
    from app.routers.files import _ensure_bucket, s3_client

    key = f"tenants/{tenant_id}/branding/logo-{uuid4()}{_LOGO_CONTENT_TYPES[content_type]}"
    client = s3_client()
    _ensure_bucket(client)
    client.put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return key


def _delete_stored_logo(tenant: Tenant) -> None:
    """Best-effort delete of the tenant's current logo object from MinIO."""
    from app.config import settings
    from app.routers.files import s3_client

    key = (tenant.settings or {}).get("logo_key")
    if not isinstance(key, str) or not key:
        return
    try:
        s3_client().delete_object(Bucket=settings.minio_bucket, Key=key)
    except Exception as exc:  # orphaned object is harmless; never block
        logger.warning(
            "logo_delete_failed",
            tenant_id=str(tenant.id),
            error_type=type(exc).__name__,
        )


@router.post("/me/logo")
async def upload_current_tenant_logo(
    file: UploadFile,
    request: Request,
    tenant: TenantDep,
    current_user: ActiveUserDep,
    db: DbDep,
) -> TenantRead:
    """Upload the tenant's business logo (staff, multipart).

    Validates type (png/jpeg/webp) and size (≤2 MB), stores the object in
    MinIO under ``tenants/{id}/branding/`` and points ``settings.logo_url``
    at the unauthenticated ``GET /businesses/{slug}/logo`` route so the logo
    renders on public portal/landing pages. Replaces any existing logo.
    """
    if current_user.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this tenant",
        )

    content_type = (file.content_type or "").lower()
    if content_type not in _LOGO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only png, jpeg or webp images are accepted",
        )
    content = await file.read()
    if len(content) > _LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Logo must be 2 MB or smaller",
        )
    try:
        key = _store_logo(tenant.id, content_type, content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not store file: {exc}",
        ) from exc

    _delete_stored_logo(tenant)
    tenant.settings = {
        **(tenant.settings or {}),
        "logo_key": key,
        "logo_url": _logo_public_url(request, tenant.slug),
    }
    await db.commit()
    await db.refresh(tenant)
    return TenantRead.model_validate(tenant)


@router.delete("/me/logo")
async def delete_current_tenant_logo(
    tenant: TenantDep,
    current_user: ActiveUserDep,
    db: DbDep,
) -> TenantRead:
    """Remove the tenant's logo (staff): clears the branding settings."""
    if current_user.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this tenant",
        )
    _delete_stored_logo(tenant)
    settings = {**(tenant.settings or {})}
    settings.pop("logo_key", None)
    settings.pop("logo_url", None)
    tenant.settings = settings
    await db.commit()
    await db.refresh(tenant)
    return TenantRead.model_validate(tenant)


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: UUID,
    current_user: ActiveUserDep,
    db: DbDep,
) -> TenantRead:
    """Get a tenant by ID.

    Authenticated users can only read their own tenant. Cross-tenant reads
    are denied with 403 to avoid leaking tenant metadata via enumeration.
    """
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot read another tenant",
        )
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantRead.model_validate(tenant)
