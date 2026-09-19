"""Appointment endpoints."""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import NON_BLOCKING_JOB_STATUSES
from app.database import get_db
from app.dependencies import TenantDep, single_active_user
from app.models import Appointment, Contact, Job
from app.rls import set_tenant_in_session
from app.routers.jobs import _validate_assignee
from app.schemas import AppointmentCreate, AppointmentRead, AppointmentUpdate
from app.work_blocks import working_hours

router = APIRouter(prefix="/appointments", tags=["Appointments"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _working_hours(settings: dict[str, Any] | None) -> tuple[time, time, set[int]]:
    """Resolve the tenant's working hours from tenant settings.

    Thin wrapper over :func:`app.work_blocks.working_hours` (the shared
    implementation used by availability, multi-day block planning and the
    schedule suggestion). Settings keys: ``working_day_start`` /
    ``working_day_end`` ("HH:MM") and ``working_days`` (list of weekday ints,
    Monday=0). Defaults preserve the historical behaviour: 08:00-18:00, every
    day of the week.
    """
    return working_hours(settings)


async def _get_appointment(db: AsyncSession, tenant_id: UUID, appointment_id: UUID) -> Appointment:
    await set_tenant_in_session(db, tenant_id)
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None or appointment.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appointment


@router.get("")
async def list_appointments(
    tenant: TenantDep,
    db: DbDep,
    assigned_user_id: UUID | None = Query(default=None),
) -> list[AppointmentRead]:
    """List appointments for the current tenant.

    ``assigned_user_id`` narrows the list to appointments assigned to that
    staff member (the mobile calendar's "Me" view); omitting it returns the
    whole team ("All").
    """
    await set_tenant_in_session(db, tenant.id)
    query = (
        select(Appointment)
        .where(Appointment.tenant_id == tenant.id)
        .order_by(Appointment.start_at.desc())
    )
    if assigned_user_id is not None:
        query = query.where(Appointment.assigned_user_id == assigned_user_id)
    result = await db.execute(query)
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

    # Same sole-staff default as job creation: a single-seat tenant's only
    # active user is the implicit assignee when none is supplied.
    assigned_user_id = data.assigned_user_id
    if assigned_user_id is None:
        sole_user = await single_active_user(db, tenant.id)
        if sole_user is not None:
            assigned_user_id = sole_user.id
    await _validate_assignee(db, tenant.id, assigned_user_id)

    appointment = Appointment(
        tenant_id=tenant.id, **{**data.model_dump(), "assigned_user_id": assigned_user_id}
    )
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
    """Return free 1-hour appointment slots for the given date.

    Both appointments and scheduled jobs block a slot — a day that looks free
    on the appointment calendar may already have a job booked. Slots only
    fall inside the tenant's configured working hours (``working_day_start`` /
    ``working_day_end`` / ``working_days`` settings); days outside the working
    week return no slots.
    """
    await set_tenant_in_session(db, tenant.id)

    work_start, work_end, working_days = _working_hours(tenant.settings)
    if date.weekday() not in working_days:
        return []
    day_start = datetime.combine(date, work_start)
    day_end = datetime.combine(date, work_end)
    if day_end <= day_start:
        return []

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
    busy_periods: list[tuple[datetime, datetime]] = [
        (appointment.start_at, appointment.end_at) for appointment in result.scalars().all()
    ]

    jobs_result = await db.execute(
        select(Job).where(
            Job.tenant_id == tenant.id,
            Job.scheduled_start.isnot(None),
            Job.scheduled_start < day_end,
            Job.status.notin_(NON_BLOCKING_JOB_STATUSES),
        )
    )
    for job in jobs_result.scalars().all():
        job_start = job.scheduled_start
        if job_start is None:  # filtered above; satisfies the type checker
            continue
        # Jobs without an end block one hour from their start.
        job_end = job.scheduled_end or (job_start + timedelta(hours=1))
        if job_end > day_start:
            busy_periods.append((job_start, job_end))

    slots: list[str] = []
    current = day_start
    while current + timedelta(hours=1) <= day_end:
        slot_end = current + timedelta(hours=1)
        is_free = True
        for busy_start, busy_end in busy_periods:
            if busy_start < slot_end and busy_end > current:
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
