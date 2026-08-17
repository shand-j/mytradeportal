"""Homeowner (customer) portal: self-registration, login and quote history.

These endpoints back the customer side of the white-label app. A customer
belongs to one business (tenant), identified by slug at register/login time.
Auth is a bearer token with ``subject_type="customer"`` so it can never be used
against the staff API.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import CurrentCustomerDep
from app.limiter import limiter
from app.models import Contact, Customer, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.schemas import (
    CustomerLogin,
    CustomerRead,
    CustomerRegister,
    CustomerTokenResponse,
    QuoteRequestRead,
)
from app.security import create_access_token, get_password_hash, verify_password

router = APIRouter(prefix="/customer", tags=["Customer Portal"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


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
    await bypass_rls_in_session(db)
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
    )
    db.add(contact)
    await db.flush()

    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=str(data.email),
        full_name=data.full_name,
        phone=data.phone,
        password_hash=get_password_hash(data.password),
        marketing_consent=data.marketing_consent,
    )
    db.add(customer)
    await db.flush()
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
    """Authenticate a homeowner and return a bearer token."""
    await bypass_rls_in_session(db)
    tenant = await _resolve_active_tenant(db, data.slug)
    await set_tenant_in_session(db, tenant.id)

    customer = await db.scalar(
        select(Customer).where(Customer.tenant_id == tenant.id, Customer.email == str(data.email))
    )
    if (
        customer is None
        or not customer.is_active
        or customer.password_hash is None
        or not verify_password(data.password, customer.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

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
    """List the authenticated customer's quote requests (their history)."""
    # The customer dependency already set the tenant RLS context.
    result = await db.execute(
        select(QuoteRequest)
        .options(selectinload(QuoteRequest.contact))
        .where(
            QuoteRequest.tenant_id == customer.tenant_id,
            QuoteRequest.customer_id == customer.id,
        )
        .order_by(QuoteRequest.created_at.desc())
    )
    return list(result.scalars().all())
