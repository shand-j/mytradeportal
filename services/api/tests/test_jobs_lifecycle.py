"""Tests for job lifecycle endpoints."""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    return response.json()


async def _create_contact(client: AsyncClient, tenant_id: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    return response.json()


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
    return response.json()


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
