"""Tests for review endpoints."""

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


async def _create_review(
    client: AsyncClient,
    tenant_id: str,
    contact_id: str,
    rating: int,
) -> dict[str, Any]:
    response = await client.post(
        "/reviews",
        headers={"X-Tenant-ID": tenant_id},
        json={"contact_id": contact_id, "rating": rating, "comment": "Great service"},
    )
    assert response.status_code == 201
    return response.json()


async def test_create_and_list_reviews(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"review-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Reviewer")
    review = await _create_review(client, tenant["id"], contact["id"], 5)

    assert review["rating"] == 5
    assert review["status"] == "pending"

    list_response = await client.get("/reviews", headers={"X-Tenant-ID": tenant["id"]})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_review_stats(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"review-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Stats Reviewer")
    await _create_review(client, tenant["id"], contact["id"], 5)
    await _create_review(client, tenant["id"], contact["id"], 3)

    response = await client.get("/reviews/stats", headers={"X-Tenant-ID": tenant["id"]})
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert data["average_rating"] == 4.0
    assert data["pending_count"] == 2


async def test_review_requires_valid_contact(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"review-{uuid4().hex[:8]}")
    response = await client.post(
        "/reviews",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": str(uuid4()), "rating": 5},
    )
    assert response.status_code == 400
