"""Customer and property endpoints for the mobile quote-capture flow."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import Contact, Customer, Property
from app.rls import set_tenant_in_session
from app.schemas import CustomerCreate, CustomerRead, PropertyCreate, PropertyRead

router = APIRouter(prefix="/customers", tags=["Customers"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _set_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    await set_tenant_in_session(db, tenant_id)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CustomerRead)
async def create_customer(
    data: CustomerCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Customer:
    """Create a customer account and an associated CRM contact."""
    await _set_tenant(db, tenant.id)

    contact = Contact(
        tenant_id=tenant.id,
        name=data.full_name,
        email=data.email,
        phone=data.phone,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)

    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=str(data.email),
        full_name=data.full_name,
        phone=data.phone,
        password_hash=None,
        marketing_consent=data.marketing_consent,
        preferred_contact_method=data.preferred_contact_method,
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)
    return customer


@router.get("", response_model=list[CustomerRead])
async def list_customers(
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[Customer]:
    """List customers for the current tenant."""
    await _set_tenant(db, tenant.id)
    result = await db.execute(
        select(Customer).where(Customer.tenant_id == tenant.id).order_by(Customer.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Customer:
    """Get a single customer."""
    await _set_tenant(db, tenant.id)
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.post(
    "/{customer_id}/properties", status_code=status.HTTP_201_CREATED, response_model=PropertyRead
)
async def create_property(
    customer_id: UUID,
    data: PropertyCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Property:
    """Add a property to a customer record."""
    await _set_tenant(db, tenant.id)
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    property_ = Property(
        tenant_id=tenant.id,
        customer_id=customer_id,
        address=data.address,
        postcode=data.postcode,
        lat=data.lat,
        lng=data.lng,
        property_type=data.property_type,
        bedrooms=data.bedrooms,
        tenure=data.tenure,
        epc_rating=data.epc_rating,
        notes=data.notes,
    )
    db.add(property_)
    await db.flush()
    await db.refresh(property_)
    return property_


@router.get("/{customer_id}/properties", response_model=list[PropertyRead])
async def list_customer_properties(
    customer_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[Property]:
    """List properties for a customer."""
    await _set_tenant(db, tenant.id)
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    result = await db.execute(
        select(Property)
        .where(Property.customer_id == customer_id, Property.tenant_id == tenant.id)
        .order_by(Property.created_at.desc())
    )
    return list(result.scalars().all())
