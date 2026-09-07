"""Tests for the homeowner (customer) portal: register, login, history."""

from decimal import Decimal
from uuid import uuid4

from app.models import Contact, Quote, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
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


async def test_register_with_quote_request_id_links_request(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A guest who submitted a quote request can register and inherit it."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    # Guest submits a quote request.
    submit = await client.post(
        f"/businesses/{slug}/quote-requests",
        json={
            "contact": {"name": "Homeowner Jane", "email": "jane@example.com"},
            "category": "eicr",
            "title": "EICR needed",
        },
    )
    assert submit.status_code == 201, submit.text
    quote_request_id = submit.json()["id"]

    # The lead exists but is not yet linked to a customer account.
    staff_before = await client.get("/quote-requests", headers={"X-Tenant-ID": str(tenant.id)})
    assert staff_before.status_code == 200
    lead_before = [lead for lead in staff_before.json() if lead["id"] == quote_request_id][0]
    assert lead_before["customer_id"] is None

    # Register with the quote request id.
    email = f"jane-{uuid4().hex[:6]}@example.com"
    payload = _register_payload(slug, email)
    payload["quote_request_id"] = quote_request_id
    reg = await client.post("/customer/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["accessToken"]
    customer_id = reg.json()["customer"]["id"]

    # Staff sees the lead linked to the new customer.
    staff_after = await client.get("/quote-requests", headers={"X-Tenant-ID": str(tenant.id)})
    assert staff_after.status_code == 200
    lead_after = [lead for lead in staff_after.json() if lead["id"] == quote_request_id][0]
    assert lead_after["customer_id"] == customer_id

    # The quote request now belongs to the customer.
    history = await client.get(
        "/customer/quote-requests", headers={"Authorization": f"Bearer {token}"}
    )
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["id"] == quote_request_id
    assert rows[0]["customer_id"] == reg.json()["customer"]["id"]

    # The tradesperson sees the linkage as well.
    staff = await client.get("/quote-requests", headers={"X-Tenant-ID": str(tenant.id)})
    assert staff.status_code == 200
    leads = staff.json()
    linked = [lead for lead in leads if lead["id"] == quote_request_id]
    assert len(linked) == 1
    assert linked[0]["customer_id"] == reg.json()["customer"]["id"]


async def _seed_lead(
    db: AsyncSession,
    tenant: Tenant,
    *,
    contact_email: str | None,
    contact_phone: str | None,
) -> tuple[Contact, QuoteRequest]:
    """Create an electrician-captured lead (contact + quote request, unclaimed)."""
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(
        tenant_id=tenant.id,
        name="Captured Lead",
        email=contact_email,
        phone=contact_phone,
    )
    db.add(contact)
    await db.flush()
    lead = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        source="web_form",
        raw_text="Fuse board keeps tripping",
        structured_data={"category": "consumer_unit", "title": "Fuse board replacement"},
    )
    db.add(lead)
    await db.flush()
    return contact, lead


async def test_register_links_existing_lead_by_email(client: AsyncClient, db: AsyncSession) -> None:
    """Registering with an email matching a captured lead's contact claims it."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    contact, lead = await _seed_lead(
        db, tenant, contact_email="Jane.Doe@Example.com", contact_phone=None
    )

    # A sent quote generated from the lead keeps the electrician's contact.
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="Fuse board replacement",
        status="sent",
        quote_request_id=lead.id,
        subtotal=Decimal("480.00"),
        vat_amount=Decimal("96.00"),
        total=Decimal("576.00"),
    )
    db.add(quote)
    await db.flush()

    reg = await client.post(
        "/customer/register", json=_register_payload(slug, "jane.doe@example.com")
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["accessToken"]
    customer_id = reg.json()["customer"]["id"]
    auth = {"Authorization": f"Bearer {token}"}

    await set_tenant_in_session(db, tenant.id)
    await db.refresh(lead)
    assert str(lead.customer_id) == customer_id

    # The lead and its quote are now visible in the customer portal.
    history = await client.get("/customer/quote-requests", headers=auth)
    assert [row["id"] for row in history.json()] == [str(lead.id)]

    quotes = await client.get("/customer/quotes", headers=auth)
    assert quotes.status_code == 200, quotes.text
    assert [row["id"] for row in quotes.json()] == [str(quote.id)]


async def test_login_links_existing_lead_by_phone_digits(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Phone matching ignores formatting: digits-only comparison on login."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"

    # Customer registers before the lead exists — nothing to link yet.
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    assert reg.status_code == 201, reg.text

    # Electrician captures a lead with the same number, formatted differently
    # (and a different email so only the phone can match).
    _, lead = await _seed_lead(
        db, tenant, contact_email="someone-else@example.com", contact_phone="07700-900 888"
    )

    login = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email, "password": "homeowner-pass-123"},
    )
    assert login.status_code == 200, login.text

    await set_tenant_in_session(db, tenant.id)
    await db.refresh(lead)
    assert str(lead.customer_id) == reg.json()["customer"]["id"]


async def test_register_does_not_link_other_tenants_lead(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Matching is tenant-scoped: a lead at another business stays unclaimed."""
    email = f"jane-{uuid4().hex[:6]}@example.com"

    other_slug = f"cust-{uuid4().hex[:8]}"
    other_tenant = await _create_tenant(db, other_slug)
    _, foreign_lead = await _seed_lead(db, other_tenant, contact_email=email, contact_phone=None)

    slug = f"cust-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    assert reg.status_code == 201, reg.text

    await db.refresh(foreign_lead)
    assert foreign_lead.customer_id is None
