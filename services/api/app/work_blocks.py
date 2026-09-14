"""Working-day block planning for job scheduling.

Quotes carry an estimated duration in working hours (``Quote.estimated_hours``).
When that volume exceeds the tenant's single-day working hours the job is
multi-day: the schedule is split into consecutive working-day blocks of no
more than the daily working hours each. This module holds the pure planning
logic — no database, no FastAPI — so the quote convert path, the job-create
path and the schedule-suggestion endpoint all share one rule set.

Tenant settings drive everything: ``working_day_start`` / ``working_day_end``
("HH:MM") and ``working_days`` (weekday ints, Monday=0). Defaults preserve the
historical behaviour: 08:00-18:00, every day of the week.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

# Labour billing units. Hour units count 1:1 toward the estimate; day units
# count as a full working day each.
HOUR_UNITS = frozenset({"h", "hr", "hrs", "hour", "hours"})
DAY_UNITS = frozenset({"d", "day", "days"})

# Sanity cap on an LLM-supplied duration estimate (hours).
_MAX_LLM_ESTIMATE_HOURS = 1000.0
# Hard cap on how many days one job may span — guards against runaway input.
_MAX_BLOCK_DAYS = 60


def working_hours(settings: dict[str, Any] | None) -> tuple[time, time, set[int]]:
    """Resolve (day start, day end, working weekdays) from tenant settings."""

    def _parse(value: Any, fallback: time) -> time:
        try:
            hour, minute = str(value).split(":")
            parsed = time(int(hour), int(minute))
        except (ValueError, AttributeError):
            return fallback
        return parsed

    s = settings or {}
    start = _parse(s.get("working_day_start", "08:00"), time(8, 0))
    end = _parse(s.get("working_day_end", "18:00"), time(18, 0))
    days: set[int] = set(range(7))
    raw_days = s.get("working_days")
    if isinstance(raw_days, list):
        parsed_days = {
            int(d) for d in raw_days if str(d).lstrip("-").isdigit() and 0 <= int(d) <= 6
        }
        if parsed_days:
            days = parsed_days
    return start, end, days


def daily_working_hours(settings: dict[str, Any] | None) -> float:
    """Hours in one tenant working day (0 when the settings are inverted)."""
    start, end, _ = working_hours(settings)
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return max(minutes, 0) / 60.0


def is_multi_day(settings: dict[str, Any] | None, total_hours: float) -> bool:
    """True when the work volume cannot fit inside a single working day."""
    daily = daily_working_hours(settings)
    return daily > 0 and total_hours > daily


@dataclass(frozen=True)
class WorkBlock:
    """One working day's share of a job: ``hours`` never exceeds the daily cap."""

    day: date
    hours: float


def plan_working_blocks(
    settings: dict[str, Any] | None,
    start_day: date,
    total_hours: float,
    max_days: int = _MAX_BLOCK_DAYS,
) -> list[WorkBlock]:
    """Split ``total_hours`` into consecutive working-day blocks from ``start_day``.

    Each block takes ``min(remaining, daily hours)``; non-working days are
    skipped (a Friday start spills to Monday, not Saturday). Returns a single
    block when the work fits in one day. ``start_day`` itself is only used
    when it is a working day — otherwise the first block lands on the next
    working day.
    """
    _, _, working_days = working_hours(settings)
    daily = daily_working_hours(settings)
    if total_hours <= 0 or daily <= 0:
        return []
    blocks: list[WorkBlock] = []
    remaining = float(total_hours)
    day = start_day
    while remaining > 0 and len(blocks) < max_days:
        if day.weekday() in working_days:
            hours = min(remaining, daily)
            blocks.append(WorkBlock(day=day, hours=hours))
            remaining -= hours
        day += timedelta(days=1)
    return blocks


def estimate_hours_from_lines(
    lines: Iterable[tuple[float, str]],
    settings: dict[str, Any] | None,
) -> float:
    """Sum labour duration from line items: hour units 1:1, day units x daily hours.

    ``lines`` yields ``(quantity, unit)`` pairs; non-labour units (ea, m, job,
    point) contribute nothing — only time-billed lines carry duration signal.
    """
    daily = daily_working_hours(settings)
    total = 0.0
    for quantity, unit in lines:
        normalised = unit.strip().lower()
        if normalised in HOUR_UNITS:
            total += quantity
        elif normalised in DAY_UNITS:
            total += quantity * daily
    return total


def resolve_estimated_hours(
    lines: Iterable[tuple[float, str]],
    llm_value: Any,
    settings: dict[str, Any] | None,
) -> Decimal | None:
    """Resolve a quote's estimated working hours.

    The LLM's quote-level ``estimated_hours`` wins when it is a positive
    number (it covers fixed-price "job" labour lines that carry no per-unit
    hours); otherwise fall back to the deterministic sum of time-billed line
    items. Returns ``None`` when neither source yields anything.
    """
    try:
        parsed = float(llm_value)
    except (TypeError, ValueError):
        parsed = 0.0
    if parsed > 0:
        return Decimal(str(round(min(parsed, _MAX_LLM_ESTIMATE_HOURS), 2)))
    computed = estimate_hours_from_lines(lines, settings)
    if computed > 0:
        return Decimal(str(round(computed, 2)))
    return None
