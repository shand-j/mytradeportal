"""Public business lookup and quote-request submission for the iOS app.

These endpoints are called by the white-label app before the customer or
tradesperson has authenticated, so they identify the target business by slug
and do not require an auth token.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import _extract_token
from app.limiter import limiter
from app.models import BusinessService, Contact, Customer, QuoteRequest, Tenant
from app.quote_automation import auto_draft_quote_for_request
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.schemas import (
    BusinessPublicConfig,
    PublicQuoteRequestAck,
    PublicQuoteRequestCreate,
)
from app.security import decode_access_token

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


async def _resolve_active_tenant_by_code(db: AsyncSession, code: str) -> Tenant:
    """Resolve an active tenant by its 6-digit customer lookup code."""
    tenant = await db.scalar(select(Tenant).where(Tenant.code == code, Tenant.is_active.is_(True)))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    return tenant


@router.get("/by-code/{code}/public-config", response_model=BusinessPublicConfig)
async def get_public_config_by_code(code: str, db: DbDep) -> BusinessPublicConfig:
    """Return the public white-label config for a business by 6-digit code.

    Called from the generic marketplace entry screen when a homeowner types in
    the electrician's code instead of using a white-label build.
    """
    await bypass_rls_for_transaction(db)
    tenant = await _resolve_active_tenant_by_code(db, code)
    return await _build_public_config(db, tenant)


async def _build_public_config(db: AsyncSession, tenant: Tenant) -> BusinessPublicConfig:
    """Build the white-label public config for a resolved tenant."""
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
        code=tenant.code,
        name=tenant.name,
        logo_url=tenant.logo_url,
        primary_color=tenant.primary_color,
        secondary_color=tenant.secondary_color,
        business_services=categories,
        contact_phone=tenant.phone or None,
        address=tenant.address or None,
    )


@router.get("/{slug}/public-config", response_model=BusinessPublicConfig)
async def get_public_config(slug: str, db: DbDep) -> BusinessPublicConfig:
    """Return the public white-label config for a business (no auth required).

    This is called by the iOS app before the customer or tradesperson has
    logged in, so it intentionally bypasses RLS.
    """
    await bypass_rls_for_transaction(db)
    tenant = await _resolve_active_tenant(db, slug)
    return await _build_public_config(db, tenant)


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
    background_tasks: BackgroundTasks,
    db: DbDep,
) -> PublicQuoteRequestAck:
    """Create a quote request from a homeowner via the white-label app.

    Unauthenticated: the target business is identified by ``slug``. A CRM
    contact is created (or reused by email) and linked to the new request so it
    shows up as a lead in the tradesperson's dashboard. An AI draft quote is
    generated in the background — the 201 ack never waits on the LLM.
    """
    tenant = await _resolve_active_tenant(db, slug)
    # Insert tenant-scoped rows under this tenant's RLS context.
    await set_tenant_in_session(db, tenant.id)

    # If the homeowner is logged in (customer token for this tenant), link the
    # request to their account so it appears in their history, and reuse their
    # contact record.
    customer: Customer | None = None
    token = _extract_token(request)
    if token:
        claims = decode_access_token(token)
        if claims is not None and claims.get("subject_type") == "customer":
            try:
                token_customer_id = UUID(str(claims.get("sub")))
                token_tenant_id = UUID(str(claims.get("tenant_id")))
            except (ValueError, TypeError):
                token_customer_id = token_tenant_id = None  # type: ignore[assignment]
            if token_customer_id is not None and token_tenant_id == tenant.id:
                candidate = await db.get(Customer, token_customer_id)
                if candidate is not None and candidate.tenant_id == tenant.id:
                    customer = candidate

    contact: Contact | None = None
    if customer is not None and customer.contact_id:
        contact = await db.get(Contact, customer.contact_id)
    if contact is None and data.contact.email:
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
    else:
        # Reused contact: refresh details the homeowner just re-entered.
        if data.contact.phone:
            contact.phone = data.contact.phone
        if data.contact.postcode:
            contact.postcode = data.contact.postcode
        if data.contact.name:
            contact.name = data.contact.name

    # Logged-in customer: keep their account details current so repeat quote
    # requests pre-fill (postcode/phone + property profile).
    if customer is not None:
        if data.contact.postcode:
            customer.postcode = data.contact.postcode
        if data.contact.phone:
            customer.phone = data.contact.phone
        prop = (data.structured_data or {}).get("property")
        if isinstance(prop, dict) and prop:
            customer.property_profile = prop

    structured_data = {
        **data.structured_data,
        "category": data.category,
        "title": data.title,
        "marketing_consent": data.marketing_consent,
    }

    quote_request = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        customer_id=customer.id if customer is not None else None,
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
    # Commit before scheduling the background auto-draft: background tasks run
    # before the get_db dependency cleanup commits, and the worker opens its
    # own session, so the new rows must already be durable.
    await db.commit()
    await db.refresh(quote_request)

    # Kick off AI quote generation in the background. Failures are logged by
    # the worker and never affect this ack.
    background_tasks.add_task(auto_draft_quote_for_request, tenant.id, quote_request.id)

    return PublicQuoteRequestAck(
        id=quote_request.id,
        status=quote_request.status,
        reference=str(quote_request.id)[:8].upper(),
    )
