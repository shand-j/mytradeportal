"""Job endpoints.

Address model: a job's address/postcode are denormalised from its contact at
creation time (both POST /jobs and the quote convert-to-job path) so a later
contact edit does not rewrite the job's history. They are display-only
afterwards — this router never writes them again.

Schedule sync: job schedules and appointments are kept as separate concepts,
synced one way only — job → appointment. When a job's scheduled_start/
scheduled_end is set or changed via PATCH /jobs/{id} and Appointment rows
reference the job (appointment.job_id), the first appointment moves to the
job's new slot and any further linked appointments shift by the same delta,
preserving their per-day spacing (multi-day jobs create one appointment per
working-day block beyond day 1). An end-less job schedule keeps each
appointment's existing duration; unscheduling a job leaves its appointments
untouched. Appointment edits never propagate back onto the job.

Multi-day jobs: when a job's duration exceeds the tenant's daily working
hours (tenant settings ``working_day_start`` / ``working_day_end`` /
``working_days``), POST /jobs caps day 1 at the daily hours and creates one
appointment per subsequent working-day block (see ``app.work_blocks``).
GET /jobs/suggest-schedule returns the earliest start where a quote's whole
block sequence fits around existing appointments and scheduled jobs.

Booking confirmation: creating a job with a real slot (``scheduled_start``
set, directly or via quote convert-to-job) emails the customer a
``booking_confirmed`` email (best-effort, tenant-branded, Reply-To the
tenant), and so does every later PATCH that moves ``scheduled_start``
(reschedules included). Passwordless (auto-provisioned) customers get an
account-claim magic-link CTA in that email; customers with a password do
not. Creating a job without a schedule, unrelated PATCHes and unscheduling
send nothing.
"""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import TenantDep
from app.email import send_customer_email
from app.email_templates import booking_confirmed as booking_confirmed_template
from app.models import Appointment, Contact, Customer, Job, Quote, QuoteLineItem, Tenant, User
from app.portal_links import magic_link_url
from app.push import notify_staff
from app.rls import set_tenant_in_session
from app.schemas import JobCreate, JobRead, JobUpdate, ScheduleSuggestion, ScheduleSuggestionDay
from app.work_blocks import (
    WorkBlock,
    daily_working_hours,
    estimate_hours_from_lines,
    is_multi_day,
    plan_working_blocks,
    working_hours,
)

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


def plan_job_blocks(
    settings: dict[str, Any] | None, start: datetime, end: datetime
) -> list[WorkBlock]:
    """Working-day block plan for a scheduled job.

    Empty when the scheduled span fits within a single working day; otherwise
    the split produced by :func:`app.work_blocks.plan_working_blocks` — the
    caller caps day 1 at ``blocks[0].hours`` and books the rest as
    appointments.
    """
    total_hours = (end - start).total_seconds() / 3600
    if not is_multi_day(settings, total_hours):
        return []
    return plan_working_blocks(settings, start.date(), total_hours)


async def create_block_appointments(
    db: AsyncSession,
    tenant_id: UUID,
    job: Job,
    blocks: list[WorkBlock],
    settings: dict[str, Any] | None,
) -> None:
    """Create one appointment per working-day block beyond day 1.

    Day 1 is represented by the job's own scheduled_start/scheduled_end (the
    availability busy-check counts scheduled jobs too), so appointments cover
    days 2..N, each starting at the tenant's working-day start.
    """
    if len(blocks) < 2:
        return
    work_start, _, _ = working_hours(settings)
    total_days = len(blocks)
    for index, block in enumerate(blocks[1:], start=2):
        start_at = datetime.combine(block.day, work_start)
        db.add(
            Appointment(
                tenant_id=tenant_id,
                contact_id=job.contact_id,
                job_id=job.id,
                title=f"{job.title} — day {index} of {total_days}",
                start_at=start_at,
                end_at=start_at + timedelta(hours=block.hours),
                address=job.address,
                assigned_user_id=job.assigned_user_id,
            )
        )


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
    # Multi-day split: a duration beyond the tenant's daily working hours is
    # capped at day 1 here; the remaining blocks become appointments below.
    blocks: list[WorkBlock] = []
    if job.scheduled_start is not None and job.scheduled_end is not None:
        blocks = plan_job_blocks(tenant.settings, job.scheduled_start, job.scheduled_end)
        if blocks:
            job.scheduled_end = job.scheduled_start + timedelta(hours=blocks[0].hours)
    db.add(job)
    await db.flush()
    if blocks:
        await create_block_appointments(db, tenant.id, job, blocks, tenant.settings)
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
    # First scheduling emails the booking confirmation just like a reschedule
    # does — the email dispatches only when the job landed on a real slot.
    if job.scheduled_start is not None:
        await _email_booking_confirmed(db, tenant.id, job)
    await db.commit()
    return JobRead.model_validate(await _get_job(db, tenant.id, job.id))


async def _sync_linked_appointments(
    db: AsyncSession, tenant_id: UUID, job: Job, previous_start: datetime | None
) -> None:
    """One-way job → appointment schedule sync (see module docstring).

    Every linked appointment shifts by the job's own movement (new start
    minus ``previous_start``), so the day-2..N block appointments of a
    multi-day job keep their working-day spacing. When the job was previously
    unscheduled there is no movement to apply: the first appointment snaps to
    the job's new slot and the rest keep their offset from it. An end-less
    job schedule keeps each appointment's existing duration; a job being
    unscheduled (no start) leaves its appointments untouched, since
    appointments cannot represent an unscheduled slot.
    """
    if job.scheduled_start is None:
        return
    result = await db.execute(
        select(Appointment)
        .where(Appointment.job_id == job.id, Appointment.tenant_id == tenant_id)
        .order_by(Appointment.start_at)
    )
    appointments = list(result.scalars().all())
    if not appointments:
        return
    if previous_start is not None:
        delta = job.scheduled_start - previous_start
    else:
        delta = job.scheduled_start - appointments[0].start_at
    for index, appointment in enumerate(appointments):
        duration = appointment.end_at - appointment.start_at
        appointment.start_at = appointment.start_at + delta
        # The day-1 appointment (the one landing on the job's own slot) tracks
        # the job's scheduled_end; later blocks keep their planned duration.
        if (
            index == 0
            and job.scheduled_end is not None
            and appointment.start_at == (job.scheduled_start)
        ):
            appointment.end_at = job.scheduled_end
        else:
            appointment.end_at = appointment.start_at + duration


async def _email_booking_confirmed(db: AsyncSession, tenant_id: UUID, job: Job) -> None:
    """Email the customer a booking confirmation for a freshly scheduled job.

    Best-effort and never raises: dispatch gaps surface via
    ``send_customer_email``'s logging. Tenant-branded with the tenant's own
    Reply-To so "need to change it? reply to this email" lands with the
    tradesperson.
    """
    if job.scheduled_start is None:
        return
    try:
        contact = await db.get(Contact, job.contact_id)
        if contact is None:
            logger.warning(
                "booking_confirmed_email_skipped",
                job_id=str(job.id),
                reason="no_contact",
            )
            return
        tenant_row = await db.get(Tenant, tenant_id)
        business_name = tenant_row.name if tenant_row is not None else "Your tradesperson"
        visit_date = job.scheduled_start.strftime("%A %d %B %Y")
        start_time = job.scheduled_start.strftime("%H:%M")
        if job.scheduled_end is not None:
            time_window = f"{start_time} - {job.scheduled_end.strftime('%H:%M')}"
        else:
            time_window = f"from {start_time}"
        address_parts = [part for part in (job.address, job.postcode) if part]
        # Account-claim CTA only for passwordless (auto-provisioned) customers:
        # the magic link lands on the portal claim page where they set a
        # password. Customers who already chose a password get no CTA.
        claim_url: str | None = None
        if tenant_row is not None:
            customer = await db.scalar(
                select(Customer).where(
                    Customer.tenant_id == tenant_id,
                    Customer.contact_id == contact.id,
                    Customer.is_active.is_(True),
                )
            )
            if customer is not None and customer.password_hash is None:
                claim_url = await magic_link_url(db, tenant_row, customer, "/claim")
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
            claim_url=claim_url,
        )
        await send_customer_email(
            db,
            tenant_id=tenant_id,
            contact_id=contact.id,
            purpose="booking confirmation",
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
        await _sync_linked_appointments(db, tenant.id, job, previous_start)
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


async def _busy_periods(
    db: AsyncSession, tenant_id: UUID, window_start: datetime, window_end: datetime
) -> list[tuple[datetime, datetime]]:
    """Appointments + scheduled jobs overlapping the window, as busy intervals."""
    busy: list[tuple[datetime, datetime]] = []
    result = await db.execute(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.start_at < window_end,
            Appointment.end_at > window_start,
            Appointment.status.notin_({"cancelled", "no_show"}),
        )
    )
    busy.extend((a.start_at, a.end_at) for a in result.scalars().all())

    jobs_result = await db.execute(
        select(Job).where(
            Job.tenant_id == tenant_id,
            Job.scheduled_start.isnot(None),
            Job.scheduled_start < window_end,
            Job.status.notin_({"cancelled", "completed"}),
        )
    )
    for job in jobs_result.scalars().all():
        job_start = job.scheduled_start
        if job_start is None:  # filtered above; satisfies the type checker
            continue
        # Jobs without an end block one hour from their start.
        job_end = job.scheduled_end or (job_start + timedelta(hours=1))
        if job_end > window_start:
            busy.append((job_start, job_end))
    return busy


def _free_hours(
    day: date,
    work_start: time,
    work_end: time,
    busy: list[tuple[datetime, datetime]],
) -> float:
    """Unbooked hours inside one day's working window."""
    day_start = datetime.combine(day, work_start)
    day_end = datetime.combine(day, work_end)
    if day_end <= day_start:
        return 0.0
    intervals = sorted(
        (max(start, day_start), min(end, day_end))
        for start, end in busy
        if start < day_end and end > day_start
    )
    booked = 0.0
    cursor = day_start
    for start, end in intervals:
        overlap_start = max(start, cursor)
        if end > overlap_start:
            booked += (end - overlap_start).total_seconds()
            cursor = max(cursor, end)
    return max((day_end - day_start).total_seconds() - booked, 0.0) / 3600


# How far ahead the schedule suggestion searches for a fitting start.
_SUGGESTION_SEARCH_DAYS = 45


@router.get("/suggest-schedule")
async def suggest_schedule(
    tenant: TenantDep,
    db: DbDep,
    quote_id: UUID | None = Query(default=None),
    hours: float | None = Query(default=None, gt=0),
) -> ScheduleSuggestion:
    """Earliest start where a job's full working-day block sequence fits.

    The work volume comes from ``hours`` directly, or from the quote's
    estimated hours (falling back to its time-billed line items). A candidate
    start only qualifies when EVERY block day has enough free time inside the
    tenant's working hours around existing appointments and scheduled jobs —
    a 3-day job starting Friday loses to one starting Monday when the weekend
    is off and Monday is half-booked.
    """
    await set_tenant_in_session(db, tenant.id)

    total_hours = hours
    if quote_id is not None:
        quote = await db.get(Quote, quote_id)
        if quote is None or quote.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quote")
        if total_hours is None:
            if quote.estimated_hours is not None:
                total_hours = float(quote.estimated_hours)
            else:
                result = await db.execute(
                    select(QuoteLineItem).where(QuoteLineItem.quote_id == quote.id)
                )
                total_hours = estimate_hours_from_lines(
                    ((float(li.quantity), li.unit) for li in result.scalars().all()),
                    tenant.settings,
                )
    if total_hours is None or total_hours <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hours or a quote with an estimated duration is required",
        )

    work_start, work_end, working_days = working_hours(tenant.settings)
    daily = daily_working_hours(tenant.settings)
    if daily <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant working hours are not configured",
        )
    search_start = date.today() + timedelta(days=1)
    # The busy window must cover the search range plus the longest possible
    # block sequence (each block consumes at most one working day).
    max_blocks = int(total_hours // daily) + 2
    window_end = datetime.combine(
        search_start + timedelta(days=_SUGGESTION_SEARCH_DAYS + max_blocks * 7),
        time.max,
    )
    busy = await _busy_periods(db, tenant.id, datetime.combine(search_start, time.min), window_end)

    for offset in range(_SUGGESTION_SEARCH_DAYS):
        candidate = search_start + timedelta(days=offset)
        if candidate.weekday() not in working_days:
            continue
        blocks = plan_working_blocks(tenant.settings, candidate, total_hours)
        if not blocks:
            break
        if all(
            _free_hours(block.day, work_start, work_end, busy) >= block.hours - 1e-6
            for block in blocks
        ):
            return ScheduleSuggestion(
                start_date=candidate,
                start_time=work_start.strftime("%H:%M"),
                days=[ScheduleSuggestionDay(date=block.day, hours=block.hours) for block in blocks],
                is_multi_day=len(blocks) > 1,
            )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No suitable slot found in the next {_SUGGESTION_SEARCH_DAYS} days",
    )


@router.get("/{job_id}")
async def get_job(job_id: UUID, tenant: TenantDep, db: DbDep) -> JobRead:
    """Get a single job."""
    job = await _get_job(db, tenant.id, job_id)
    return JobRead.model_validate(job)
