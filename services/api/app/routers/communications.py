"""Communication log endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import TenantDep
from app.models import Communication, Contact
from app.rls import set_tenant_in_session
from app.schemas import CommunicationCreate, CommunicationRead

router = APIRouter(prefix="/communications", tags=["Communications"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def list_communications(tenant: TenantDep, db: DbDep) -> list[CommunicationRead]:
    """List communications for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(
        select(Communication)
        .where(Communication.tenant_id == tenant.id)
        .order_by(Communication.created_at.desc())
    )
    return [CommunicationRead.model_validate(c) for c in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_communication(
    data: CommunicationCreate,
    tenant: TenantDep,
    db: DbDep,
) -> CommunicationRead:
    """Log a communication for the current tenant."""
    await set_tenant_in_session(db, tenant.id)

    if data.contact_id:
        contact = await db.get(Contact, data.contact_id)
        if contact is None or contact.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    communication = Communication(tenant_id=tenant.id, **data.model_dump())
    db.add(communication)
    await db.commit()
    await db.refresh(communication)
    return CommunicationRead.model_validate(communication)
