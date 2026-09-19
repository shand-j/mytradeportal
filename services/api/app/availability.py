"""Free/busy calendar math shared by the staff and public availability paths.

One rule set: appointments and scheduled jobs block time; cancelled/no-show
appointments and cancelled/completed/draft jobs do not. A draft job is the
tentative hold auto-created when a customer accepts a quote with preferred
dates — the electrician has not confirmed it, so it must not block anyone's
calendar (including the public availability shown to other customers).

The same rule set powers the dispatch guardrails (``app.dispatch``): the
assignee-scoped queries below are the per-person view of the tenant-wide
``busy_periods`` math, so "would this double-book Dave?" and "is Dave free?"
can never disagree.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Job

# Job statuses that never block the calendar.
NON_BLOCKING_JOB_STATUSES = frozenset({"cancelled", "completed", "draft"})

# Appointment statuses that never block the calendar.
NON_BLOCKING_APPOINTMENT_STATUSES = frozenset({"cancelled", "no_show"})

# Jobs without a scheduled end block one hour from their start.
DEFAULT_JOB_DURATION = timedelta(hours=1)


async def busy_periods(
    db: AsyncSession, tenant_id: UUID, window_start: datetime, window_end: datetime
) -> list[tuple[datetime, datetime]]:
    """Appointments + scheduled jobs overlapping the window, as busy intervals."""
    busy: list[tuple[datetime, datetime]] = []
    result = await db.execute(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.start_at < window_end,
            Appointment.end_at > window_start,
            Appointment.status.notin_(NON_BLOCKING_APPOINTMENT_STATUSES),
        )
    )
    busy.extend((a.start_at, a.end_at) for a in result.scalars().all())

    jobs_result = await db.execute(
        select(Job).where(
            Job.tenant_id == tenant_id,
            Job.scheduled_start.isnot(None),
            Job.scheduled_start < window_end,
            Job.status.notin_(NON_BLOCKING_JOB_STATUSES),
        )
    )
    for job in jobs_result.scalars().all():
        job_start = job.scheduled_start
        if job_start is None:  # filtered above; satisfies the type checker
            continue
        # Jobs without an end block one hour from their start.
        job_end = job.scheduled_end or (job_start + DEFAULT_JOB_DURATION)
        if job_end > window_start:
            busy.append((job_start, job_end))
    return busy


def free_hours(
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


@dataclass(frozen=True)
class AssigneeBooking:
    """One existing booking on an assignee's calendar (for conflict messages)."""

    kind: str  # "job" | "appointment"
    id: UUID
    title: str
    start: datetime
    end: datetime


async def assignee_bookings(
    db: AsyncSession,
    tenant_id: UUID,
    assignee_id: UUID,
    window_start: datetime,
    window_end: datetime,
    *,
    exclude_job_id: UUID | None = None,
    exclude_appointment_ids: frozenset[UUID] = frozenset(),
) -> list[AssigneeBooking]:
    """The assignee's blocking jobs/appointments overlapping the window.

    Same overlap predicate and blocking rules as :func:`busy_periods`
    (strict inequality, so back-to-back slots do not collide), scoped to one
    assignee and returning identities so callers can name the conflict. The
    entity being created/moved is excluded via ``exclude_job_id`` /
    ``exclude_appointment_ids`` so a reschedule never conflicts with itself.
    """
    bookings: list[AssigneeBooking] = []
    appointment_query = select(Appointment).where(
        Appointment.tenant_id == tenant_id,
        Appointment.assigned_user_id == assignee_id,
        Appointment.start_at < window_end,
        Appointment.end_at > window_start,
        Appointment.status.notin_(NON_BLOCKING_APPOINTMENT_STATUSES),
    )
    if exclude_appointment_ids:
        appointment_query = appointment_query.where(Appointment.id.notin_(exclude_appointment_ids))
    result = await db.execute(appointment_query)
    bookings.extend(
        AssigneeBooking("appointment", a.id, a.title, a.start_at, a.end_at)
        for a in result.scalars().all()
    )

    job_query = select(Job).where(
        Job.tenant_id == tenant_id,
        Job.assigned_user_id == assignee_id,
        Job.scheduled_start.isnot(None),
        Job.scheduled_start < window_end,
        Job.status.notin_(NON_BLOCKING_JOB_STATUSES),
    )
    if exclude_job_id is not None:
        job_query = job_query.where(Job.id != exclude_job_id)
    jobs_result = await db.execute(job_query)
    for job in jobs_result.scalars().all():
        job_start = job.scheduled_start
        if job_start is None:  # filtered above; satisfies the type checker
            continue
        job_end = job.scheduled_end or (job_start + DEFAULT_JOB_DURATION)
        if job_end > window_start:
            bookings.append(AssigneeBooking("job", job.id, job.title, job_start, job_end))
    return bookings


async def assignee_day_hours(
    db: AsyncSession,
    tenant_id: UUID,
    assignee_id: UUID,
    day: date,
    *,
    exclude_job_id: UUID | None = None,
    exclude_appointment_ids: frozenset[UUID] = frozenset(),
) -> float:
    """Hours already scheduled for the assignee on one calendar day.

    Durations are clamped to the day's bounds, so an overnight booking only
    counts the portion falling on ``day`` (the rest lands on the next day's
    sum when that day is checked).
    """
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)
    bookings = await assignee_bookings(
        db,
        tenant_id,
        assignee_id,
        day_start,
        day_end,
        exclude_job_id=exclude_job_id,
        exclude_appointment_ids=exclude_appointment_ids,
    )
    total_seconds = sum(
        (min(b.end, day_end) - max(b.start, day_start)).total_seconds() for b in bookings
    )
    return total_seconds / 3600
