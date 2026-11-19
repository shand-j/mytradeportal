"""Customer preferred visit dates: storage format and parsing.

Preferences live on ``Quote.accepted_dates`` as a list of strings captured
at quote acceptance (public token page, customer portal or customer app).
Entries are either ISO dates ("2026-09-15"), ISO dates with a coarse time
window ("2026-09-15 (afternoon)"), or the en-GB short labels the customer
app offers ("Fri 12 Sep" — no year, so the current year is assumed, rolling
to next year when that day has already passed). Unparseable entries are
ignored everywhere they are consumed.

Pure helpers only — no database, no FastAPI — so the public-docs router,
the quote-acceptance transition and the quote convert-to-job path all share
one format.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# English month abbreviations, parsed manually so label parsing is locale-independent.
_MONTH_ABBREVS = {
    mon: num
    for num, mon in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

# Trailing "(window)" suffix of a stored preference, e.g. "2026-09-15 (morning)".
_TIME_WINDOW_RE = re.compile(r"\(([^()]{1,20})\)\s*$")


def format_preferred_date(iso_date: str, time_window: str | None) -> str:
    """Storage form for one preference: "2026-09-15" or "2026-09-15 (morning)"."""
    window = (time_window or "").strip()
    return f"{iso_date} ({window})" if window else iso_date


def parse_preferred_date(raw: Any, today: date) -> date | None:
    """Parse one accepted_dates entry into a concrete date.

    Handles ISO dates (with or without a time-window suffix) and the en-GB
    short labels. Unparseable entries return None.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    for candidate in (text, text.split()[0]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    day: int | None = None
    month: int | None = None
    for token in text.replace(",", " ").split():
        if token.isdigit() and day is None and 1 <= int(token) <= 31:
            day = int(token)
        elif month is None:
            month = _MONTH_ABBREVS.get(token.lower()[:3])
    if day is None or month is None:
        return None
    try:
        candidate_date = date(today.year, month, day)
        if candidate_date < today:
            candidate_date = date(today.year + 1, month, day)
    except ValueError:
        return None
    return candidate_date


def preferred_time_window(raw: Any) -> str | None:
    """The trailing "(window)" label of an entry, lower-cased, e.g. "morning"."""
    if not isinstance(raw, str):
        return None
    match = _TIME_WINDOW_RE.search(raw.strip())
    return match.group(1).strip().lower() if match else None


def first_preferred_date(entries: list[str], today: date) -> tuple[date, str | None] | None:
    """First parseable entry — the customer's ranked 1st choice — and its window."""
    for raw in entries:
        parsed = parse_preferred_date(raw, today)
        if parsed is not None:
            return parsed, preferred_time_window(raw)
    return None
