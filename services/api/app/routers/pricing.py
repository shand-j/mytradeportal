"""Pricing profile and rate-card endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import PricingProfile, PricingRate
from app.rls import set_tenant_in_session
from app.schemas import PricingProfileCreate, PricingProfileRead, PricingRateCreate, PricingRateRead

router = APIRouter(prefix="/pricing", tags=["Pricing"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _set_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    await set_tenant_in_session(db, tenant_id)


@router.post("/profiles", status_code=status.HTTP_201_CREATED, response_model=PricingProfileRead)
async def create_pricing_profile(
    data: PricingProfileCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PricingProfile:
    """Create a pricing profile (time & materials or per point)."""
    await _set_tenant(db, tenant.id)
    profile = PricingProfile(
        tenant_id=tenant.id,
        name=data.name,
        profile_type=data.profile_type,
        is_default=data.is_default,
        vat_rate=data.vat_rate,
        markup_percentage=data.markup_percentage,
        call_out_fee=data.call_out_fee,
        minimum_charge=data.minimum_charge,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return profile


@router.get("/profiles", response_model=list[PricingProfileRead])
async def list_pricing_profiles(
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[PricingProfile]:
    """List pricing profiles for the current tenant."""
    await _set_tenant(db, tenant.id)
    result = await db.execute(
        select(PricingProfile)
        .where(PricingProfile.tenant_id == tenant.id)
        .order_by(PricingProfile.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/profiles/{profile_id}/rates",
    status_code=status.HTTP_201_CREATED,
    response_model=PricingRateRead,
)
async def create_pricing_rate(
    profile_id: UUID,
    data: PricingRateCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PricingRate:
    """Add a rate to a pricing profile."""
    await _set_tenant(db, tenant.id)
    profile = await db.get(PricingProfile, profile_id)
    if profile is None or profile.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pricing profile not found"
        )

    rate = PricingRate(
        tenant_id=tenant.id,
        pricing_profile_id=profile_id,
        category=data.category,
        label=data.label,
        unit=data.unit,
        rate=data.rate,
        cost=data.cost,
        is_active=data.is_active,
    )
    db.add(rate)
    await db.flush()
    await db.refresh(rate)
    return rate


@router.get("/profiles/{profile_id}/rates", response_model=list[PricingRateRead])
async def list_pricing_rates(
    profile_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[PricingRate]:
    """List rates for a pricing profile."""
    await _set_tenant(db, tenant.id)
    profile = await db.get(PricingProfile, profile_id)
    if profile is None or profile.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pricing profile not found"
        )

    result = await db.execute(
        select(PricingRate)
        .where(
            PricingRate.pricing_profile_id == profile_id,
            PricingRate.tenant_id == tenant.id,
        )
        .order_by(PricingRate.created_at.desc())
    )
    return list(result.scalars().all())
