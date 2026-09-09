"""Progressive business onboarding endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import BusinessService
from app.rls import set_tenant_in_session
from app.schemas import OnboardingStatusRead, OnboardingStepUpdate

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _set_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    await set_tenant_in_session(db, tenant_id)


@router.get("/status", response_model=OnboardingStatusRead)
async def get_onboarding_status(
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> OnboardingStatusRead:
    """Return the current onboarding state for the tenant."""
    await _set_tenant(db, tenant.id)

    progress: dict[str, Any] = tenant.onboarding_progress or {}

    # Launch gate: business identity, compliance, services.
    required_steps = ["business_identity", "compliance", "services"]
    completed_steps = [s for s in required_steps if progress.get(s, {}).get("completed") is True]
    pending_steps = [s for s in required_steps if s not in completed_steps]

    launch_enabled = tenant.status == "active" or (
        len(pending_steps) == 0 and tenant.status in {"onboarding", "provisional"}
    )

    return OnboardingStatusRead(
        status=tenant.status,
        onboarding_progress=progress,
        launch_enabled=launch_enabled,
        pending_steps=pending_steps,
    )


async def _sync_business_services(db: AsyncSession, tenant_id: UUID, value: dict[str, Any]) -> None:
    """Persist the services selected during onboarding as BusinessService rows.

    These rows power the customer quote-request category list and can later be
    enriched with pricing profiles per service.
    """
    services = value.get("services") or []
    if not isinstance(services, list):
        return

    existing = {
        row.category: row
        for row in (
            await db.scalars(select(BusinessService).where(BusinessService.tenant_id == tenant_id))
        ).all()
    }

    selected = set(services)
    for category in selected:
        if category in existing:
            existing[category].is_active = True
            existing[category].is_launch_enabled = True
        else:
            db.add(
                BusinessService(
                    tenant_id=tenant_id,
                    category=category,
                    is_active=True,
                    is_launch_enabled=True,
                )
            )

    for category, row in existing.items():
        if category not in selected:
            row.is_active = False
            row.is_launch_enabled = False


@router.patch("/step/{step_name}", response_model=OnboardingStatusRead)
async def update_onboarding_step(
    step_name: str,
    data: OnboardingStepUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> OnboardingStatusRead:
    """Update a single onboarding step and recalculate launch eligibility."""
    await _set_tenant(db, tenant.id)

    # Copy the JSONB dict so the reassignment below is a genuinely new object.
    # Mutating the existing dict in place is not tracked by SQLAlchemy, which
    # would silently drop every step after the first.
    progress: dict[str, Any] = dict(tenant.onboarding_progress or {})
    progress[step_name] = {"completed": True, "value": data.value}

    if step_name == "services":
        await _sync_business_services(db, tenant.id, data.value)

    # Workload metrics captured during onboarding (e.g. in the business
    # identity step) are persisted into tenant.settings verbatim; the
    # time-saved metric is computed client-side from them later.
    metrics = {
        key: int(data.value[key])
        for key in ("quotes_per_week", "avg_minutes_per_quote")
        if isinstance(data.value.get(key), int) and not isinstance(data.value.get(key), bool)
    }
    if metrics:
        tenant.settings = {**(tenant.settings or {}), **metrics}

    if step_name == "branding":
        # Branding captured in onboarding must land in tenant.settings — that
        # is what Tenant.primary_color and the white-label public config read.
        colour = data.value.get("primary_color")
        if isinstance(colour, str) and colour:
            tenant.settings = {**(tenant.settings or {}), "primary_color": colour}

    if step_name == "tax":
        # VAT answers drive quote/invoice VAT rates (calculations.tenant_vat_rate).
        if "vat_registered" in data.value:
            tenant.vat_registered = bool(data.value["vat_registered"])
        if data.value.get("vat_number"):
            tenant.vat_number = str(data.value["vat_number"])[:12]
        if data.value.get("vat_scheme"):
            tenant.vat_scheme = str(data.value["vat_scheme"])[:50]

    if step_name == "compliance":
        # CPS scheme + membership also land on tenant.settings so they are
        # visible beyond the onboarding_progress blob (admin, profile, quotes).
        compliance_settings = {
            key: data.value[key]
            for key in ("scheme", "membership", "cps_status")
            if data.value.get(key)
        }
        if compliance_settings:
            tenant.settings = {**(tenant.settings or {}), **compliance_settings}

    required_steps = ["business_identity", "compliance", "services"]
    completed_steps = [s for s in required_steps if progress.get(s, {}).get("completed") is True]
    pending_steps = [s for s in required_steps if s not in completed_steps]

    if pending_steps:
        tenant.status = "onboarding"
    elif tenant.status in {"onboarding", "provisional"}:
        tenant.status = "active"
        from datetime import datetime

        tenant.launched_at = datetime.utcnow()

    tenant.onboarding_progress = progress
    await db.flush()
    return await get_onboarding_status(tenant, current_user, db)


@router.post("/launch", status_code=status.HTTP_200_OK, response_model=OnboardingStatusRead)
async def launch_business(
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> OnboardingStatusRead:
    """Mark the business as active once launch-gate steps are complete."""
    await _set_tenant(db, tenant.id)

    progress: dict[str, Any] = tenant.onboarding_progress or {}
    required_steps = ["business_identity", "compliance", "services"]
    completed_steps = [s for s in required_steps if progress.get(s, {}).get("completed") is True]
    pending_steps = [s for s in required_steps if s not in completed_steps]

    if pending_steps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot launch; pending steps: {', '.join(pending_steps)}",
        )

    from datetime import datetime

    tenant.status = "active"
    tenant.launched_at = datetime.utcnow()
    await db.flush()
    return await get_onboarding_status(tenant, current_user, db)
