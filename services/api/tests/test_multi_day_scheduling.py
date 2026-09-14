"""Multi-day job scheduling tests (N19).

Covers: quote estimated_hours exposure + is_multi_day derivation, the pure
working-block planner (boundaries, weekends), AI hours estimation precedence,
the multi-day split on quote → job conversion and POST /jobs, and the
/jobs/suggest-schedule recommendation skipping busy days.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.work_blocks import (
    daily_working_hours,
    is_multi_day,
    plan_working_blocks,
    resolve_estimated_hours,
)
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# Tenant working pattern used across most tests: 8-hour days, Monday-Friday.
WORKWEEK_SETTINGS = {
    "working_day_start": "08:00",
    "working_day_end": "16:00",
    "working_days": [0, 1, 2, 3, 4],
}


def _next_weekday(weekday: int, min_days_ahead: int = 1) -> date:
    """Next future date (at least ``min_days_ahead`` out) on ``weekday`` (Mon=0)."""
    candidate = date.today() + timedelta(days=min_days_ahead)
    while candidate.weekday() != weekday:
        candidate += timedelta(days=1)
    return candidate


def _next_working_day(day: date) -> date:
    candidate = day + timedelta(days=1)
    while candidate.weekday() not in WORKWEEK_SETTINGS["working_days"]:
        candidate += timedelta(days=1)
    return candidate


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


async def _set_workweek(client: AsyncClient, tenant_id: str) -> None:
    response = await client.patch(
        "/tenants/me",
        headers={"X-Tenant-ID": tenant_id},
        json={"settings": WORKWEEK_SETTINGS},
    )
    assert response.status_code == 200, response.text


async def _create_quote(
    client: AsyncClient,
    tenant_id: str,
    contact_id: str,
    estimated_hours: str | None = None,
    line_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contact_id": contact_id,
        "title": "Rewire",
        "line_items": line_items
        or [{"description": "Labour", "quantity": "4", "unit": "hours", "unit_price": "60.00"}],
    }
    if estimated_hours is not None:
        payload["estimated_hours"] = estimated_hours
    response = await client.post("/quotes", headers={"X-Tenant-ID": tenant_id}, json=payload)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def _approve_quote(client: AsyncClient, tenant_id: str, quote_id: str) -> None:
    response = await client.post(
        f"/quotes/{quote_id}/approve", headers={"X-Tenant-ID": tenant_id}, json={}
    )
    assert response.status_code == 200, response.text


async def _list_appointments(client: AsyncClient, tenant_id: str) -> list[dict[str, Any]]:
    response = await client.get("/appointments", headers={"X-Tenant-ID": tenant_id})
    assert response.status_code == 200
    data: list[dict[str, Any]] = response.json()
    return sorted(data, key=lambda a: a["start_at"])


# ---------------------------------------------------------------------------
# Pure planner unit tests
# ---------------------------------------------------------------------------


async def test_daily_hours_and_multi_day_boundary() -> None:
    assert daily_working_hours(WORKWEEK_SETTINGS) == 8.0
    # Exactly one working day is NOT multi-day; anything over is.
    assert not is_multi_day(WORKWEEK_SETTINGS, 8.0)
    assert is_multi_day(WORKWEEK_SETTINGS, 8.5)


async def test_plan_blocks_exact_day_is_single_block() -> None:
    monday = _next_weekday(0)
    blocks = plan_working_blocks(WORKWEEK_SETTINGS, monday, 8.0)
    assert len(blocks) == 1
    assert blocks[0].day == monday
    assert blocks[0].hours == 8.0


async def test_plan_blocks_skips_weekend() -> None:
    friday = _next_weekday(4)
    blocks = plan_working_blocks(WORKWEEK_SETTINGS, friday, 20.0)
    assert [(b.day, b.hours) for b in blocks] == [
        (friday, 8.0),
        (friday + timedelta(days=3), 8.0),  # Monday
        (friday + timedelta(days=4), 4.0),  # Tuesday
    ]


async def test_plan_blocks_non_working_start_moves_to_next_working_day() -> None:
    saturday = _next_weekday(5)
    blocks = plan_working_blocks(WORKWEEK_SETTINGS, saturday, 4.0)
    assert len(blocks) == 1
    assert blocks[0].day == saturday + timedelta(days=2)  # Monday


async def test_estimate_hours_llm_wins_then_line_fallback() -> None:
    lines = [(4.0, "hours"), (1.0, "day"), (10.0, "ea")]
    # LLM quote-level estimate takes precedence (covers fixed-price labour).
    assert resolve_estimated_hours(lines, 6.5, WORKWEEK_SETTINGS) == Decimal("6.5")
    # Fallback: 4 hours + 1 day x 8h; non-time units contribute nothing.
    assert resolve_estimated_hours(lines, None, WORKWEEK_SETTINGS) == Decimal("12.0")
    assert resolve_estimated_hours([(2.0, "job")], None, WORKWEEK_SETTINGS) is None


# ---------------------------------------------------------------------------
# Quote estimated_hours exposure
# ---------------------------------------------------------------------------


async def test_quote_read_exposes_estimated_hours_and_multi_day(admin_client: AsyncClient) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])
    contact = await _create_contact(client, tenant["id"], "Multi Day")
    quote = await _create_quote(client, tenant["id"], contact["id"], estimated_hours="20")

    fetched = await client.get(f"/quotes/{quote['id']}", headers={"X-Tenant-ID": tenant["id"]})
    assert fetched.status_code == 200
    body = fetched.json()
    assert Decimal(body["estimated_hours"]) == Decimal("20.00")
    assert body["is_multi_day"] is True

    # Exactly one working day (8h here) is not multi-day.
    patched = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"estimated_hours": "8"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_multi_day"] is False

    listed = await client.get("/quotes", headers={"X-Tenant-ID": tenant["id"]})
    assert listed.status_code == 200
    assert listed.json()[0]["estimated_hours"] is not None


async def test_quote_update_can_clear_estimated_hours(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"md-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Clear Hours")
    quote = await _create_quote(client, tenant["id"], contact["id"], estimated_hours="6")

    cleared = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"estimated_hours": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["estimated_hours"] is None
    assert cleared.json()["is_multi_day"] is False


async def test_ai_generation_populates_estimated_hours(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"md-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "AI Hours")
    generated = {
        "line_items": [
            {
                "description": "Rewire labour",
                "kind": "labour",
                "quantity": 16,
                "unit": "hour",
                "unit_price": 60.0,
                "reason": "two days",
            }
        ],
        "estimated_hours": 18.5,
        "assumptions": [],
        "notes": "",
    }
    with (
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=([], "unavailable")),
        ),
        patch(
            "app.routers.quotes.generate_quote_from_prompt", new=AsyncMock(return_value=generated)
        ),
    ):
        response = await client.post(
            "/quotes/generate",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"description": "Full house rewire", "contact_id": contact["id"]},
        )
    assert response.status_code == 201, response.text
    # The LLM's quote-level estimate wins over the 16h of labour lines.
    assert Decimal(response.json()["estimated_hours"]) == Decimal("18.50")


# ---------------------------------------------------------------------------
# Multi-day split on job create / convert
# ---------------------------------------------------------------------------


async def test_convert_to_job_splits_multi_day_across_working_days(
    admin_client: AsyncClient,
) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])
    contact = await _create_contact(client, tenant["id"], "Convert Split")
    quote = await _create_quote(client, tenant["id"], contact["id"], estimated_hours="20")
    await _approve_quote(client, tenant["id"], quote["id"])

    friday = _next_weekday(4)
    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": f"{friday.isoformat()}T09:00:00"},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    # Day 1 capped at the 8-hour working day.
    assert job["scheduled_start"] == f"{friday.isoformat()}T09:00:00"
    assert job["scheduled_end"] == f"{friday.isoformat()}T17:00:00"

    appointments = await _list_appointments(client, tenant["id"])
    monday = friday + timedelta(days=3)
    tuesday = friday + timedelta(days=4)
    assert [(a["start_at"], a["end_at"]) for a in appointments] == [
        (f"{monday.isoformat()}T08:00:00", f"{monday.isoformat()}T16:00:00"),
        (f"{tuesday.isoformat()}T08:00:00", f"{tuesday.isoformat()}T12:00:00"),
    ]
    assert all(a["job_id"] == job["id"] for a in appointments)
    assert "day 2 of 3" in appointments[0]["title"]
    assert "day 3 of 3" in appointments[1]["title"]


async def test_convert_to_job_single_day_creates_no_appointments(admin_client: AsyncClient) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])
    contact = await _create_contact(client, tenant["id"], "Single Day")
    quote = await _create_quote(client, tenant["id"], contact["id"], estimated_hours="6")
    await _approve_quote(client, tenant["id"], quote["id"])

    monday = _next_weekday(0)
    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": f"{monday.isoformat()}T09:00:00"},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["scheduled_end"] == f"{monday.isoformat()}T15:00:00"
    assert await _list_appointments(client, tenant["id"]) == []


async def test_create_job_with_long_span_splits_into_blocks(admin_client: AsyncClient) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])
    contact = await _create_contact(client, tenant["id"], "Manual Split")

    monday = _next_weekday(0)
    tuesday = monday + timedelta(days=1)
    # 12 hours of work encoded as start + duration (09:00 → 21:00 same day).
    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board + testing",
            "scheduled_start": f"{monday.isoformat()}T09:00:00",
            "scheduled_end": f"{monday.isoformat()}T21:00:00",
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    # 12h > 8h day → day 1 capped, remaining 4h booked on the next working day.
    assert job["scheduled_end"] == f"{monday.isoformat()}T17:00:00"
    appointments = await _list_appointments(client, tenant["id"])
    assert [(a["start_at"], a["end_at"]) for a in appointments] == [
        (f"{tuesday.isoformat()}T08:00:00", f"{tuesday.isoformat()}T12:00:00"),
    ]


async def test_reschedule_multi_day_job_shifts_block_appointments(
    admin_client: AsyncClient,
) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])
    contact = await _create_contact(client, tenant["id"], "Reschedule")
    quote = await _create_quote(client, tenant["id"], contact["id"], estimated_hours="16")
    await _approve_quote(client, tenant["id"], quote["id"])

    monday = _next_weekday(0)
    converted = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": f"{monday.isoformat()}T09:00:00"},
    )
    assert converted.status_code == 201, converted.text
    job = converted.json()

    # Move day 1 by a week: the day-2 appointment must shift by the same delta.
    new_start = monday + timedelta(days=7)
    moved = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": f"{new_start.isoformat()}T09:00:00"},
    )
    assert moved.status_code == 200, moved.text
    appointments = await _list_appointments(client, tenant["id"])
    assert len(appointments) == 1
    assert appointments[0]["start_at"] == f"{(new_start + timedelta(days=1)).isoformat()}T08:00:00"
    assert appointments[0]["end_at"] == f"{(new_start + timedelta(days=1)).isoformat()}T16:00:00"


# ---------------------------------------------------------------------------
# Schedule suggestion
# ---------------------------------------------------------------------------


async def test_suggest_schedule_returns_earliest_fitting_blocks(admin_client: AsyncClient) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])
    contact = await _create_contact(client, tenant["id"], "Suggest")
    quote = await _create_quote(client, tenant["id"], contact["id"], estimated_hours="16")

    response = await client.get(
        "/jobs/suggest-schedule",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"quote_id": quote["id"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_multi_day"] is True
    assert body["start_time"] == "08:00"
    assert len(body["days"]) == 2
    assert body["start_date"] == body["days"][0]["date"]
    # 8h + 8h on consecutive working days, starting tomorrow at the earliest.
    first = date.fromisoformat(body["days"][0]["date"])
    second = date.fromisoformat(body["days"][1]["date"])
    assert first >= date.today() + timedelta(days=1)
    assert first.weekday() in WORKWEEK_SETTINGS["working_days"]
    assert second == _next_working_day(first)
    assert [d["hours"] for d in body["days"]] == [8.0, 8.0]


async def test_suggest_schedule_skips_busy_days(admin_client: AsyncClient) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])
    contact = await _create_contact(client, tenant["id"], "Suggest Busy")
    quote = await _create_quote(client, tenant["id"], contact["id"], estimated_hours="16")

    initial = await client.get(
        "/jobs/suggest-schedule",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"quote_id": quote["id"]},
    )
    assert initial.status_code == 200, initial.text
    first_start = date.fromisoformat(initial.json()["start_date"])

    # Book the whole first candidate day out — the suggestion must move on.
    booked = await client.post(
        "/appointments",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Other work",
            "start_at": f"{first_start.isoformat()}T08:00:00",
            "end_at": f"{first_start.isoformat()}T16:00:00",
        },
    )
    assert booked.status_code == 201, booked.text

    moved = await client.get(
        "/jobs/suggest-schedule",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"quote_id": quote["id"]},
    )
    assert moved.status_code == 200, moved.text
    assert date.fromisoformat(moved.json()["start_date"]) == _next_working_day(first_start)


async def test_suggest_schedule_single_day_and_hours_param(admin_client: AsyncClient) -> None:
    client = admin_client
    tenant = {"id": client.headers["X-Tenant-ID"]}
    await _set_workweek(client, tenant["id"])

    response = await client.get(
        "/jobs/suggest-schedule",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"hours": 4},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_multi_day"] is False
    assert body["days"] == [{"date": body["start_date"], "hours": 4.0}]


async def test_suggest_schedule_requires_hours(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"md-{uuid4().hex[:8]}")
    response = await client.get("/jobs/suggest-schedule", headers={"X-Tenant-ID": tenant["id"]})
    assert response.status_code == 400
