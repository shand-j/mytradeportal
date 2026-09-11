"""Tenant management endpoints."""

from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from mtp_shared import get_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import Actions, write_audit_log
from app.database import get_db
from app.dependencies import ActiveUserDep, TenantDep
from app.models import Tenant, User
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.schemas import TenantBootstrapRead, TenantCreate, TenantRead, TenantUpdate, UserRead
from app.security import get_password_hash
from app.supabase import admin_create_user, is_supabase_configured
from app.utils.tenant_code import generate_unique_tenant_code

router = APIRouter(prefix="/tenants", tags=["Tenants"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
_settings = get_settings()


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
    existing = await db.execute(select(Tenant).where(Tenant.slug == data.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant slug already exists",
        )

    # One account per staff email: onboarding retries used to mint a fresh
    # tenant per attempt (random slug), stacking duplicate businesses for the
    # same person. The app guides the user to log in + resume instead.
    if data.admin_email:
        await bypass_rls_for_transaction(db)
        existing_user = await db.scalar(select(User).where(User.email == data.admin_email))
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

    tenant_code = await generate_unique_tenant_code(db)
    tenant = Tenant(slug=data.slug, code=tenant_code, name=data.name)
    tenant_settings: dict[str, Any] = {}
    for key, value in (
        ("phone", data.phone),
        ("address", data.address),
        ("postcode", data.postcode),
    ):
        if value:
            tenant_settings[key] = value
    if tenant_settings:
        tenant.settings = tenant_settings
    db.add(tenant)
    await db.flush()

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
