"""Tests for the homeowner (customer) portal: register, login, history."""

from uuid import uuid4

from app.models import Tenant
from app.rls import bypass_rls_in_session
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    tenant = Tenant(slug=slug, name=f"{slug} Electrical")
    db.add(tenant)
    await db.flush()
    return tenant


def _register_payload(slug: str, email: str) -> dict[str, object]:
    return {
        "slug": slug,
        "full_name": "Homeowner Jane",
        "email": email,
        "phone": "07700 900888",
        "password": "homeowner-pass-123",
    }


async def test_register_returns_token_and_customer(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"cust-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)

    email = f"jane-{uuid4().hex[:6]}@example.com"
    resp = await client.post("/customer/register", json=_register_payload(slug, email))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["accessToken"]
    assert body["customer"]["email"] == email
    assert body["customer"]["full_name"] == "Homeowner Jane"

    # The token authorises /customer/me.
    token = body["accessToken"]
    me = await client.get("/customer/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


async def test_login_after_register(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"cust-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    await client.post("/customer/register", json=_register_payload(slug, email))

    login = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email, "password": "homeowner-pass-123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["accessToken"]

    bad = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email, "password": "not-the-password"},
    )
    assert bad.status_code == 401


async def test_duplicate_register_conflicts(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"cust-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    first = await client.post("/customer/register", json=_register_payload(slug, email))
    assert first.status_code == 201
    second = await client.post("/customer/register", json=_register_payload(slug, email))
    assert second.status_code == 409


async def test_submission_links_to_logged_in_customer(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    token = reg.json()["accessToken"]
    auth = {"Authorization": f"Bearer {token}"}

    # Submit a request while authenticated -> should link to the customer.
    submit = await client.post(
        f"/businesses/{slug}/quote-requests",
        headers=auth,
        json={
            "contact": {"name": "Homeowner Jane", "email": email},
            "category": "eicr",
            "title": "My linked EICR",
        },
    )
    assert submit.status_code == 201, submit.text

    # The customer sees it in their history.
    history = await client.get("/customer/quote-requests", headers=auth)
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["structured_data"]["title"] == "My linked EICR"

    # The tradesperson also sees it as a lead (linked to the customer).
    staff = await client.get("/quote-requests", headers={"X-Tenant-ID": str(tenant.id)})
    assert staff.status_code == 200
    leads = staff.json()
    assert any(lead["customer_id"] is not None for lead in leads)


async def test_customer_token_rejected_by_staff_api(client: AsyncClient, db: AsyncSession) -> None:
    """A customer token must not authenticate against the staff user API."""
    slug = f"cust-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    token = reg.json()["accessToken"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401


async def test_me_requires_customer_token(client: AsyncClient) -> None:
    resp = await client.get("/customer/me")
    assert resp.status_code == 401
