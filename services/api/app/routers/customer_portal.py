"""Homeowner (customer) portal: self-registration, login and quote history.

These endpoints back the customer side of the white-label app. A customer
belongs to one business (tenant), identified by slug at register/login time.
Auth is a bearer token with ``subject_type="customer"`` so it can never be used
against the staff API.

The web portal additionally supports invisible (magic-link) auth: emails embed
a link on the tenant's portal subdomain carrying a one-customer token that
``POST /customer/auth/magic`` exchanges for the same customer JWT.
"""

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import stripe_client
from app.database import get_db
from app.dependencies import CurrentCustomerDep, _extract_tenant_slug
from app.email import send_customer_email
from app.email_templates import account_created as account_created_template
from app.limiter import limiter
from app.models import (
    Appointment,
    BillOfQuantities,
    Contact,
    Customer,
    CustomerPortalToken,
    DocumentAccessToken,
    Invoice,
    MediaAsset,
    Quote,
    QuoteRequest,
    Tenant,
)
from app.portal_links import (
    flip_preferred_contact_to_app,
    hash_portal_token,
    magic_link_url,
)
from app.quote_acceptance import apply_quote_acceptance, apply_quote_decline
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.routers.contacts import BLOCKED_CUSTOMER_DETAIL, contact_is_blocked
from app.routers.public_docs import _invoice_payment_url, hash_document_token
from app.schemas import (
    AppointmentCreate,
    AppointmentRead,
    CustomerAccountClaim,
    CustomerLogin,
    CustomerMagicLinkCustomer,
    CustomerMagicLinkExchange,
    CustomerMagicLinkRequest,
    CustomerMagicLinkTokenResponse,
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

# Invoice statuses a customer may see. Same allow-list reasoning as quotes:
# drafts are electrician-only working documents and must never leak.
CUSTOMER_VISIBLE_INVOICE_STATUSES = frozenset({"sent", "paid", "overdue"})


class CustomerInvoiceLineItemRead(BaseModel):
    """A line item on a customer-facing invoice."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class CustomerInvoiceRead(BaseModel):
    """Customer-facing invoice: money, status and the business branding needed
    to render it — no staff internals (paddle ids, tenant/contact ids)."""

    id: UUID
    invoice_number: str
    status: str
    issue_date: datetime
    due_date: datetime | None
    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal
    paid_at: datetime | None
    notes: str | None
    line_items: list[CustomerInvoiceLineItemRead]
    business_name: str
    business_logo_url: str | None
    business_primary_color: str
    # Stripe /pay page URL for unpaid invoices when the tenant takes card
    # payments; null when card payment is unavailable or already settled.
    payment_url: str | None = None


def _customer_invoice_read(invoice: Invoice, tenant: Tenant | None) -> CustomerInvoiceRead:
    return CustomerInvoiceRead(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        status=invoice.status,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        vat_rate=invoice.vat_rate,
        vat_amount=invoice.vat_amount,
        total=invoice.total,
        paid_at=invoice.paid_at,
        notes=invoice.notes,
        line_items=[
            CustomerInvoiceLineItemRead.model_validate(item) for item in invoice.line_items
        ],
        business_name=tenant.name if tenant is not None else "Your electrician",
        business_logo_url=tenant.logo_url if tenant is not None else None,
        business_primary_color=tenant.primary_color if tenant is not None else "#D4650A",
    )


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
    if existing is not None and existing.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    if existing is not None and not data.password:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists — check your inbox for a sign-in link",
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

    if existing is not None:
        # Claim a passwordless account auto-provisioned at quote-request intake:
        # set the password and refresh details instead of forking a record.
        customer = existing
        customer.contact_id = contact.id
        customer.full_name = data.full_name
        customer.password_hash = get_password_hash(data.password)
        if data.phone:
            customer.phone = data.phone
        if data.address:
            customer.address = data.address
        if data.postcode:
            customer.postcode = data.postcode
        customer.marketing_consent = data.marketing_consent
        if data.preferred_contact_method:
            customer.preferred_contact_method = data.preferred_contact_method
    else:
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
    await send_customer_email(
        db,
        tenant_id=tenant.id,
        contact_id=customer.contact_id,
        purpose="welcome",
        to_email=customer.email,
        subject=subject,
        html_body=html,
        text_body=text,
        event="account_created",
        template="account_created",
        context={"customer_id": str(customer.id), "tenant_id": str(tenant.id)},
    )
    # The account commit already happened above; persist any email-failure
    # alert the send just raised (no-op when the send succeeded).
    await db.commit()

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

    # Blocked customers (N26) are refused only after their credentials have
    # verified, so the 403 cannot be used to enumerate block status.
    if await contact_is_blocked(db, tenant.id, customer.contact_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BLOCKED_CUSTOMER_DETAIL)

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


_MAGIC_LINK_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired magic link"
)
_MAGIC_REQUEST_RESPONSE = {
    "detail": "If an account exists for this email, a sign-in link is on its way."
}


@router.post("/auth/magic", response_model=CustomerMagicLinkTokenResponse)
@limiter.limit("10/minute")
async def exchange_magic_link(
    data: CustomerMagicLinkExchange,
    request: Request,
    db: DbDep,
) -> CustomerMagicLinkTokenResponse:
    """Exchange a portal magic-link token for a customer session JWT.

    Pre-auth endpoint: the token row lives outside RLS (same pattern as
    document access tokens). Unknown, expired and revoked tokens all fail with
    the same 401 so the endpoint never confirms a token exists. When the
    request arrives on a tenant subdomain, the token must belong to that
    tenant — a link leaked across businesses does not sign in.
    """
    await bypass_rls_for_transaction(db)
    record = await db.scalar(
        select(CustomerPortalToken).where(
            CustomerPortalToken.token_hash == hash_portal_token(data.token)
        )
    )
    if record is None or record.revoked_at is not None or record.expires_at < datetime.now(UTC):
        raise _MAGIC_LINK_401

    slug = _extract_tenant_slug(request.headers.get("host"))
    if slug is not None:
        host_tenant = await db.scalar(
            select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
        )
        if host_tenant is None or host_tenant.id != record.tenant_id:
            raise _MAGIC_LINK_401

    customer = await db.get(Customer, record.customer_id)
    if customer is None or not customer.is_active or customer.tenant_id != record.tenant_id:
        raise _MAGIC_LINK_401

    record.last_used_at = datetime.now(UTC)
    await db.commit()

    from app.config import settings

    session_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.auth_access_token_expire_minutes
    )
    return CustomerMagicLinkTokenResponse(
        access_token=_issue_token(customer),
        customer=CustomerMagicLinkCustomer(
            id=customer.id, full_name=customer.full_name, email=customer.email
        ),
        expires_at=session_expires_at,
    )


@router.post("/auth/magic/request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")
async def request_magic_link(
    data: CustomerMagicLinkRequest,
    request: Request,
    db: DbDep,
) -> dict[str, str]:
    """Email a portal magic link to the customer, if the account exists.

    The response is deliberately identical whether or not a customer with this
    email exists in the resolved tenant, so the endpoint cannot be used to
    enumerate accounts. The tenant comes from the Host subdomain (falling back
    to the default tenant on bare hosts, matching ``resolve_tenant``).
    """
    await bypass_rls_for_transaction(db)
    slug = _extract_tenant_slug(request.headers.get("host"))

    from app.config import settings

    tenant = await db.scalar(
        select(Tenant).where(
            Tenant.slug == (slug or settings.default_tenant_slug),
            Tenant.is_active.is_(True),
        )
    )
    customer = None
    if tenant is not None:
        customer = await db.scalar(
            select(Customer).where(
                Customer.tenant_id == tenant.id,
                func.lower(Customer.email) == str(data.email).lower(),
                Customer.is_active.is_(True),
            )
        )

    if tenant is not None and customer is not None:
        link = await magic_link_url(db, tenant, customer, "/quotes")
        await db.commit()
        # Transactional sign-in mail, platform-branded from the no-reply
        # sender. Best-effort: the wrapper logs and never raises.
        subject = f"Your sign-in link — {tenant.name}"
        text = (
            f"Hi {customer.full_name or 'there'},\n\n"
            f"Use this link to sign in to your {tenant.name} portal:\n{link}\n\n"
            "If you didn't request it, you can ignore this email.\n\n"
            "— My Trade Portal"
        )
        html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Your sign-in link</h1>
    <p>Hi {customer.full_name or "there"},</p>
    <p>Use the button below to sign in to your <strong>{tenant.name}</strong> portal.</p>
    <p style="margin:24px 0;"><a href="{link}" style="background:#D4650A;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;">Sign in</a></p>
    <p style="color:#64748b;font-size:13px;">If you didn't request this link, you can ignore this email.</p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
        await send_customer_email(
            db,
            tenant_id=tenant.id,
            contact_id=customer.contact_id,
            purpose="sign-in link",
            to_email=customer.email,
            subject=subject,
            html_body=html,
            text_body=text,
            event="magic_link_requested",
            template="magic_link",
            context={"customer_id": str(customer.id), "tenant_id": str(tenant.id)},
        )
        # The token commit already happened above; persist any email-failure
        # alert the send just raised (no-op when the send succeeded).
        await db.commit()

    return _MAGIC_REQUEST_RESPONSE


_CLAIM_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired claim link"
)


@router.post("/auth/claim", response_model=CustomerMagicLinkTokenResponse)
@limiter.limit("10/minute")
async def claim_account(
    data: CustomerAccountClaim,
    request: Request,
    db: DbDep,
) -> CustomerMagicLinkTokenResponse:
    """Claim an auto-provisioned customer account: set a password, get a JWT.

    Validates the portal magic-link token under the same rules as the magic
    exchange (SHA-256 lookup, not expired, not revoked, tenant-pinned to the
    Host subdomain), then sets the customer's password, revokes the token so
    each link claims exactly once, and flips the CRM contact's preferred
    contact method to "app" — the customer now has an account. A customer who
    already has a password can still claim: the token is proof of inbox
    ownership, so the claim doubles as a verified password reset.
    """
    await bypass_rls_for_transaction(db)
    record = await db.scalar(
        select(CustomerPortalToken).where(
            CustomerPortalToken.token_hash == hash_portal_token(data.token)
        )
    )
    if record is None or record.revoked_at is not None or record.expires_at < datetime.now(UTC):
        raise _CLAIM_401

    slug = _extract_tenant_slug(request.headers.get("host"))
    if slug is not None:
        host_tenant = await db.scalar(
            select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
        )
        if host_tenant is None or host_tenant.id != record.tenant_id:
            raise _CLAIM_401

    customer = await db.get(Customer, record.customer_id)
    if customer is None or not customer.is_active or customer.tenant_id != record.tenant_id:
        raise _CLAIM_401

    customer.password_hash = get_password_hash(data.password)
    record.revoked_at = datetime.now(UTC)
    record.last_used_at = datetime.now(UTC)
    await flip_preferred_contact_to_app(db, customer)
    await db.commit()

    from app.config import settings

    session_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.auth_access_token_expire_minutes
    )
    return CustomerMagicLinkTokenResponse(
        access_token=_issue_token(customer),
        customer=CustomerMagicLinkCustomer(
            id=customer.id, full_name=customer.full_name, email=customer.email
        ),
        expires_at=session_expires_at,
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
    # Both client shapes (list of date strings, list of {date} objects)
    # normalise to the same string list inside the shared transition.
    tenant = await db.get(Tenant, customer.tenant_id)
    await apply_quote_acceptance(
        db,
        quote=quote,
        tenant=tenant,
        customer_name=customer.full_name,
        preferred_dates=data.preferred_date_strings() if data is not None else None,
        outcome_payload={"actor": "customer", "customer_id": str(customer.id)},
        email_contact_id=customer.contact_id,
        email_to=customer.email,
        customer=customer,
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
    await apply_quote_decline(db, quote=quote)
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


async def _get_customer_invoice(db: AsyncSession, customer: Customer, invoice_id: UUID) -> Invoice:
    """Fetch an invoice the customer may see, or 404.

    Scoped to the customer's tenant and CRM contact and gated on the visible
    status allow-list, so drafts and other tenants'/customers' invoices are
    indistinguishable from missing ones.
    """
    invoice = await db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(
            Invoice.tenant_id == customer.tenant_id,
            Invoice.id == invoice_id,
            Invoice.contact_id == customer.contact_id,
            Invoice.status.in_(CUSTOMER_VISIBLE_INVOICE_STATUSES),
        )
    )
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.get("/invoices", response_model=list[CustomerInvoiceRead])
async def list_my_invoices(
    customer: CurrentCustomerDep,
    db: DbDep,
) -> list[CustomerInvoiceRead]:
    """List invoices sent to the authenticated customer (never drafts)."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(
            Invoice.tenant_id == customer.tenant_id,
            Invoice.contact_id == customer.contact_id,
            Invoice.status.in_(CUSTOMER_VISIBLE_INVOICE_STATUSES),
        )
        .order_by(Invoice.issue_date.desc())
    )
    invoices = list(result.scalars().all())
    tenant = await db.get(Tenant, customer.tenant_id)
    return [_customer_invoice_read(invoice, tenant) for invoice in invoices]


@router.get("/invoices/{invoice_id}", response_model=CustomerInvoiceRead)
async def get_my_invoice(
    invoice_id: UUID,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> CustomerInvoiceRead:
    """Invoice detail with line items and business branding for rendering."""
    invoice = await _get_customer_invoice(db, customer, invoice_id)
    tenant = await db.get(Tenant, customer.tenant_id)
    read = _customer_invoice_read(invoice, tenant)
    read.payment_url = await _portal_invoice_payment_url(db, invoice, tenant)
    return read


async def _portal_invoice_payment_url(
    db: AsyncSession, invoice: Invoice, tenant: Tenant | None
) -> str | None:
    """Stripe /pay URL for an unpaid portal invoice, or None when unavailable.

    Reuses the public-docs payment helper. The /pay page URL is keyed on a
    document access token, so a dedicated token is minted here WITHOUT
    revoking the one emailed with the invoice (unlike ``issue_document_token``)
    — both the emailed link and the portal pay link keep working.
    """
    if tenant is None or invoice.status == "paid" or not stripe_client.is_configured():
        return None
    raw = secrets.token_urlsafe(32)
    db.add(
        DocumentAccessToken(
            tenant_id=tenant.id,
            kind="invoice",
            document_id=invoice.id,
            token_hash=hash_document_token(raw),
            contact_email=None,
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
    )
    await db.flush()
    return await _invoice_payment_url(db, invoice, tenant, raw)


@router.post("/invoices/{invoice_id}/pay")
async def pay_my_invoice(
    invoice_id: UUID,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> None:
    """Online invoice payment moved to Stripe Connect (ADR-003).

    Tradie receivables never touch Paddle anymore; the customer pays by card
    on the landing-site /pay page linked from the invoice email. This endpoint
    remains only to give older app builds a clear signal instead of a 404.
    """
    invoice = await _get_customer_invoice(db, customer, invoice_id)
    if invoice.status == "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already paid",
        )
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Online card payment has moved — use the pay link in the invoice email.",
    )
