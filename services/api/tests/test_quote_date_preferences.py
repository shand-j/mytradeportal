"""Tests for availability-aware quote date preferences and auto draft jobs.

Covers the issue #179 flow: the token-scoped public availability summary
(free/busy by date, no booking details), preference submission via
POST /public/quote/{token}/preferences, the tentative DRAFT job auto-created
at acceptance from the customer's 1st choice (never blocking the calendar,
never emailing the customer), and convert-to-job adopting that draft.
"""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.models import Job, Notification, Quote, Tenant
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_TOKEN_RE = re.compile(r"https://www\.mytradeportal\.co\.uk/(quote|invoice)/([A-Za-z0-9_-]+)")


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_contact(client: AsyncClient, tenant_id: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_quote(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Fuse board replacement",
            "line_items": [
                {"description": "Consumer unit", "quantity": "1", "unit_price": "450.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


def _extract_token(html: str, kind: str) -> str:
    match = _TOKEN_RE.search(html)
    assert match is not None, f"no {kind} link found in email body"
    assert match.group(1) == kind
    return match.group(2)


async def _send_quote_and_get_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """Tenant, contact, quote and the raw emailed document token."""
    sent: dict[str, Any] = {}

    async def fake_send_customer_email(db: Any = None, **kwargs: Any) -> bool:
        sent.update(kwargs)
        return True

    monkeypatch.setattr("app.routers.quotes.send_customer_email", fake_send_customer_email)

    tenant = await _create_tenant(client, f"pref-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Preference Homeowner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200
    return tenant, contact, quote, _extract_token(sent["html_body"], "quote")


def _mute_confirmation_email(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Capture the acceptance-confirmation email instead of sending it."""
    confirmation: dict[str, Any] = {}

    async def fake_confirmation_email(db: Any = None, **kwargs: Any) -> bool:
        confirmation.update(kwargs)
        return True

    monkeypatch.setattr("app.quote_acceptance.send_customer_email", fake_confirmation_email)
    monkeypatch.setattr("app.quote_acceptance.record_quote_outcome", AsyncMock(return_value=None))
    return confirmation


async def _create_appointment(
    client: AsyncClient,
    tenant_id: str,
    contact_id: str,
    day: date,
    start_hour: int,
    end_hour: int,
    title: str,
) -> None:
    response = await client.post(
        "/appointments",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": title,
            "start_at": f"{day.isoformat()}T{start_hour:02d}:00:00",
            "end_at": f"{day.isoformat()}T{end_hour:02d}:00:00",
        },
    )
    assert response.status_code == 201, response.text


async def _get_job_for_quote(db: AsyncSession, tenant_id: str, quote_id: str) -> Job | None:
    await set_tenant_in_session(db, UUID(tenant_id))
    job: Job | None = await db.scalar(select(Job).where(Job.quote_id == UUID(quote_id)))
    return job


# ---------------------------------------------------------------------------
# Public availability summary
# ---------------------------------------------------------------------------


async def test_public_availability_free_busy_by_date_without_details(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, contact, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    partial_day = date.today() + timedelta(days=1)
    busy_day = date.today() + timedelta(days=2)
    await _create_appointment(
        client, tenant["id"], contact["id"], partial_day, 9, 11, "Mrs Jones — private job"
    )
    await _create_appointment(
        client, tenant["id"], contact["id"], busy_day, 8, 18, "All day rewire at 12 Secret Lane"
    )

    response = await client.get(f"/public/quote/{raw}/availability?days=7")
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data.keys()) == {"estimated_hours", "days"}
    days = {entry["date"]: entry["status"] for entry in data["days"]}
    assert len(days) == 7
    assert days[partial_day.isoformat()] == "partial"
    assert days[busy_day.isoformat()] == "busy"
    assert days[(date.today() + timedelta(days=3)).isoformat()] == "available"
    # Privacy: no booking titles, addresses or customer names leak.
    assert "Mrs Jones" not in response.text
    assert "Secret Lane" not in response.text
    assert "rewire" not in response.text
    for entry in data["days"]:
        assert set(entry.keys()) == {"date", "status"}


async def test_public_availability_reports_estimated_hours(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    await set_tenant_in_session(db, UUID(tenant["id"]))
    quote_row = await db.get(Quote, UUID(quote["id"]))
    assert quote_row is not None
    quote_row.estimated_hours = Decimal("4.5")
    await db.commit()

    response = await client.get(f"/public/quote/{raw}/availability?days=3")
    assert response.status_code == 200
    assert response.json()["estimated_hours"] == 4.5


async def test_public_availability_marks_non_working_days_closed(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    await set_tenant_in_session(db, UUID(tenant["id"]))
    tenant_row = await db.get(Tenant, UUID(tenant["id"]))
    assert tenant_row is not None
    tenant_row.settings = {"working_days": [0]}  # Mondays only
    await db.commit()

    response = await client.get(f"/public/quote/{raw}/availability?days=14")
    assert response.status_code == 200
    days = {entry["date"]: entry["status"] for entry in response.json()["days"]}
    # Next Monday plus its Tuesday: on Mondays the next-Monday + Tuesday pair
    # can land on day 8, so the window must exceed 7 days to always contain both.
    monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    assert days[monday.isoformat()] == "available"
    tuesday = monday + timedelta(days=1)
    assert days[tuesday.isoformat()] == "closed"


async def test_public_availability_unknown_token_404s(client: AsyncClient) -> None:
    response = await client.get(f"/public/quote/{'x' * 43}/availability")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Preference submission
# ---------------------------------------------------------------------------


async def test_submit_preferences_stores_ranked_choices(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    first = (date.today() + timedelta(days=2)).isoformat()
    second = (date.today() + timedelta(days=4)).isoformat()

    response = await client.post(
        f"/public/quote/{raw}/preferences",
        json={
            "preferences": [
                {"date": first, "time": "morning"},
                {"date": second},
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted_dates"] == [f"{first} (morning)", second]

    await set_tenant_in_session(db, UUID(tenant["id"]))
    quote_row = await db.get(Quote, UUID(quote["id"]))
    assert quote_row is not None
    assert quote_row.accepted_dates == [f"{first} (morning)", second]
    # No job yet — the draft is created at acceptance, not on submission.
    assert await db.scalar(select(Job).where(Job.quote_id == quote_row.id)) is None
    # The public payload echoes the customer's own choices back to the page.
    payload = await client.get(f"/public/quote/{raw}")
    assert payload.json()["accepted_dates"] == [f"{first} (morning)", second]


async def test_submit_preferences_rejects_more_than_three(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    prefs = [
        {"date": (date.today() + timedelta(days=offset)).isoformat()} for offset in range(2, 6)
    ]
    response = await client.post(f"/public/quote/{raw}/preferences", json={"preferences": prefs})
    assert response.status_code == 422
    empty = await client.post(f"/public/quote/{raw}/preferences", json={"preferences": []})
    assert empty.status_code == 422


async def test_submit_preferences_conflict_after_decline(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    decline = await client.post(f"/public/quote/{raw}/decline")
    assert decline.status_code == 200
    response = await client.post(
        f"/public/quote/{raw}/preferences",
        json={"preferences": [{"date": (date.today() + timedelta(days=2)).isoformat()}]},
    )
    assert response.status_code == 409


async def test_submit_preferences_unknown_token_404s(client: AsyncClient) -> None:
    response = await client.post(
        f"/public/quote/{'x' * 43}/preferences",
        json={"preferences": [{"date": "2026-09-21"}]},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Auto draft job on acceptance
# ---------------------------------------------------------------------------


async def test_accept_with_preferences_creates_draft_job_from_first_choice(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    confirmation = _mute_confirmation_email(monkeypatch)
    booking_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.jobs.send_customer_email", booking_email)

    first = date.today() + timedelta(days=2)
    second = date.today() + timedelta(days=3)
    third = date.today() + timedelta(days=5)
    response = await client.post(
        f"/public/quote/{raw}/accept",
        json={
            "preferred_dates": [
                {"date": first.isoformat(), "time": "afternoon"},
                {"date": second.isoformat(), "time": "morning"},
                {"date": third.isoformat()},
            ]
        },
    )
    assert response.status_code == 200, response.text

    job = await _get_job_for_quote(db, tenant["id"], quote["id"])
    assert job is not None
    assert job.status == "draft"
    assert job.tenant_id == UUID(tenant["id"])
    assert job.title == "Fuse board replacement"
    # 1st choice pre-filled: afternoon window → 13:00, 2h default duration.
    assert job.scheduled_start == datetime(first.year, first.month, first.day, 13, 0)
    assert job.scheduled_end == datetime(first.year, first.month, first.day, 15, 0)
    assert job.notes is not None
    assert third.isoformat() in job.notes

    # The staff notification lists all three ranked choices.
    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == UUID(tenant["id"]),
            Notification.type == "quote_accepted",
        )
    )
    assert notification is not None
    assert f"{first.isoformat()} (afternoon)" in notification.body
    assert f"{second.isoformat()} (morning)" in notification.body
    assert third.isoformat() in notification.body
    assert "draft job" in notification.body

    # Only the acceptance confirmation went out — a draft never confirms a booking.
    assert confirmation.get("event") == "quote_accepted"
    booking_email.assert_not_called()


async def test_accept_without_preferences_creates_no_job(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    _mute_confirmation_email(monkeypatch)

    response = await client.post(f"/public/quote/{raw}/accept")
    assert response.status_code == 200, response.text
    assert await _get_job_for_quote(db, tenant["id"], quote["id"]) is None


async def test_preferences_after_acceptance_create_then_reseat_draft(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    _mute_confirmation_email(monkeypatch)

    accept = await client.post(f"/public/quote/{raw}/accept")
    assert accept.status_code == 200
    assert await _get_job_for_quote(db, tenant["id"], quote["id"]) is None

    first = date.today() + timedelta(days=3)
    response = await client.post(
        f"/public/quote/{raw}/preferences",
        json={"preferences": [{"date": first.isoformat(), "time": "morning"}]},
    )
    assert response.status_code == 200, response.text

    job = await _get_job_for_quote(db, tenant["id"], quote["id"])
    assert job is not None
    assert job.status == "draft"
    assert job.scheduled_start == datetime(first.year, first.month, first.day, 9, 0)

    # Staff hear about post-acceptance preference submissions.
    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == UUID(tenant["id"]),
            Notification.type == "quote_dates_submitted",
        )
    )
    assert notification is not None
    assert first.isoformat() in notification.body

    # Re-submitting moves the same draft rather than stacking jobs.
    moved = date.today() + timedelta(days=6)
    again = await client.post(
        f"/public/quote/{raw}/preferences",
        json={"preferences": [{"date": moved.isoformat()}]},
    )
    assert again.status_code == 200
    await db.refresh(job)
    assert job.scheduled_start == datetime(moved.year, moved.month, moved.day, 9, 0)
    jobs = (await db.scalars(select(Job).where(Job.quote_id == UUID(quote["id"])))).all()
    assert len(jobs) == 1


async def test_draft_job_never_blocks_availability(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    _mute_confirmation_email(monkeypatch)

    first = date.today() + timedelta(days=2)
    accept = await client.post(
        f"/public/quote/{raw}/accept",
        json={"preferred_dates": [{"date": first.isoformat(), "time": "morning"}]},
    )
    assert accept.status_code == 200
    job = await _get_job_for_quote(db, tenant["id"], quote["id"])
    assert job is not None and job.status == "draft"

    # The tentative hold leaves the day fully free on the public summary…
    availability = await client.get(f"/public/quote/{raw}/availability?days=4")
    days = {entry["date"]: entry["status"] for entry in availability.json()["days"]}
    assert days[first.isoformat()] == "available"
    # …and on the staff slot view used when picking the 2nd/3rd choice.
    slots = await client.get(
        f"/appointments/availability?date={first.isoformat()}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert slots.status_code == 200
    assert len(slots.json()) > 0


async def test_convert_to_job_adopts_draft(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    _mute_confirmation_email(monkeypatch)
    booking = AsyncMock(return_value=None)
    monkeypatch.setattr("app.routers.quotes._email_booking_confirmed", booking)

    first = date.today() + timedelta(days=2)
    accept = await client.post(
        f"/public/quote/{raw}/accept",
        json={"preferred_dates": [{"date": first.isoformat()}]},
    )
    assert accept.status_code == 200
    draft = await _get_job_for_quote(db, tenant["id"], quote["id"])
    assert draft is not None and draft.status == "draft"

    convert = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": f"{first.isoformat()}T10:00:00"},
    )
    assert convert.status_code == 201, convert.text
    converted = convert.json()
    assert converted["id"] == str(draft.id)
    assert converted["status"] == "scheduled"
    assert converted["scheduled_start"] == f"{first.isoformat()}T10:00:00"
    booking.assert_awaited_once()

    # Once confirmed, the job is no longer a draft — a second convert 409s.
    again = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert again.status_code == 409
