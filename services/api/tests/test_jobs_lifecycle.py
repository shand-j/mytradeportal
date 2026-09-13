"""Tests for job lifecycle endpoints."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import Notification
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
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


async def _create_job(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Wiring job",
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def test_create_job_links_notification_to_job(client: AsyncClient, db: AsyncSession) -> None:
    """job_scheduled stores /job/{id} so the staff bell row deep-links."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Notifier")
    job = await _create_job(client, tenant["id"], contact["id"])

    await set_tenant_in_session(db, UUID(tenant["id"]))
    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == UUID(tenant["id"]),
            Notification.type == "job_scheduled",
        )
    )
    assert notification is not None
    assert notification.link == f"/job/{job['id']}"


async def test_job_read_includes_customer_address(client: AsyncClient) -> None:
    """JobRead embeds the contact's address/postcode (calendar week view)."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "name": "Job Address",
            "email": "job.address@example.com",
            "address": "10 Downing Street",
            "postcode": "SW1A 2AA",
        },
    )
    assert response.status_code == 201
    contact: dict[str, Any] = response.json()
    job = await _create_job(client, tenant["id"], contact["id"])

    list_response = await client.get("/jobs", headers={"X-Tenant-ID": tenant["id"]})
    assert list_response.status_code == 200
    listed = next(j for j in list_response.json() if j["id"] == job["id"])
    assert listed["customer"]["address"] == "10 Downing Street"
    assert listed["customer"]["postcode"] == "SW1A 2AA"

    get_response = await client.get(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert get_response.status_code == 200
    assert get_response.json()["customer"]["address"] == "10 Downing Street"
    assert get_response.json()["customer"]["postcode"] == "SW1A 2AA"


async def test_update_job_schedule(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Scheduler")
    job = await _create_job(client, tenant["id"], contact["id"])

    start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=2)
    response = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "scheduled_start": start.isoformat(),
            "scheduled_end": end.isoformat(),
            "notes": "Customer requested morning",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["notes"] == "Customer requested morning"
    assert data["scheduled_start"] is not None


async def test_start_job(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Starter")
    job = await _create_job(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/jobs/{job['id']}/start",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


async def test_complete_job(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Completer")
    job = await _create_job(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/jobs/{job['id']}/complete",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


async def test_cancel_job(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Canceller")
    job = await _create_job(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/jobs/{job['id']}/cancel",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_delete_job(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Deleter")
    job = await _create_job(client, tenant["id"], contact["id"])

    response = await client.delete(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 204

    get_response = await client.get(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert get_response.status_code == 404
