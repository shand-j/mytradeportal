"""Free/busy calendar math shared by the staff and public availability paths.

One rule set: appointments and scheduled jobs block time; cancelled/no-show
appointments and cancelled/completed/draft jobs do not. A draft job is the
tentative hold auto-created when a customer accepts a quote with preferred
dates — the electrician has not confirmed it, so it must not block anyone's
calendar (including the public availability shown to other customers).
"""

from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Job

# Job statuses that never block the calendar.
NON_BLOCKING_JOB_STATUSES = frozenset({"cancelled", "completed", "draft"})

# Appointment statuses that never block the calendar.
NON_BLOCKING_APPOINTMENT_STATUSES = frozenset({"cancelled", "no_show"})


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
        job_end = job.scheduled_end or (job_start + timedelta(hours=1))
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
