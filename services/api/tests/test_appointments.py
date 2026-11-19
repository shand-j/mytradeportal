"""Tests for appointment endpoints."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import Appointment, User
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _create_user(db: AsyncSession, tenant_id: str, name: str) -> User:
    await set_tenant_in_session(db, UUID(tenant_id))
    user = User(
        tenant_id=UUID(tenant_id),
        email=f"{name.lower().replace(' ', '.')}@staff.example.com",
        full_name=name,
        role="engineer",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_list_appointments_filters_by_assignee(client: AsyncClient, db: AsyncSession) -> None:
    """?assigned_user_id narrows the list ("Me"); omitting it returns all ("All")."""
    tenant = await _create_tenant(client, f"appt-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Appt Filter")
    spark_one = await _create_user(db, tenant["id"], "Spark One")
    spark_two = await _create_user(db, tenant["id"], "Spark Two")

    start = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)

    async def add(title: str, assignee: User | None) -> Appointment:
        # AppointmentCreate does not expose assigned_user_id (only the
        # job → appointment sync sets it), so seed rows directly.
        appointment = Appointment(
            tenant_id=UUID(tenant["id"]),
            contact_id=UUID(contact["id"]),
            title=title,
            start_at=start,
            end_at=start + timedelta(hours=1),
            assigned_user_id=assignee.id if assignee is not None else None,
        )
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)
        return appointment

    mine = await add("Visit one", spark_one)
    theirs = await add("Visit two", spark_two)
    unassigned = await add("Visit unassigned", None)

    all_response = await client.get("/appointments", headers={"X-Tenant-ID": tenant["id"]})
    assert all_response.status_code == 200
    all_ids = {a["id"] for a in all_response.json()}
    assert all_ids == {str(mine.id), str(theirs.id), str(unassigned.id)}

    filtered = await client.get(
        "/appointments",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"assigned_user_id": str(spark_one.id)},
    )
    assert filtered.status_code == 200
    assert {a["id"] for a in filtered.json()} == {str(mine.id)}
