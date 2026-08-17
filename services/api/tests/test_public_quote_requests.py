"""Tests for the public (unauthenticated) quote-request submission endpoint."""

from uuid import uuid4

from app.models import Tenant
from app.rls import bypass_rls_in_session
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    tenant = Tenant(slug=slug, name=f"{slug} Electrical")
    db.add(tenant)
    await db.flush()
    return tenant


async def test_public_submission_creates_lead_with_contact(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    response = await client.post(
        f"/businesses/{slug}/quote-requests",
        json={
            "contact": {
                "name": "Public Homeowner",
                "email": "homeowner@example.com",
                "phone": "07700 900777",
                "postcode": "SK8 3NJ",
            },
            "category": "consumer_unit",
            "title": "Consumer unit upgrade",
            "urgency": "this_week",
        },
    )
    assert response.status_code == 201, response.text
    ack = response.json()
    assert ack["status"] == "pending"
    assert ack["reference"]

    # The request shows up in the tenant's leads list with the linked contact.
    listing = await client.get(
        "/quote-requests",
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert len(rows) == 1
    lead = rows[0]
    assert lead["source"] == "app"
    assert lead["customer"]["name"] == "Public Homeowner"
    assert lead["customer"]["postcode"] == "SK8 3NJ"
    assert lead["structured_data"]["category"] == "consumer_unit"


async def test_public_submission_reuses_contact_by_email(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)

    payload = {
        "contact": {"name": "Repeat Homeowner", "email": "repeat@example.com"},
        "category": "ev_charger",
    }
    first = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    second = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201

    tenant = await db.scalar(select(Tenant).where(Tenant.slug == slug))
    listing = await client.get(
        "/quote-requests",
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    rows = listing.json()
    # Two requests, but both link to the same contact (deduplicated by email).
    assert len(rows) == 2
    contact_ids = {row["contact_id"] for row in rows}
    assert len(contact_ids) == 1


async def test_public_submission_unknown_business_is_404(client: AsyncClient) -> None:
    response = await client.post(
        "/businesses/does-not-exist/quote-requests",
        json={"contact": {"name": "Nobody"}},
    )
    assert response.status_code == 404
