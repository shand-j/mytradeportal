"""Public business lookup for the iOS app white-label entry flow."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BusinessService, Tenant
from app.rls import bypass_rls_in_session
from app.schemas import BusinessPublicConfig

router = APIRouter(prefix="/businesses", tags=["Businesses"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{slug}/public-config", response_model=BusinessPublicConfig)
async def get_public_config(slug: str, db: DbDep) -> BusinessPublicConfig:
    """Return the public white-label config for a business (no auth required).

    This is called by the iOS app before the customer or tradesperson has
    logged in, so it intentionally bypasses RLS.
    """
    await bypass_rls_in_session(db)

    tenant = await db.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True)))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )

    service_rows = await db.scalars(
        select(BusinessService.category).where(
            BusinessService.tenant_id == tenant.id,
            BusinessService.is_active.is_(True),
            BusinessService.is_launch_enabled.is_(True),
        )
    )
    categories = list(service_rows.all())

    return BusinessPublicConfig(
        slug=tenant.slug,
        name=tenant.name,
        logo_url=tenant.logo_url,
        primary_color=tenant.primary_color,
        secondary_color=tenant.secondary_color,
        business_services=categories,
        contact_phone=tenant.phone or None,
        address=tenant.address or None,
    )
