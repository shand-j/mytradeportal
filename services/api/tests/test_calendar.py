"""Tests for the calendar feed (.ics subscription) endpoints."""

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_contact(client: AsyncClient, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_appointment(
    client: AsyncClient,
    contact_id: str,
    start: datetime,
    end: datetime,
    title: str = "Site visit",
) -> dict[str, Any]:
    response = await client.post(
        "/appointments",
        json={
            "contact_id": contact_id,
            "title": title,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


def _token_from_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


async def test_feed_link_returns_https_and_webcal_urls(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/calendar/feed-link")
    assert response.status_code == 200
    data = response.json()
    assert data["url"].startswith("http")
    assert "/calendar/feed.ics?token=" in data["url"]
    assert data["webcal_url"] == "webcal://" + data["url"].split("://", 1)[1]

    # The feed token is minted once and stable across calls.
    again = await admin_client.get("/calendar/feed-link")
    assert again.json()["url"] == data["url"]


async def test_feed_link_uses_branded_base_url_when_configured(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.routers.calendar.CALENDAR_FEED_BASE_URL", "https://app.mytradeportal.co.uk/"
    )
    response = await admin_client.get("/calendar/feed-link")
    assert response.status_code == 200
    data = response.json()
    assert data["url"].startswith("https://app.mytradeportal.co.uk/calendar/feed.ics?token=")
    assert data["webcal_url"].startswith("webcal://app.mytradeportal.co.uk/calendar/feed.ics")


async def test_feed_link_uses_request_origin_when_no_override(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    # Even with APP_PUBLIC_URL configured (it points at the back office), the
    # feed link must be built on the API's own request origin.
    monkeypatch.setattr("app.routers.calendar.CALENDAR_FEED_BASE_URL", "")
    monkeypatch.setattr(settings, "app_public_url", "https://portal.example.com")
    response = await admin_client.get("/calendar/feed-link")
    assert response.status_code == 200
    data = response.json()
    assert data["url"].startswith("http://test/calendar/feed.ics?token=")
    assert data["webcal_url"].startswith("webcal://test/calendar/feed.ics")


async def test_feed_link_never_emits_admin_domain(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    # Production regression: APP_PUBLIC_URL pointed at the Django admin, so the
    # feed URL 404'd as HTML and iOS refused the subscription.
    monkeypatch.setattr("app.routers.calendar.CALENDAR_FEED_BASE_URL", "")
    monkeypatch.setattr(settings, "app_public_url", "https://admin-production-d0f5.up.railway.app")
    response = await admin_client.get("/calendar/feed-link")
    assert response.status_code == 200
    data = response.json()
    assert "admin-production-d0f5.up.railway.app" not in data["url"]
    assert "admin-production-d0f5.up.railway.app" not in data["webcal_url"]
    assert data["url"].startswith("http://test/calendar/feed.ics")


async def test_feed_base_url_warns_on_admin_domain_override(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "app.routers.calendar.CALENDAR_FEED_BASE_URL",
        "https://admin-production-d0f5.up.railway.app",
    )
    with caplog.at_level("WARNING", logger="app.routers.calendar"):
        response = await admin_client.get("/calendar/feed-link")
    assert response.status_code == 200
    assert any("admin domain" in record.getMessage() for record in caplog.records)


async def test_feed_ics_serves_valid_icalendar(admin_client: AsyncClient) -> None:
    contact = await _create_contact(admin_client, "Feed Customer")
    start = datetime.utcnow().replace(microsecond=0) + timedelta(days=1)
    await _create_appointment(admin_client, contact["id"], start, start + timedelta(hours=2))

    link = (await admin_client.get("/calendar/feed-link")).json()
    token = _token_from_url(link["url"])

    response = await admin_client.get(f"/calendar/feed.ics?token={token}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")

    body = response.text
    assert "\r\n" in body
    assert body.startswith("BEGIN:VCALENDAR")
    assert "VERSION:2.0" in body
    assert "PRODID:" in body
    assert "CALSCALE:GREGORIAN" in body
    assert "METHOD:PUBLISH" in body
    assert "X-WR-CALNAME:" in body
    assert "BEGIN:VEVENT" in body
    assert "SUMMARY:Site visit" in body
    assert body.rstrip().endswith("END:VCALENDAR")


async def test_feed_ics_vevent_fields_are_complete_and_tz_aware(
    admin_client: AsyncClient,
) -> None:
    """iOS rejects VEVENTs without UIDs or with naive (floating) datetimes."""
    contact = await _create_contact(admin_client, "Tz Customer")
    start = datetime(2026, 9, 20, 9, 30)  # stored naive; the API treats it as UTC
    await _create_appointment(admin_client, contact["id"], start, start + timedelta(hours=1))

    link = (await admin_client.get("/calendar/feed-link")).json()
    token = _token_from_url(link["url"])
    response = await admin_client.get(f"/calendar/feed.ics?token={token}")
    assert response.status_code == 200

    events = response.text.split("BEGIN:VEVENT")[1:]
    assert events, "expected at least one VEVENT"
    for event in events:
        assert re.search(r"^UID:\S+@\S+\r$", event, re.MULTILINE)
        assert re.search(r"^DTSTAMP:\d{8}T\d{6}Z\r$", event, re.MULTILINE)
        assert re.search(r"^DTSTART:\d{8}T\d{6}Z\r$", event, re.MULTILINE)
        assert re.search(r"^DTEND:\d{8}T\d{6}Z\r$", event, re.MULTILINE)
        assert re.search(r"^SUMMARY:.+\r$", event, re.MULTILINE)
    assert "DTSTART:20260920T093000Z" in response.text


async def test_feed_ics_unknown_token_returns_404(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/calendar/feed.ics?token=does-not-exist")
    assert response.status_code == 404
