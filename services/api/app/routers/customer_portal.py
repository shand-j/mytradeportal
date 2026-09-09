"""Homeowner (customer) portal: self-registration, login and quote history.

These endpoints back the customer side of the white-label app. A customer
belongs to one business (tenant), identified by slug at register/login time.
Auth is a bearer token with ``subject_type="customer"`` so it can never be used
against the staff API.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import CurrentCustomerDep
from app.limiter import limiter
from app.models import (
    Appointment,
    BillOfQuantities,
    Contact,
    Customer,
    MediaAsset,
    Quote,
    QuoteRequest,
    Tenant,
)
from app.push import notify_staff
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.schemas import (
    AppointmentCreate,
    AppointmentRead,
    CustomerLogin,
    CustomerRead,
    CustomerRegister,
    CustomerTokenResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    QuoteRead,
    QuoteRequestMediaCreate,
    QuoteRequestRead,
)
from app.security import create_access_token, get_password_hash, verify_password

router = APIRouter(prefix="/customer", tags=["Customer Portal"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = structlog.get_logger("api.customer_portal")


def _phone_digits(value: str | None) -> str:
    """Reduce a phone number to its digits so formatting differences match."""
    return "".join(ch for ch in (value or "") if ch.isdigit())


async def _link_quote_requests_by_contact(db: AsyncSession, customer: Customer) -> int:
    """Link unclaimed quote requests whose contact matches this customer.

    Matches within the tenant on the linked CRM contact's email
    (case-insensitive) or phone (digits-only), so leads and quotes the
    electrician captured manually become visible in the customer portal once
    the homeowner registers or logs in with the same details. Only requests
    with ``customer_id IS NULL`` are claimed. Returns the number linked.
    """
    conditions = []
    if customer.email:
        conditions.append(func.lower(Contact.email) == customer.email.lower())
    digits = _phone_digits(customer.phone)
    if digits:
        conditions.append(
            func.regexp_replace(func.coalesce(Contact.phone, ""), r"\D", "", "g") == digits
        )
    if not conditions:
        return 0

    # Never poach a request whose contact email is registered to a different
    # customer account — it belongs to that account even if the phone matches
    # (e.g. a retried registration with a new email but the same phone).
    email_owned_by_another_customer = (
        select(Customer.id)
        .where(
            Customer.tenant_id == customer.tenant_id,
            Customer.id != customer.id,
            func.lower(Customer.email) == func.lower(Contact.email),
        )
        .exists()
    )

    result = await db.execute(
        select(QuoteRequest)
        .join(Contact, QuoteRequest.contact_id == Contact.id)
        .where(
            QuoteRequest.tenant_id == customer.tenant_id,
            QuoteRequest.customer_id.is_(None),
            or_(*conditions),
            ~email_owned_by_another_customer,
        )
    )
    linked = list(result.scalars().all())
    for quote_request in linked:
        quote_request.customer_id = customer.id
    if linked:
        await db.flush()
    logger.info(
        "customer_linked_requests",
        tenant_id=str(customer.tenant_id),
        customer_id=str(customer.id),
        count=len(linked),
    )
    return len(linked)


async def _resolve_active_tenant(db: AsyncSession, slug: str) -> Tenant:
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True)))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return tenant


def _issue_token(customer: Customer) -> str:
    return create_access_token(
        user_id=customer.id,
        tenant_id=customer.tenant_id,
        role="customer",
        email=customer.email,
        subject_type="customer",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=CustomerTokenResponse)
@limiter.limit("5/minute")
async def register_customer(
    data: CustomerRegister,
    request: Request,
    db: DbDep,
) -> CustomerTokenResponse:
    """Register a homeowner against a business and return a bearer token."""
    # tenants is a global table; look it up before entering the tenant's RLS.
    await bypass_rls_for_transaction(db)
    tenant = await _resolve_active_tenant(db, data.slug)
    await set_tenant_in_session(db, tenant.id)

    existing = await db.scalar(
        select(Customer).where(Customer.tenant_id == tenant.id, Customer.email == str(data.email))
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    contact = Contact(
        tenant_id=tenant.id,
        name=data.full_name,
        email=str(data.email),
        phone=data.phone,
        address=data.address,
        postcode=data.postcode,
    )
    db.add(contact)
    await db.flush()

    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=str(data.email),
        full_name=data.full_name,
        phone=data.phone,
        address=data.address,
        postcode=data.postcode,
        password_hash=get_password_hash(data.password),
        marketing_consent=data.marketing_consent,
        preferred_contact_method=data.preferred_contact_method,
    )
    db.add(customer)
    await db.flush()

    # If the customer arrived from a quote request, link the two records so
    # their history and the in-app chat thread work immediately. Keep the
    # customer's contact pointer in sync with the request's contact.
    if data.quote_request_id is not None:
        quote_request = await db.scalar(
            select(QuoteRequest).where(
                QuoteRequest.id == data.quote_request_id,
                QuoteRequest.tenant_id == tenant.id,
            )
        )
        if quote_request is not None:
            quote_request.customer_id = customer.id
            quote_request.contact_id = contact.id
            customer.contact_id = contact.id
            # Carry the property profile forward so repeat quotes pre-fill it.
            if not customer.property_profile:
                prop = (quote_request.structured_data or {}).get("property")
                if isinstance(prop, dict) and prop:
                    customer.property_profile = prop

    # Claim any leads the electrician captured earlier with the same
    # email/phone so they show up in the customer's history immediately.
    await _link_quote_requests_by_contact(db, customer)

    await db.refresh(customer)
    await db.commit()

    return CustomerTokenResponse(
        access_token=_issue_token(customer),
        customer=CustomerRead.model_validate(customer),
    )


@router.post("/login", response_model=CustomerTokenResponse)
@limiter.limit("5/minute")
async def login_customer(
    data: CustomerLogin,
    request: Request,
    db: DbDep,
) -> CustomerTokenResponse:
    """Authenticate a homeowner and return a bearer token.

    Tenant-agnostic: customers no longer pick a business at login (a hangover
    from the per-tenant-subdomain web approach). With a slug, resolution is
    direct; without one, the account is located by email across tenants and
    the tenant is derived from it (newest account wins on duplicates).
    """
    await bypass_rls_for_transaction(db)

    if data.slug:
        tenant = await _resolve_active_tenant(db, data.slug)
        customer = await db.scalar(
            select(Customer).where(
                Customer.tenant_id == tenant.id,
                func.lower(Customer.email) == str(data.email).lower(),
            )
        )
    else:
        customer = (
            (
                await db.execute(
                    select(Customer)
                    .where(func.lower(Customer.email) == str(data.email).lower())
                    .order_by(Customer.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        resolved_tenant = await db.get(Tenant, customer.tenant_id)
        if resolved_tenant is None or not resolved_tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        tenant = resolved_tenant

    await set_tenant_in_session(db, tenant.id)
    if (
        customer is None
        or not customer.is_active
        or customer.password_hash is None
        or not verify_password(data.password, customer.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Claim any leads captured with the same email/phone since the last login.
    if await _link_quote_requests_by_contact(db, customer):
        await db.commit()

    return CustomerTokenResponse(
        access_token=_issue_token(customer),
        customer=CustomerRead.model_validate(customer),
    )


@router.get("/me", response_model=CustomerRead)
async def get_me(customer: CurrentCustomerDep) -> Customer:
    """Return the authenticated customer."""
    return customer


@router.get("/quote-requests", response_model=list[QuoteRequestRead])
async def list_my_quote_requests(
    customer: CurrentCustomerDep,
    db: DbDep,
) -> list[QuoteRequest]:
    """List the authenticated customer's quote requests (their history).

    Each response includes the linked quote (with line items) when the request
    has been converted to a quote, so the customer can view, accept or reject it.
    """
    # The customer dependency already set the tenant RLS context.
    result = await db.execute(
        select(QuoteRequest)
        .options(
            selectinload(QuoteRequest.contact),
            selectinload(QuoteRequest.quote).selectinload(Quote.line_items),
            selectinload(QuoteRequest.quote).selectinload(Quote.contact),
            selectinload(QuoteRequest.quote)
            .selectinload(Quote.bill_of_quantities)
            .selectinload(BillOfQuantities.line_items),
        )
        .where(
            QuoteRequest.tenant_id == customer.tenant_id,
            QuoteRequest.customer_id == customer.id,
        )
        .order_by(QuoteRequest.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/files/presigned-upload", response_model=PresignedUploadResponse)
async def customer_presigned_upload(
    data: PresignedUploadRequest,
    customer: CurrentCustomerDep,
) -> PresignedUploadResponse:
    """Customer-scoped presigned upload (photos on quote requests)."""
    import uuid as _uuid

    from app.config import settings
    from app.routers.files import _s3_client

    key = f"tenants/{customer.tenant_id}/{_uuid.uuid4()}/{data.filename}"
    try:
        presigned = _s3_client().generate_presigned_post(
            Bucket=settings.minio_bucket,
            Key=key,
            Fields={"Content-Type": data.content_type or "application/octet-stream"},
            Conditions=[["starts-with", "$Content-Type", ""]],
            ExpiresIn=300,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate presigned upload URL: {exc}",
        ) from exc
    return PresignedUploadResponse(url=presigned["url"], fields=presigned["fields"], key=key)


@router.post("/quote-requests/{quote_request_id}/media", status_code=status.HTTP_201_CREATED)
async def customer_attach_media(
    quote_request_id: UUID,
    data: QuoteRequestMediaCreate,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> dict[str, str]:
    """Attach an uploaded photo to the customer's own quote request."""
    await set_tenant_in_session(db, customer.tenant_id)
    quote_request = await db.get(QuoteRequest, quote_request_id)
    if (
        quote_request is None
        or quote_request.tenant_id != customer.tenant_id
        or quote_request.customer_id != customer.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")

    asset = MediaAsset(
        tenant_id=customer.tenant_id,
        quote_request_id=quote_request_id,
        file_url=data.file_url,
        file_key=data.file_key,
        mime_type=data.mime_type,
        size_bytes=data.size_bytes,
        source=data.source,
    )
    db.add(asset)
    await db.commit()
    return {"id": str(asset.id), "file_url": data.file_url}


@router.get("/quotes", response_model=list[QuoteRead])
async def list_my_quotes(
    customer: CurrentCustomerDep,
    db: DbDep,
) -> list[Quote]:
    """List quotes sent to the authenticated customer.

    Matches quotes attached to the customer's own CRM contact plus quotes
    generated from a lead that was linked to this customer account (the lead
    keeps the electrician-created contact).
    """
    result = await db.execute(
        select(Quote)
        .options(
            selectinload(Quote.line_items),
            selectinload(Quote.contact),
            selectinload(Quote.bill_of_quantities),
        )
        .where(
            Quote.tenant_id == customer.tenant_id,
            or_(
                Quote.contact_id == customer.contact_id,
                Quote.quote_request.has(QuoteRequest.customer_id == customer.id),
            ),
            Quote.status.in_(["sent", "approved", "rejected", "expired"]),
        )
        .order_by(Quote.created_at.desc())
    )
    return list(result.scalars().all())


async def _get_customer_quote(db: AsyncSession, customer: Customer, quote_id: UUID) -> Quote:
    quote = await db.scalar(
        select(Quote)
        .options(
            selectinload(Quote.line_items),
            selectinload(Quote.contact),
            selectinload(Quote.bill_of_quantities).selectinload(BillOfQuantities.line_items),
        )
        .where(
            Quote.tenant_id == customer.tenant_id,
            Quote.id == quote_id,
            or_(
                Quote.contact_id == customer.contact_id,
                Quote.quote_request.has(QuoteRequest.customer_id == customer.id),
            ),
        )
    )
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return quote


@router.post("/quotes/{quote_id}/accept", response_model=QuoteRead)
async def accept_quote(
    quote_id: UUID,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> Quote:
    """Customer accepts a sent quote."""
    quote = await _get_customer_quote(db, customer, quote_id)
    if quote.status != "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote cannot be accepted",
        )
    quote.status = "approved"
    quote.approved_at = datetime.utcnow()
    await notify_staff(
        db,
        customer.tenant_id,
        kind="quote_accepted",
        title="Quote accepted",
        body=f"{customer.full_name} accepted quote '{quote.title}'.",
        link=f"/quote/{quote.id}",
    )
    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/quotes/{quote_id}/reject", response_model=QuoteRead)
async def reject_quote(
    quote_id: UUID,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> Quote:
    """Customer rejects a sent quote."""
    quote = await _get_customer_quote(db, customer, quote_id)
    if quote.status != "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote cannot be rejected",
        )
    quote.status = "rejected"
    quote.approved_at = None
    await db.commit()
    await db.refresh(quote)
    return quote


@router.get("/appointments", response_model=list[AppointmentRead])
async def list_my_appointments(
    customer: CurrentCustomerDep,
    db: DbDep,
) -> list[Appointment]:
    """List appointments for the authenticated customer."""
    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == customer.tenant_id,
            Appointment.contact_id == customer.contact_id,
        )
        .order_by(Appointment.start_at.desc())
    )
    return list(result.scalars().all())


@router.post("/appointments", status_code=status.HTTP_201_CREATED, response_model=AppointmentRead)
async def create_customer_appointment(
    data: AppointmentCreate,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> Appointment:
    """Create an appointment for the authenticated customer."""
    # The customer token identifies the contact; ignore any contact_id supplied
    # by the client to prevent cross-customer bookings.
    payload = data.model_dump()
    payload["contact_id"] = customer.contact_id
    # Appointments are stored as naive UTC datetimes; strip tzinfo from ISO inputs.
    for key in ("start_at", "end_at"):
        dt = payload[key]
        if dt is not None and dt.tzinfo is not None:
            payload[key] = dt.astimezone(UTC).replace(tzinfo=None)
    appointment = Appointment(tenant_id=customer.tenant_id, **payload)
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    return appointment
