"""Job endpoints.

Address model: a job's address/postcode are denormalised from its contact at
creation time (both POST /jobs and the quote convert-to-job path) so a later
contact edit does not rewrite the job's history. They are display-only
afterwards — this router never writes them again.

Schedule sync: job schedules and appointments are kept as separate concepts,
synced one way only — job → appointment. When a job's scheduled_start/
scheduled_end is set or changed via PATCH /jobs/{id} and Appointment rows
reference the job (appointment.job_id), those appointments' start_at/end_at
move to match (an end-less job schedule keeps each appointment's existing
duration; unscheduling a job leaves its appointments untouched). This router
never creates appointments from job schedules, and appointment edits never
propagate back onto the job.

Booking confirmation: the same PATCH that sets or moves a job's
scheduled_start also emails the customer a ``booking_confirmed`` email
(best-effort, tenant-branded, Reply-To the tenant). Unrelated PATCHes and
unscheduling send nothing.
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import TenantDep
from app.email import send_event_email
from app.email_templates import booking_confirmed as booking_confirmed_template
from app.models import Appointment, Contact, Job, Quote, Tenant, User
from app.push import notify_staff
from app.rls import set_tenant_in_session
from app.schemas import JobCreate, JobRead, JobUpdate

router = APIRouter(prefix="/jobs", tags=["Jobs"])
logger = structlog.get_logger("api.jobs")
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _job_load_options() -> tuple[Any, ...]:
    """Eager-load everything JobRead derives display fields from."""
    return (
        selectinload(Job.contact),
        selectinload(Job.assignee),
        selectinload(Job.media),
    )


async def _get_job(db: AsyncSession, tenant_id: UUID, job_id: UUID) -> Job:
    await set_tenant_in_session(db, tenant_id)
    result = await db.execute(
        select(Job)
        .options(*_job_load_options())
        .where(Job.id == job_id, Job.tenant_id == tenant_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def _validate_assignee(
    db: AsyncSession, tenant_id: UUID, assigned_user_id: UUID | None
) -> None:
    """Assignees must be active staff of the same tenant."""
    if assigned_user_id is None:
        return
    user = await db.get(User, assigned_user_id)
    if user is None or user.tenant_id != tenant_id or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignee")


@router.get("")
async def list_jobs(tenant: TenantDep, db: DbDep) -> list[JobRead]:
    """List jobs for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(
        select(Job)
        .options(*_job_load_options())
        .where(Job.tenant_id == tenant.id)
        .order_by(Job.created_at.desc())
    )
    return [JobRead.model_validate(j) for j in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(data: JobCreate, tenant: TenantDep, db: DbDep) -> JobRead:
    """Create a job."""
    await set_tenant_in_session(db, tenant.id)

    contact = await db.get(Contact, data.contact_id)
    if contact is None or contact.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    if data.quote_id:
        quote = await db.get(Quote, data.quote_id)
        if quote is None or quote.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quote")

    await _validate_assignee(db, tenant.id, data.assigned_user_id)

    job = Job(
        tenant_id=tenant.id,
        # Denormalise the contact's current address for display stability;
        # lat/lng stay null (no geocoding yet).
        address=contact.address,
        postcode=contact.postcode,
        **data.model_dump(),
    )
    db.add(job)
    await db.flush()
    if job.status == "scheduled":
        scheduled_str = (
            job.scheduled_start.strftime("%a %d %b %H:%M") if job.scheduled_start else "TBC"
        )
        await notify_staff(
            db,
            tenant.id,
            kind="job_scheduled",
            title="Job scheduled",
            body=f"'{job.title}' scheduled for {scheduled_str}.",
            link=f"/job/{job.id}",
        )
    await db.commit()
    return JobRead.model_validate(await _get_job(db, tenant.id, job.id))


async def _sync_linked_appointments(db: AsyncSession, tenant_id: UUID, job: Job) -> None:
    """One-way job → appointment schedule sync (see module docstring).

    Moves every appointment linked to the job to the job's new slot. An
    end-less job schedule keeps each appointment's existing duration; a job
    being unscheduled (no start) leaves its appointments untouched, since
    appointments cannot represent an unscheduled slot.
    """
    if job.scheduled_start is None:
        return
    result = await db.execute(
        select(Appointment).where(Appointment.job_id == job.id, Appointment.tenant_id == tenant_id)
    )
    for appointment in result.scalars().all():
        duration = appointment.end_at - appointment.start_at
        appointment.start_at = job.scheduled_start
        appointment.end_at = job.scheduled_end or (job.scheduled_start + duration)


async def _email_booking_confirmed(db: AsyncSession, tenant_id: UUID, job: Job) -> None:
    """Email the customer a booking confirmation for a freshly scheduled job.

    Best-effort and never raises: dispatch gaps surface via
    ``send_event_email``'s logging. Tenant-branded with the tenant's own
    Reply-To so "need to change it? reply to this email" lands with the
    tradesperson.
    """
    if job.scheduled_start is None:
        return
    try:
        contact = job.contact
        tenant_row = await db.get(Tenant, tenant_id)
        business_name = tenant_row.name if tenant_row is not None else "Your tradesperson"
        visit_date = job.scheduled_start.strftime("%A %d %B %Y")
        start_time = job.scheduled_start.strftime("%H:%M")
        if job.scheduled_end is not None:
            time_window = f"{start_time} - {job.scheduled_end.strftime('%H:%M')}"
        else:
            time_window = f"from {start_time}"
        address_parts = [part for part in (job.address, job.postcode) if part]
        subject, html, text = booking_confirmed_template(
            customer_name=contact.name.split()[0] if contact.name else "there",
            business_name=business_name,
            job_title=job.title,
            visit_date=visit_date,
            time_window=time_window,
            address=", ".join(address_parts) if address_parts else None,
            tradie_name=business_name,
            tradie_phone=(
                tenant_row.phone if tenant_row is not None and tenant_row.phone else None
            ),
        )
        await send_event_email(
            to_email=contact.email,
            subject=subject,
            html_body=html,
            text_body=text,
            event="booking_confirmed",
            template="booking_confirmed",
            from_name=business_name,
            reply_to=(tenant_row.email if tenant_row is not None and tenant_row.email else None),
            context={"job_id": str(job.id), "tenant_id": str(tenant_id)},
        )
    except Exception as exc:
        logger.error(
            "booking_confirmed_email_failed",
            job_id=str(job.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )


@router.patch("/{job_id}")
async def update_job(
    job_id: UUID,
    data: JobUpdate,
    tenant: TenantDep,
    db: DbDep,
) -> JobRead:
    """Update a job's schedule, notes or assignee."""
    job = await _get_job(db, tenant.id, job_id)
    changes = data.model_dump(exclude_unset=True)
    if "assigned_user_id" in changes:
        await _validate_assignee(db, tenant.id, changes["assigned_user_id"])
    previous_start = job.scheduled_start
    for key, value in changes.items():
        setattr(job, key, value)
    if "scheduled_start" in changes or "scheduled_end" in changes:
        await _sync_linked_appointments(db, tenant.id, job)
        # Booking confirmation to the customer on every schedule change that
        # lands on a real slot (first scheduling and reschedules alike;
        # unscheduling sends nothing — the electrician tells them directly).
        if "scheduled_start" in changes and job.scheduled_start != previous_start:
            await _email_booking_confirmed(db, tenant.id, job)
    await db.commit()
    # The assignee/media relationships were loaded by the initial _get_job;
    # expire them so the re-read reflects the values just written.
    db.expire(job, ["assignee", "media"])
    return JobRead.model_validate(await _get_job(db, tenant.id, job.id))


@router.post("/{job_id}/start")
async def start_job(job_id: UUID, tenant: TenantDep, db: DbDep) -> JobRead:
    """Mark a job as in progress."""
    job = await _get_job(db, tenant.id, job_id)
    job.status = "in_progress"
    await db.commit()
    return JobRead.model_validate(job)


@router.post("/{job_id}/complete")
async def complete_job(job_id: UUID, tenant: TenantDep, db: DbDep) -> JobRead:
    """Mark a job as completed."""
    job = await _get_job(db, tenant.id, job_id)
    job.status = "completed"
    job.completed_at = datetime.utcnow()
    await db.commit()
    return JobRead.model_validate(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: UUID, tenant: TenantDep, db: DbDep) -> JobRead:
    """Cancel a job."""
    job = await _get_job(db, tenant.id, job_id)
    job.status = "cancelled"
    await db.commit()
    return JobRead.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: UUID, tenant: TenantDep, db: DbDep) -> None:
    """Delete a job."""
    job = await _get_job(db, tenant.id, job_id)
    await db.delete(job)
    await db.commit()


@router.get("/{job_id}")
async def get_job(job_id: UUID, tenant: TenantDep, db: DbDep) -> JobRead:
    """Get a single job."""
    job = await _get_job(db, tenant.id, job_id)
    return JobRead.model_validate(job)
