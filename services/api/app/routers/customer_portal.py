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
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import CurrentCustomerDep
from app.email import send_event_email
from app.email_templates import account_created as account_created_template
from app.email_templates import quote_accepted as quote_accepted_template
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
    CustomerQuoteAccept,
    CustomerRead,
    CustomerRegister,
    CustomerTenantAssociation,
    CustomerTokenResponse,
    QuoteRead,
    QuoteRequestMediaCreate,
    QuoteRequestRead,
)
from app.security import create_access_token, get_password_hash, verify_password

router = APIRouter(prefix="/customer", tags=["Customer Portal"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = structlog.get_logger("api.customer_portal")

# Quote statuses a customer may see. Visibility is an allow-list (not
# "anything except draft") so future pre-send states (e.g. an explicit
# "in_review" status) can never leak unreviewed line items to the homeowner.
CUSTOMER_VISIBLE_QUOTE_STATUSES = frozenset({"sent", "approved", "rejected", "expired", "invoiced"})


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


async def _tenant_associations(
    db: AsyncSession, email: str, current_tenant_id: UUID
) -> list[CustomerTenantAssociation]:
    """Every active-tenant customer account for an email (multi-tenant shape).

    Cross-tenant by design — it must run under the transaction-local RLS
    bypass the register/login flows establish — so a homeowner with accounts
    at several electricians sees every association from one login. Only
    tenant id/slug/name are exposed, and callers invoke it strictly after
    credentials have been verified.
    """
    rows = (
        await db.execute(
            select(Customer.tenant_id, Tenant.slug, Tenant.name)
            .join(Tenant, Customer.tenant_id == Tenant.id)
            .where(
                func.lower(Customer.email) == email.lower(),
                Tenant.is_active.is_(True),
            )
            .order_by(Customer.created_at.desc())
        )
    ).all()
    return [
        CustomerTenantAssociation(
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            is_current=tenant_id == current_tenant_id,
        )
        for tenant_id, slug, name in rows
    ]


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

    # Reuse the CRM contact created when the homeowner requested their quote —
    # registering must not fork a second contact for the same person.
    contact = await db.scalar(
        select(Contact).where(Contact.tenant_id == tenant.id, Contact.email == str(data.email))
    )
    if contact is None:
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
    else:
        if data.phone:
            contact.phone = data.phone
        if data.address:
            contact.address = data.address
        if data.postcode:
            contact.postcode = data.postcode

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

    # Snapshot the tenant associations before commit ends the transaction
    # (and with it the cross-tenant RLS bypass the lookup relies on).
    associations = await _tenant_associations(db, customer.email, tenant.id)

    await db.refresh(customer)
    await db.commit()

    # Welcome email — transactional account mail, so platform-branded from the
    # no-reply sender (no tenant display name, no Reply-To). Best-effort: the
    # wrapper logs and never raises.
    from app.config import settings

    app_origin = settings.app_public_url.rstrip("/") if settings.app_public_url else ""
    subject, html, text = account_created_template(
        name=customer.full_name.split()[0] if customer.full_name else None,
        business_name=tenant.name,
        login_url=f"{app_origin}/customer-login" if app_origin else None,
    )
    await send_event_email(
        to_email=customer.email,
        subject=subject,
        html_body=html,
        text_body=text,
        event="account_created",
        template="account_created",
        context={"customer_id": str(customer.id), "tenant_id": str(tenant.id)},
    )

    return CustomerTokenResponse(
        access_token=_issue_token(customer),
        customer=CustomerRead.model_validate(customer),
        tenants=associations,
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
    the tenant is derived from it (newest account wins on duplicates). The
    response also lists every active tenant association for the email —
    single-tenant resolution today, multi-tenant-ready shape for later.
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

    # Post-auth tenant associations: only computed once credentials have
    # passed, and before _link_quote_requests_by_contact's commit ends the
    # transaction-local RLS bypass the cross-tenant lookup needs.
    associations = await _tenant_associations(db, customer.email, tenant.id)

    # Claim any leads captured with the same email/phone since the last login.
    if await _link_quote_requests_by_contact(db, customer):
        await db.commit()

    return CustomerTokenResponse(
        access_token=_issue_token(customer),
        customer=CustomerRead.model_validate(customer),
        tenants=associations,
    )


@router.get("/me", response_model=CustomerRead)
async def get_me(customer: CurrentCustomerDep) -> Customer:
    """Return the authenticated customer."""
    return customer


@router.get("/quote-requests", response_model=list[QuoteRequestRead])
async def list_my_quote_requests(
    customer: CurrentCustomerDep,
    db: DbDep,
) -> list[QuoteRequestRead]:
    """List the authenticated customer's quote requests (their history).

    Each response includes the linked quote (with line items) once the
    electrician has sent it, so the customer can view, accept or reject it.
    Drafts under review are withheld — the customer sees the request as
    "awaiting review" instead of peeking at unreviewed line items.
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
    rows = list(result.scalars().all())
    reads = [QuoteRequestRead.model_validate(qr) for qr in rows]
    # Quotes the electrician has not sent yet stay hidden: the customer sees
    # the request as awaiting review instead of peeking at unreviewed line
    # items. Gated on the allow-list, not "not draft", so new pre-send
    # statuses cannot leak by default.
    return [
        read.model_copy(update={"quote": None})
        if read.quote is not None and read.quote.status not in CUSTOMER_VISIBLE_QUOTE_STATUSES
        else read
        for read in reads
    ]


@router.post("/files/upload")
async def customer_upload_file(
    file: UploadFile,
    customer: CurrentCustomerDep,
) -> dict[str, str]:
    """Customer-scoped upload (photos on quote requests). Proxied through the
    API because MinIO is private-network-only."""
    from app.routers.files import _MAX_UPLOAD_BYTES, store_upload

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large"
        )
    try:
        return store_upload(customer.tenant_id, file, content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not store file: {exc}",
        ) from exc


@router.get("/files/download")
async def customer_download_file(key: str, customer: CurrentCustomerDep) -> Response:
    """Stream a stored file back to the customer (tenant-prefix enforced)."""
    from app.routers.files import stream_download

    return stream_download(customer.tenant_id, key)


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
            Quote.status.in_(CUSTOMER_VISIBLE_QUOTE_STATUSES),
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
            # Unsent quotes (draft/review states) are electrician-only; treat
            # them as not found. Allow-list, so new pre-send statuses stay
            # hidden by default.
            Quote.status.in_(CUSTOMER_VISIBLE_QUOTE_STATUSES),
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
    data: CustomerQuoteAccept | None = None,
) -> Quote:
    """Customer accepts a sent quote, reconfirming preferred visit dates."""
    quote = await _get_customer_quote(db, customer, quote_id)
    if quote.status != "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote cannot be accepted",
        )
    quote.status = "approved"
    quote.approved_at = datetime.utcnow()
    # The customer's reconfirmed dates ride on the quote so they surface when
    # the electrician converts it to a job.
    if data is not None and data.preferred_dates is not None:
        quote.accepted_dates = data.preferred_dates
    dates_note = ""
    if quote.accepted_dates:
        dates_note = f" Customer confirmed preferred dates: {', '.join(quote.accepted_dates)}."
    await notify_staff(
        db,
        customer.tenant_id,
        kind="quote_accepted",
        title="Quote accepted",
        body=f"{customer.full_name} accepted quote '{quote.title}'.{dates_note}",
        link=f"/quotes/{quote.id}",
    )
    await db.commit()
    # Confirm the acceptance to the customer by email. No response is expected,
    # so it goes out platform-branded from the no-reply sender. Best-effort:
    # the wrapper logs and never raises.
    tenant = await db.get(Tenant, customer.tenant_id)
    business_name = tenant.name if tenant is not None else "Your electrician"
    subject, html, text = quote_accepted_template(
        customer_name=customer.full_name.split()[0] if customer.full_name else "there",
        business_name=business_name,
        quote_title=quote.title,
        quote_total=f"£{quote.total}",
    )
    await send_event_email(
        to_email=customer.email,
        subject=subject,
        html_body=html,
        text_body=text,
        event="quote_accepted",
        template="quote_accepted",
        context={
            "quote_id": str(quote.id),
            "customer_id": str(customer.id),
            "tenant_id": str(customer.tenant_id),
        },
    )
    # Re-fetch with relationships eager-loaded: QuoteRead serialises
    # line_items/contact, which are expired on the committed object.
    return await _get_customer_quote(db, customer, quote_id)


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
