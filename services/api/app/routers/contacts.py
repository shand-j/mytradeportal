"""Contact endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import Actions, write_audit_log
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import Contact
from app.rls import set_tenant_in_session
from app.schemas import ContactCreate, ContactRead, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["Contacts"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_contact(db: AsyncSession, tenant_id: UUID, contact_id: UUID) -> Contact:
    await set_tenant_in_session(db, tenant_id)
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.get("")
async def list_contacts(tenant: TenantDep, db: DbDep) -> list[ContactRead]:
    """List contacts for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(select(Contact).where(Contact.tenant_id == tenant.id))
    return [ContactRead.model_validate(c) for c in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contact(
    data: ContactCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ContactRead:
    """Create a contact for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, **data.model_dump())
    db.add(contact)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_CREATED,
        entity_type="contact",
        entity_id=contact.id,
        payload={"name": contact.name, "email": contact.email},
    )
    await db.commit()
    await db.refresh(contact)
    return ContactRead.model_validate(contact)


@router.get("/{contact_id}")
async def get_contact(contact_id: UUID, tenant: TenantDep, db: DbDep) -> ContactRead:
    """Get a single contact."""
    contact = await _get_contact(db, tenant.id, contact_id)
    return ContactRead.model_validate(contact)


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ContactRead:
    """Update a contact."""
    contact = await _get_contact(db, tenant.id, contact_id)
    changed = data.model_dump(exclude_unset=True)
    for key, value in changed.items():
        setattr(contact, key, value)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_UPDATED,
        entity_type="contact",
        entity_id=contact.id,
        payload={"changed_fields": sorted(changed.keys())},
    )
    await db.commit()
    await db.refresh(contact)
    return ContactRead.model_validate(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """Delete a contact."""
    contact = await _get_contact(db, tenant.id, contact_id)
    # Capture identifying fields BEFORE deletion so the audit row still has
    # human-readable context after the contact row is gone.
    snapshot = {"name": contact.name, "email": contact.email}
    await db.delete(contact)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_DELETED,
        entity_type="contact",
        entity_id=contact_id,
        payload=snapshot,
    )
    await db.commit()
