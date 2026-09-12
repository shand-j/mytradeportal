"""Tests for tenant working hours driving appointment availability (N16)."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _next_weekday(weekday: int) -> date:
    """Next future date (at least tomorrow) falling on ``weekday`` (Mon=0)."""
    candidate = date.today() + timedelta(days=1)
    while candidate.weekday() != weekday:
        candidate += timedelta(days=1)
    return candidate


async def _availability(admin_client: AsyncClient, day: date) -> list[str]:
    response = await admin_client.get(
        "/appointments/availability", params={"date": day.isoformat()}
    )
    assert response.status_code == 200
    slots: list[str] = response.json()
    return slots


async def test_availability_defaults_to_full_week_8_to_18(admin_client: AsyncClient) -> None:
    slots = await _availability(admin_client, _next_weekday(0))
    assert len(slots) == 10
    assert slots[0].endswith("T08:00:00")
    assert slots[-1].endswith("T17:00:00")


async def test_availability_uses_configured_start_and_end(admin_client: AsyncClient) -> None:
    patch = await admin_client.patch(
        "/tenants/me",
        json={"settings": {"working_day_start": "09:30", "working_day_end": "12:30"}},
    )
    assert patch.status_code == 200

    slots = await _availability(admin_client, _next_weekday(0))
    assert len(slots) == 3
    assert slots[0].endswith("T09:30:00")
    assert slots[-1].endswith("T11:30:00")


async def test_availability_respects_working_days(admin_client: AsyncClient) -> None:
    patch = await admin_client.patch(
        "/tenants/me",
        json={"settings": {"working_days": [0]}},  # Mondays only
    )
    assert patch.status_code == 200

    assert await _availability(admin_client, _next_weekday(0)) != []
    assert await _availability(admin_client, _next_weekday(2)) == []


async def test_availability_settings_persist_round_trip(admin_client: AsyncClient) -> None:
    patch = await admin_client.patch(
        "/tenants/me",
        json={
            "settings": {
                "working_day_start": "07:00",
                "working_day_end": "15:00",
                "working_days": [1, 2, 3, 4],
            }
        },
    )
    assert patch.status_code == 200
    settings = patch.json()["settings"]
    assert settings["working_day_start"] == "07:00"
    assert settings["working_day_end"] == "15:00"
    assert settings["working_days"] == [1, 2, 3, 4]

    # Tuesday (1) is a working day, Saturday (5) is not.
    assert len(await _availability(admin_client, _next_weekday(1))) == 8
    assert await _availability(admin_client, _next_weekday(5)) == []
