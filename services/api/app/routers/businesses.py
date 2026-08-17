"""Public business lookup and quote-request submission for the iOS app.

These endpoints are called by the white-label app before the customer or
tradesperson has authenticated, so they identify the target business by slug
and do not require an auth token.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.models import BusinessService, Contact, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.schemas import (
    BusinessPublicConfig,
    PublicQuoteRequestAck,
    PublicQuoteRequestCreate,
)

router = APIRouter(prefix="/businesses", tags=["Businesses"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _resolve_active_tenant(db: AsyncSession, slug: str) -> Tenant:
    """Resolve an active tenant by slug. ``tenants`` is a global (non-RLS) table."""
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True)))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    return tenant


@router.get("/{slug}/public-config", response_model=BusinessPublicConfig)
async def get_public_config(slug: str, db: DbDep) -> BusinessPublicConfig:
    """Return the public white-label config for a business (no auth required).

    This is called by the iOS app before the customer or tradesperson has
    logged in, so it intentionally bypasses RLS.
    """
    await bypass_rls_in_session(db)

    tenant = await _resolve_active_tenant(db, slug)

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


@router.post(
    "/{slug}/quote-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=PublicQuoteRequestAck,
)
@limiter.limit("10/minute")
async def submit_public_quote_request(
    slug: str,
    data: PublicQuoteRequestCreate,
    request: Request,
    db: DbDep,
) -> PublicQuoteRequestAck:
    """Create a quote request from a homeowner via the white-label app.

    Unauthenticated: the target business is identified by ``slug``. A CRM
    contact is created (or reused by email) and linked to the new request so it
    shows up as a lead in the tradesperson's dashboard.
    """
    tenant = await _resolve_active_tenant(db, slug)
    # Insert tenant-scoped rows under this tenant's RLS context.
    await set_tenant_in_session(db, tenant.id)

    contact: Contact | None = None
    if data.contact.email:
        contact = await db.scalar(
            select(Contact).where(
                Contact.tenant_id == tenant.id,
                Contact.email == str(data.contact.email),
            )
        )
    if contact is None:
        contact = Contact(
            tenant_id=tenant.id,
            name=data.contact.name,
            email=str(data.contact.email) if data.contact.email else None,
            phone=data.contact.phone,
            postcode=data.contact.postcode,
        )
        db.add(contact)
        await db.flush()

    structured_data = {
        **data.structured_data,
        "category": data.category,
        "title": data.title,
        "marketing_consent": data.marketing_consent,
    }

    quote_request = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        source="app",
        raw_text=data.raw_text,
        structured_data=structured_data,
        urgency=data.urgency,
        media_urls=data.media_urls,
        preferred_dates=data.preferred_dates,
        safety_review_required=data.safety_review_required,
    )
    db.add(quote_request)
    await db.flush()
    await db.refresh(quote_request)

    return PublicQuoteRequestAck(
        id=quote_request.id,
        status=quote_request.status,
        reference=str(quote_request.id)[:8].upper(),
    )
