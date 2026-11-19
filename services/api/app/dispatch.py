"""Dispatch guardrails (epic #233 phase 2): server-side assignment rules.

Every path that puts work on a person's calendar — job create/update,
appointment create/update, quote convert-to-job (including draft adoption) —
must pass through here before committing. The checks are deliberately
server-side: the mobile app is not the only client.

Three rules, each a structured 409 (``detail`` is a dict with a
machine-readable ``code`` and a human-toastable ``reason``):

- ``schedule_conflict`` — the assignee already has a blocking job or
  appointment overlapping the window (double-booking). The busy math is the
  shared :mod:`app.availability` rule set, so draft jobs and
  cancelled/no-show appointments never block and back-to-back slots are fine.
- ``daily_hours_cap`` — the assignment would push the assignee past
  ``DAILY_SCHEDULE_CAP_HOURS`` scheduled hours on a calendar day.
- ``job_locked`` — the job is ``in_progress`` or ``completed``, so
  reassignment/reschedule is refused. A supervisor override is a known
  follow-up (out of scope for phase 2).
"""

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import AssigneeBooking, assignee_bookings, assignee_day_hours

if TYPE_CHECKING:
    from app.models import Job

# Maximum scheduled hours one assignee may carry on a single calendar day.
DAILY_SCHEDULE_CAP_HOURS = 10.0

# Job statuses whose schedule/assignee are frozen: the work is underway or
# done, so moving it would rewrite history the customer and crew rely on.
LOCKED_JOB_STATUSES = frozenset({"in_progress", "completed"})

# Float tolerance so exact-boundary totals (8h + 2h == 10h) pass the cap.
_EPSILON = 1e-6


def _conflict(code: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "reason": reason},
    )


def ensure_job_mutable(job: "Job") -> None:
    """Reject reassignment/reschedule of in-progress/completed jobs."""
    if job.status in LOCKED_JOB_STATUSES:
        raise _conflict(
            "job_locked",
            f"'{job.title}' is {job.status.replace('_', ' ')} — it can no longer be "
            "rescheduled or reassigned.",
        )


def _format_booking(booking: AssigneeBooking) -> str:
    return (
        f"'{booking.title}' "
        f"({booking.start.strftime('%a %d %b %H:%M')}-{booking.end.strftime('%H:%M')})"
    )


def _day_spans(start: datetime, end: datetime) -> list[tuple[date, float]]:
    """Split a span into (calendar day, hours on that day) pairs."""
    spans: list[tuple[date, float]] = []
    cursor = start
    while cursor < end:
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
        chunk_end = min(end, next_midnight)
        spans.append((cursor.date(), (chunk_end - cursor).total_seconds() / 3600))
        cursor = chunk_end
    return spans


async def enforce_assignment_guardrails(
    db: AsyncSession,
    tenant_id: UUID,
    assignee_id: UUID | None,
    spans: list[tuple[datetime, datetime]],
    *,
    exclude_job_id: UUID | None = None,
    exclude_appointment_ids: frozenset[UUID] = frozenset(),
) -> None:
    """Raise 409 when assigning ``spans`` to ``assignee_id`` breaks a rule.

    ``spans`` are the concrete (start, end) windows about to be booked — for a
    multi-day job that is the capped day-1 job span plus each block
    appointment's span. Unassigned work (no assignee) is never guarded.
    """
    if assignee_id is None or not spans:
        return

    window_start = min(start for start, _ in spans)
    window_end = max(end for _, end in spans)
    conflicts = await assignee_bookings(
        db,
        tenant_id,
        assignee_id,
        window_start,
        window_end,
        exclude_job_id=exclude_job_id,
        exclude_appointment_ids=exclude_appointment_ids,
    )
    for start, end in spans:
        hit = next(
            (b for b in conflicts if b.start < end and b.end > start),
            None,
        )
        if hit is not None:
            raise _conflict(
                "schedule_conflict",
                f"The assignee already has {_format_booking(hit)} in that window.",
            )

    # Daily cap: the assignee's existing hours plus every new span's hours on
    # the same calendar day must stay within the cap.
    new_hours_by_day: dict[date, float] = {}
    for start, end in spans:
        for day, hours in _day_spans(start, end):
            new_hours_by_day[day] = new_hours_by_day.get(day, 0.0) + hours
    for day, new_hours in new_hours_by_day.items():
        existing = await assignee_day_hours(
            db,
            tenant_id,
            assignee_id,
            day,
            exclude_job_id=exclude_job_id,
            exclude_appointment_ids=exclude_appointment_ids,
        )
        if existing + new_hours > DAILY_SCHEDULE_CAP_HOURS + _EPSILON:
            total = existing + new_hours
            raise _conflict(
                "daily_hours_cap",
                f"This would book the assignee for {total:.1f}h on "
                f"{day.strftime('%a %d %b')} — over the "
                f"{DAILY_SCHEDULE_CAP_HOURS:.0f}h daily cap.",
            )
