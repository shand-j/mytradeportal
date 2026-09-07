"""Tests for authenticated quote request (lead) management endpoints."""

from uuid import uuid4

import pytest
from app.main import app
from app.models import Tenant, User
from app.security import get_password_hash
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _admin_client(base_client: AsyncClient, db: AsyncSession) -> tuple[AsyncClient, Tenant]:
    """Create a tenant + admin and authenticate a new client for that tenant."""
    tenant = Tenant(slug=f"lead-{uuid4().hex[:8]}", name="Lead Test Electrical")
    db.add(tenant)
    await db.flush()

    from app.rls import set_tenant_in_session

    await set_tenant_in_session(db, tenant.id)

    user = User(
        tenant_id=tenant.id,
        email=f"admin-{uuid4().hex[:6]}@leadtest.local",
        full_name="Lead Admin",
        role="admin",
        password_hash=get_password_hash("lead-admin-pass"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Use a fresh AsyncClient so auth state (cookies / tenant header) does not
    # leak between tenants.
    client = AsyncClient(transport=ASGITransport(app=app), base_url=base_client.base_url)
    response = await client.post(
        "/auth/login",
        headers={"host": f"{tenant.slug}.localhost"},
        json={"email": user.email, "password": "lead-admin-pass"},
    )
    assert response.status_code == 200
    client.headers["X-Tenant-ID"] = str(tenant.id)
    return client, tenant


@pytest.mark.asyncio
async def test_update_quote_request_merges_structured_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    """PATCH /quote-requests/{id} merges electrician intake into structured_data."""
    auth_client, tenant = await _admin_client(client, db)

    # Create a lead via the public endpoint.
    response = await client.post(
        f"/businesses/{tenant.slug}/quote-requests",
        json={
            "contact": {"name": "Lead Owner", "email": "owner@example.com", "postcode": "M1 1AA"},
            "category": "consumer_unit",
            "title": "Consumer unit upgrade",
            "raw_text": "Old fuse board keeps tripping",
        },
    )
    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]

    # Tradesperson reviews and adds intake details.
    response = await auth_client.patch(
        f"/quote-requests/{lead_id}",
        json={
            "structured_data": {
                "electricianIntake": {
                    "propertyType": "House",
                    "bedrooms": "3",
                    "cuLocation": "Kitchen",
                    "parking": "Driveway",
                    "access": "Key-safe code 1234",
                    "notes": "Customer has dogs",
                },
            },
            "status": "processed",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "processed"
    assert data["structured_data"]["electricianIntake"]["cuLocation"] == "Kitchen"
    # Original captured data should still be present.
    assert data["structured_data"]["category"] == "consumer_unit"


@pytest.mark.asyncio
async def test_update_quote_request_other_tenant_is_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A tenant cannot PATCH another tenant's lead."""
    first, _tenant = await _admin_client(client, db)

    # Create lead in first tenant.
    response = await first.post(
        "/quote-requests",
        json={
            "contact": {"name": "Lead Owner", "email": "owner@example.com"},
            "structured_data": {"category": "ev_charger"},
            "raw_text": "EV charger install",
        },
    )
    assert response.status_code == 201
    lead_id = response.json()["id"]

    # Second tenant tries to patch it.
    second, _tenant2 = await _admin_client(client, db)
    response = await second.patch(
        f"/quote-requests/{lead_id}",
        json={"structured_data": {"electricianIntake": {"propertyType": "Flat"}}},
    )
    assert response.status_code == 404
