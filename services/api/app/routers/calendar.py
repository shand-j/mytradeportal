"""Calendar feed: a subscribable .ics URL per tenant (Apple/Google Calendar).

The feed is public-by-token (calendar apps can't send auth headers): each
tenant gets an opaque feed token in ``tenant.settings["calendar_feed_token"]``,
minted on first request of the link endpoint. Appointments stream out as
VEVENTs. This is one-way (app → calendar); true two-way sync is post-beta.
"""

import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CALENDAR_FEED_BASE_URL, settings
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import Appointment, Tenant
from app.rls import bypass_rls_for_transaction, set_tenant_in_session

router = APIRouter(prefix="/calendar", tags=["Calendar"])
DbDep = Annotated[AsyncSession, Depends(get_db)]

logger = logging.getLogger(__name__)

_FEED_TOKEN_KEY = "calendar_feed_token"


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_dt(value: datetime) -> str:
    """Format as the iCalendar UTC DATE-TIME form (``YYYYMMDDTHHMMSSZ``).

    The API stores appointment times as naive UTC datetimes; aware values are
    converted. iOS cannot place naive floating times reliably and may reject
    the whole feed, so every DATE-TIME is pinned to UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _looks_like_admin_host(base_url: str) -> bool:
    host = urlparse(base_url).hostname or ""
    return host.split(".", 1)[0].startswith("admin")


def _feed_base_url(request: Request) -> str:
    """Base URL for feed links: override → request origin → ``app_public_url``.

    The request origin (the API's own host, via ``--proxy-headers``) is the
    correct default: the feed is served by this service. ``app_public_url``
    points at the back office / admin domain, where the feed path does not
    exist and returns HTML — iOS rejects that as a validation failure — so it
    is only a last resort.
    """
    base = (
        CALENDAR_FEED_BASE_URL or str(request.base_url).rstrip("/") or settings.app_public_url
    ).rstrip("/")
    if _looks_like_admin_host(base):
        logger.warning(
            "Calendar feed base URL %r resolves to the admin domain; "
            "set CALENDAR_FEED_BASE_URL to the API origin",
            base,
        )
    return base


def _feed_url(request: Request, token: str) -> str:
    return f"{_feed_base_url(request)}/calendar/feed.ics?token={token}"


def _webcal_url(https_url: str) -> str:
    """Rewrite an http(s) feed URL as webcal:// so iOS offers to subscribe."""
    return "webcal://" + https_url.split("://", 1)[-1]


@router.get("/feed-link")
async def get_feed_link(
    request: Request,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> dict[str, str]:
    """Return (minting on first use) this tenant's calendar feed URL.

    ``url`` is the plain https .ics feed (Google Calendar, manual copy);
    ``webcal_url`` is the same URL with a webcal:// scheme, which makes iOS
    show the native "Subscribe to this calendar?" prompt when opened.
    """
    await set_tenant_in_session(db, tenant.id)
    tenant_settings = dict(tenant.settings or {})
    token = tenant_settings.get(_FEED_TOKEN_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        tenant_settings[_FEED_TOKEN_KEY] = token
        tenant.settings = tenant_settings
        await db.commit()
    url = _feed_url(request, token)
    return {"url": url, "webcal_url": _webcal_url(url)}


@router.get("/feed.ics", response_class=PlainTextResponse)
async def calendar_feed(token: str, db: DbDep) -> PlainTextResponse:
    """The subscribable iCalendar feed of a tenant's appointments."""
    await bypass_rls_for_transaction(db)
    rows = (await db.execute(select(Tenant))).scalars().all()
    tenant = next((t for t in rows if (t.settings or {}).get(_FEED_TOKEN_KEY) == token), None)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown feed")

    appointments = (
        (
            await db.execute(
                select(Appointment)
                .where(Appointment.tenant_id == tenant.id, Appointment.status != "cancelled")
                .order_by(Appointment.start_at)
            )
        )
        .scalars()
        .all()
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//My Trade Portal//Calendar Feed//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(tenant.name)} jobs",
        # Hint hourly refresh so new/changed jobs reach subscribers promptly.
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for appt in appointments:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{appt.id}@mytradeportal",
            f"DTSTAMP:{_ics_dt(appt.updated_at)}",
            f"DTSTART:{_ics_dt(appt.start_at)}",
            f"DTEND:{_ics_dt(appt.end_at)}",
            f"SUMMARY:{_ics_escape(appt.title)}",
        ]
        if appt.address:
            lines.append(f"LOCATION:{_ics_escape(appt.address)}")
        if appt.notes:
            lines.append(f"DESCRIPTION:{_ics_escape(appt.notes)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    return PlainTextResponse(
        "\r\n".join(lines) + "\r\n",
        media_type="text/calendar",
        headers={"Content-Disposition": "inline; filename=calendar.ics"},
    )
