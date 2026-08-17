"""Progressive business onboarding endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
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
