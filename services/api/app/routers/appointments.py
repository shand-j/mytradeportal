"""Appointment endpoints."""

from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import TenantDep
from app.models import Appointment, Contact, Job
from app.rls import set_tenant_in_session
from app.schemas import AppointmentCreate, AppointmentRead, AppointmentUpdate

router = APIRouter(prefix="/appointments", tags=["Appointments"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_appointment(db: AsyncSession, tenant_id: UUID, appointment_id: UUID) -> Appointment:
    await set_tenant_in_session(db, tenant_id)
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None or appointment.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appointment


@router.get("")
async def list_appointments(tenant: TenantDep, db: DbDep) -> list[AppointmentRead]:
    """List appointments for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(
        select(Appointment)
        .where(Appointment.tenant_id == tenant.id)
        .order_by(Appointment.start_at.desc())
    )
    return [AppointmentRead.model_validate(a) for a in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    tenant: TenantDep,
    db: DbDep,
) -> AppointmentRead:
    """Create an appointment."""
    await set_tenant_in_session(db, tenant.id)

    contact = await db.get(Contact, data.contact_id)
    if contact is None or contact.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    if data.job_id:
        job = await db.get(Job, data.job_id)
        if job is None or job.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job")

    appointment = Appointment(tenant_id=tenant.id, **data.model_dump())
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    return AppointmentRead.model_validate(appointment)


@router.get("/availability")
async def get_availability(
    tenant: TenantDep,
    db: DbDep,
    date: date = Query(..., description="Date to check availability (YYYY-MM-DD)"),
) -> list[str]:
    """Return free 1-hour appointment slots for the given date."""
    await set_tenant_in_session(db, tenant.id)

    day_start = datetime.combine(date, time(8, 0))
    day_end = datetime.combine(date, time(18, 0))

    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant.id,
            Appointment.start_at < day_end,
            Appointment.end_at > day_start,
            Appointment.status.notin_({"cancelled", "no_show"}),
        )
        .order_by(Appointment.start_at)
    )
    busy = result.scalars().all()

    slots: list[str] = []
    current = day_start
    while current + timedelta(hours=1) <= day_end:
        slot_end = current + timedelta(hours=1)
        is_free = True
        for appointment in busy:
            if appointment.start_at < slot_end and appointment.end_at > current:
                is_free = False
                break
        if is_free:
            slots.append(current.isoformat())
        current = slot_end

    return slots


@router.patch("/{appointment_id}")
async def update_appointment(
    appointment_id: UUID,
    data: AppointmentUpdate,
    tenant: TenantDep,
    db: DbDep,
) -> AppointmentRead:
    """Update an appointment."""
    appointment = await _get_appointment(db, tenant.id, appointment_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(appointment, key, value)
    await db.commit()
    return AppointmentRead.model_validate(appointment)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: UUID,
    tenant: TenantDep,
    db: DbDep,
) -> None:
    """Delete an appointment."""
    appointment = await _get_appointment(db, tenant.id, appointment_id)
    await db.delete(appointment)
    await db.commit()


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: UUID,
    tenant: TenantDep,
    db: DbDep,
) -> AppointmentRead:
    """Get a single appointment."""
    appointment = await _get_appointment(db, tenant.id, appointment_id)
    return AppointmentRead.model_validate(appointment)
