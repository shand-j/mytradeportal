"""Tests for communication log endpoints."""

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


async def test_create_and_list_communications(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"comm-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Comm Customer")

    response = await client.post(
        "/communications",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "channel": "email",
            "subject": "Quote follow-up",
            "body": "Here is your quote.",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["channel"] == "email"
    assert data["tenant_id"] == tenant["id"]

    list_response = await client.get("/communications", headers={"X-Tenant-ID": tenant["id"]})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_communication_requires_valid_contact(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"comm-{uuid4().hex[:8]}")
    response = await client.post(
        "/communications",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": str(uuid4()), "channel": "sms", "body": "Hello"},
    )
    assert response.status_code == 400
