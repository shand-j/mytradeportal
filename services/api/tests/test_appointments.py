"""Tests for appointment endpoints."""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


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


async def _create_appointment(
    client: AsyncClient,
    tenant_id: str,
    contact_id: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    response = await client.post(
        "/appointments",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Site visit",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def test_update_appointment(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"appt-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Appt Updater")
    start = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
    appt = await _create_appointment(
        client, tenant["id"], contact["id"], start, start + timedelta(hours=1)
    )

    response = await client.patch(
        f"/appointments/{appt['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"title": "Updated site visit", "status": "confirmed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated site visit"
    assert data["status"] == "confirmed"


async def test_delete_appointment(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"appt-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Appt Deleter")
    start = datetime.utcnow().replace(hour=11, minute=0, second=0, microsecond=0)
    appt = await _create_appointment(
        client, tenant["id"], contact["id"], start, start + timedelta(hours=1)
    )

    response = await client.delete(
        f"/appointments/{appt['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 204

    get_response = await client.get(
        f"/appointments/{appt['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert get_response.status_code == 404


async def test_availability_excludes_busy_slots(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"appt-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Appt Checker")

    date = datetime.utcnow().date() + timedelta(days=7)
    busy_start = datetime.combine(date, datetime.min.time().replace(hour=10))
    busy_end = busy_start + timedelta(hours=1)
    await _create_appointment(client, tenant["id"], contact["id"], busy_start, busy_end)

    response = await client.get(
        "/appointments/availability",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"date": date.isoformat()},
    )
    assert response.status_code == 200
    slots = response.json()
    assert len(slots) == 9  # 08:00-18:00 gives 10 one-hour slots, one is busy
    assert busy_start.isoformat() not in slots
    assert (busy_start + timedelta(hours=1)).isoformat() in slots
