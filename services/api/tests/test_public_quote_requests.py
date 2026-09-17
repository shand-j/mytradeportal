"""Tests for the public (unauthenticated) quote-request submission endpoint."""

from uuid import uuid4

from app.models import Contact, Tenant
from app.rls import bypass_rls_in_session
from app.utils.tenant_code import generate_unique_tenant_code
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    code = await generate_unique_tenant_code(db)
    tenant = Tenant(slug=slug, code=code, name=f"{slug} Electrical")
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
    assert tenant is not None
    listing = await client.get(
        "/quote-requests",
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    rows = listing.json()
    # Two requests, but both link to the same contact (deduplicated by email).
    assert len(rows) == 2
    contact_ids = {row["contact_id"] for row in rows}
    assert len(contact_ids) == 1


async def test_public_submission_blocked_contact_is_rejected(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    db.add(
        Contact(
            tenant_id=tenant.id,
            name="Blocked Homeowner",
            email="blocked@example.com",
            is_blocked=True,
        )
    )
    await db.flush()

    response = await client.post(
        f"/businesses/{slug}/quote-requests",
        json={
            "contact": {"name": "Blocked Homeowner", "email": "blocked@example.com"},
            "category": "consumer_unit",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"].startswith("customer_blocked:")

    # No quote request was created for the blocked contact.
    listing = await client.get("/quote-requests", headers={"X-Tenant-ID": str(tenant.id)})
    assert listing.json() == []


async def test_public_submission_unblocked_contact_still_works(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    db.add(
        Contact(
            tenant_id=tenant.id,
            name="Unblocked Homeowner",
            email="unblocked@example.com",
            is_blocked=False,
        )
    )
    await db.flush()

    response = await client.post(
        f"/businesses/{slug}/quote-requests",
        json={
            "contact": {"name": "Unblocked Homeowner", "email": "unblocked@example.com"},
            "category": "consumer_unit",
        },
    )
    assert response.status_code == 201, response.text


async def test_public_submission_unknown_business_is_404(client: AsyncClient) -> None:
    response = await client.post(
        "/businesses/does-not-exist/quote-requests",
        json={"contact": {"name": "Nobody"}},
    )
    assert response.status_code == 404


async def test_public_config_by_code_returns_tenant(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"code-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    assert tenant.code is not None

    response = await client.get(f"/businesses/by-code/{tenant.code}/public-config")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["slug"] == slug
    assert data["code"] == tenant.code
    assert data["name"] == tenant.name


async def test_public_config_by_code_unknown_is_404(client: AsyncClient) -> None:
    response = await client.get("/businesses/by-code/000000/public-config")
    assert response.status_code == 404
