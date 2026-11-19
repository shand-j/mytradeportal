"""Tests for structured measurements on jobs (label/value pairs on the Job model)."""

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

MEASUREMENTS = [
    {"label": "Cable run", "value": "12 m"},
    {"label": "Consumer unit height", "value": "1.4 m"},
]


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
            "title": "Consumer unit replacement",
            "line_items": [
                {"description": "Labour", "quantity": "3", "unit": "hrs", "unit_price": "45.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _approve_quote(client: AsyncClient, tenant_id: str, quote_id: str) -> None:
    response = await client.post(
        f"/quotes/{quote_id}/approve",
        headers={"X-Tenant-ID": tenant_id},
        json={},
    )
    assert response.status_code == 200, response.text


async def test_create_job_with_measurements_round_trips(client: AsyncClient) -> None:
    """POST /jobs stores measurements; the response, GET and list return them."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Measured Create")

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board swap",
            "measurements": MEASUREMENTS,
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["measurements"] == MEASUREMENTS

    fetched = await client.get(f"/jobs/{job['id']}", headers={"X-Tenant-ID": tenant["id"]})
    assert fetched.status_code == 200
    assert fetched.json()["measurements"] == MEASUREMENTS

    listed = await client.get("/jobs", headers={"X-Tenant-ID": tenant["id"]})
    assert listed.status_code == 200
    listed_job = next(j for j in listed.json() if j["id"] == job["id"])
    assert listed_job["measurements"] == MEASUREMENTS


async def test_create_job_defaults_measurements_to_empty(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Measured Default")

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["measurements"] == []


async def test_update_job_measurements(client: AsyncClient) -> None:
    """PATCH /jobs/{id} replaces the measurements list and can clear it."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Measured Update")
    create_response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board swap",
            "measurements": MEASUREMENTS,
        },
    )
    assert create_response.status_code == 201, create_response.text
    job = create_response.json()

    updated_measurements = [*MEASUREMENTS, {"label": "Earthing conductor", "value": "16 mm²"}]
    patch_response = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"measurements": updated_measurements},
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["measurements"] == updated_measurements

    # Omitting the key leaves the list untouched.
    untouched = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"notes": "Still measured"},
    )
    assert untouched.status_code == 200, untouched.text
    assert untouched.json()["measurements"] == updated_measurements

    cleared = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"measurements": []},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["measurements"] == []


async def test_measurements_require_label_and_value(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Measured Invalid")

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board swap",
            "measurements": [{"label": "", "value": "12 m"}],
        },
    )
    assert response.status_code == 422

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board swap",
            "measurements": [{"label": "Cable run"}],
        },
    )
    assert response.status_code == 422


async def test_convert_quote_to_job_preserves_measurements(client: AsyncClient) -> None:
    """Measurements supplied at conversion land on the converted job."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Measured Convert")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"measurements": MEASUREMENTS},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["measurements"] == MEASUREMENTS

    fetched = await client.get(f"/jobs/{job['id']}", headers={"X-Tenant-ID": tenant["id"]})
    assert fetched.status_code == 200
    assert fetched.json()["measurements"] == MEASUREMENTS


async def test_convert_quote_to_job_defaults_measurements_to_empty(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Measured Convert Empty")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert response.status_code == 201, response.text
    assert response.json()["measurements"] == []
