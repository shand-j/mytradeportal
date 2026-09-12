"""Tests for the homeowner (customer) portal: register, login, history."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.models import Contact, Notification, Quote, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
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
    lead_before = next(lead for lead in staff_before.json() if lead["id"] == quote_request_id)
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
    lead_after = next(lead for lead in staff_after.json() if lead["id"] == quote_request_id)
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


async def test_register_does_not_poach_lead_whose_email_is_another_customer(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A lead whose contact email is a registered customer's must not be
    claimed by a different account on phone match alone (repeat registration
    with a new email + same phone was surfacing the earlier quote request in
    the new account)."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    email_a = f"alice-{uuid4().hex[:6]}@example.com"
    payload_a = _register_payload(slug, email_a)
    payload_a["phone"] = "07700 900111"
    reg_a = await client.post("/customer/register", json=payload_a)
    assert reg_a.status_code == 201, reg_a.text

    # Lead captured with A's email but a phone that B will register with.
    _, lead = await _seed_lead(db, tenant, contact_email=email_a, contact_phone="07700 900222")

    email_b = f"bob-{uuid4().hex[:6]}@example.com"
    payload_b = _register_payload(slug, email_b)
    payload_b["phone"] = "07700 900222"
    reg_b = await client.post("/customer/register", json=payload_b)
    assert reg_b.status_code == 201, reg_b.text

    await db.refresh(lead)
    # Phone matches B but the email belongs to A — B must not see it.
    assert lead.customer_id is None

    # A claims it on login via the email match.
    login_a = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email_a, "password": "homeowner-pass-123"},
    )
    assert login_a.status_code == 200, login_a.text
    await set_tenant_in_session(db, tenant.id)
    await db.refresh(lead)
    assert str(lead.customer_id) == reg_a.json()["customer"]["id"]


async def test_accept_quote_reconfirms_preferred_dates(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Acceptance with preferred_dates persists them on the quote so the
    electrician sees them at job conversion."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    contact, lead = await _seed_lead(
        db, tenant, contact_email="pat@example.com", contact_phone=None
    )
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="Recessed lighting",
        status="sent",
        quote_request_id=lead.id,
        subtotal=Decimal("400.00"),
        vat_amount=Decimal("80.00"),
        total=Decimal("480.00"),
    )
    db.add(quote)
    await db.flush()

    reg = await client.post("/customer/register", json=_register_payload(slug, "pat@example.com"))
    assert reg.status_code == 201, reg.text
    auth = {"Authorization": f"Bearer {reg.json()['accessToken']}"}

    response = await client.post(
        f"/customer/quotes/{quote.id}/accept",
        headers=auth,
        json={"preferred_dates": ["Fri 12 Sep", "Mon 15 Sep"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["accepted_dates"] == ["Fri 12 Sep", "Mon 15 Sep"]

    # The staff notification deep-links to the quote detail screen.
    await set_tenant_in_session(db, tenant.id)
    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant.id,
            Notification.type == "quote_accepted",
        )
    )
    assert notification is not None
    assert notification.link == f"/quotes/{quote.id}"


async def test_draft_quote_hidden_until_electrician_sends(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Customers must not see line items for a quote the electrician is still
    reviewing — the request shows as awaiting review and detail 404s."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    assert reg.status_code == 201, reg.text
    token = reg.json()["accessToken"]
    customer_id = reg.json()["customer"]["id"]

    await set_tenant_in_session(db, tenant.id)
    contact = await db.scalar(
        select(Contact).where(Contact.tenant_id == tenant.id, Contact.email == email)
    )
    assert contact is not None
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="Socket installation",
        status="draft",
    )
    db.add(quote)
    await db.flush()
    quote_request = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        customer_id=customer_id,
        quote_id=quote.id,
        source="app",
        raw_text="New sockets",
    )
    db.add(quote_request)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    history = await client.get("/customer/quote-requests", headers=headers)
    assert history.status_code == 200, history.text
    entry = history.json()[0]
    assert entry["quote"] is None

    # Accepting a draft is refused: the quote is not findable while pending.
    accept = await client.post(f"/customer/quotes/{quote.id}/accept", headers=headers)
    assert accept.status_code == 404

    # Once sent, the quote becomes visible.
    await set_tenant_in_session(db, tenant.id)
    quote.status = "sent"
    quote.sent_at = datetime.utcnow()
    await db.commit()
    sent_history = await client.get("/customer/quote-requests", headers=headers)
    assert sent_history.json()[0]["quote"] is not None
    sent_accept = await client.post(f"/customer/quotes/{quote.id}/accept", headers=headers)
    assert sent_accept.status_code == 200


async def test_register_reuses_existing_contact(client: AsyncClient, db: AsyncSession) -> None:
    """Registering must not fork a duplicate contact for a lead's email."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"

    await set_tenant_in_session(db, tenant.id)
    existing = Contact(
        tenant_id=tenant.id,
        name="Lead Jane",
        email=email,
        phone="07700 900888",
        address="1 High Street",
        postcode="M1 2AB",
    )
    db.add(existing)
    await db.commit()

    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    assert reg.status_code == 201, reg.text

    await bypass_rls_in_session(db)
    contacts = (
        (await db.execute(select(Contact).where(Contact.tenant_id == tenant.id))).scalars().all()
    )
    assert len(contacts) == 1
    assert contacts[0].id == existing.id


async def test_contact_has_account_flag(client: AsyncClient, db: AsyncSession) -> None:
    """Contacts expose has_account so staff can see comms expectations."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    assert reg.status_code == 201

    await set_tenant_in_session(db, tenant.id)
    db.add(Contact(tenant_id=tenant.id, name="No Account Lead", email="lead@example.com"))
    await db.commit()

    # Staff view: the registered contact is flagged, the bare lead is not.
    password = "admin-password-123"
    from app.models import User
    from app.security import get_password_hash

    await set_tenant_in_session(db, tenant.id)
    db.add(
        User(
            tenant_id=tenant.id,
            email="owner@test.local",
            full_name="Owner",
            role="admin",
            password_hash=get_password_hash(password),
            is_active=True,
        )
    )
    await db.commit()
    login = await client.post(
        "/auth/login",
        headers={"host": f"{slug}.localhost"},
        json={"email": "owner@test.local", "password": password},
    )
    assert login.status_code == 200, login.text
    response = await client.get("/contacts", headers={"X-Tenant-ID": str(tenant.id)})
    assert response.status_code == 200
    flags = {c["email"]: c["has_account"] for c in response.json()}
    assert flags[email] is True
    assert flags["lead@example.com"] is False


async def test_quote_visibility_allow_list_hides_unlisted_statuses(
    client: AsyncClient, db: AsyncSession
) -> None:
    """C3: customer quote visibility is a positive allow-list — a quote in any
    pre-send state (draft or a future "in_review") is hidden everywhere, while
    terminal states the customer took part in (e.g. invoiced) stay visible."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    assert reg.status_code == 201, reg.text
    token = reg.json()["accessToken"]
    customer_id = reg.json()["customer"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    await set_tenant_in_session(db, tenant.id)
    contact = await db.scalar(
        select(Contact).where(Contact.tenant_id == tenant.id, Contact.email == email)
    )
    assert contact is not None
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="Socket installation",
        status="in_review",  # hypothetical future pre-send state
    )
    db.add(quote)
    await db.flush()
    db.add(
        QuoteRequest(
            tenant_id=tenant.id,
            contact_id=contact.id,
            customer_id=customer_id,
            quote_id=quote.id,
            source="app",
            raw_text="New sockets",
        )
    )
    await db.commit()

    # Hidden from the history embed, the quotes list and the action endpoints.
    history = await client.get("/customer/quote-requests", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()[0]["quote"] is None
    quotes = await client.get("/customer/quotes", headers=headers)
    assert quotes.status_code == 200, quotes.text
    assert quotes.json() == []
    accept = await client.post(f"/customer/quotes/{quote.id}/accept", headers=headers)
    assert accept.status_code == 404

    # Terminal states the customer participated in stay visible (an accepted
    # quote that was converted to an invoice must not vanish from the portal).
    await set_tenant_in_session(db, tenant.id)
    quote.status = "invoiced"
    await db.commit()
    history = await client.get("/customer/quote-requests", headers=headers)
    assert history.json()[0]["quote"]["status"] == "invoiced"
    quotes = await client.get("/customer/quotes", headers=headers)
    assert [q["id"] for q in quotes.json()] == [str(quote.id)]


async def test_register_response_includes_current_tenant_association(
    client: AsyncClient, db: AsyncSession
) -> None:
    """C12: register returns the tenant association list (single entry)."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    reg = await client.post(
        "/customer/register", json=_register_payload(slug, f"jane-{uuid4().hex[:6]}@example.com")
    )
    assert reg.status_code == 201, reg.text
    tenants = reg.json()["tenants"]
    assert len(tenants) == 1
    assert tenants[0]["slug"] == slug
    assert tenants[0]["tenant_id"] == str(tenant.id)
    assert tenants[0]["name"] == tenant.name
    assert tenants[0]["is_current"] is True


async def test_login_resolves_tenant_post_auth_and_lists_associations(
    client: AsyncClient, db: AsyncSession
) -> None:
    """C12: login needs no business selection — email+password auth first,
    tenant resolved from the account afterwards (newest active account wins),
    and every active tenant association rides on the response."""
    from app.models import Customer
    from app.security import get_password_hash

    slug_a = f"cust-{uuid4().hex[:8]}"
    slug_b = f"cust-{uuid4().hex[:8]}"
    await _create_tenant(db, slug_a)
    tenant_b = await _create_tenant(db, slug_b)
    email = f"jane-{uuid4().hex[:6]}@example.com"

    # Older account at tenant A via the public register endpoint.
    reg = await client.post("/customer/register", json=_register_payload(slug_a, email))
    assert reg.status_code == 201, reg.text

    # Newer account for the same email at tenant B (duplicate emails across
    # tenants are allowed — resolution must pick the newest).
    await set_tenant_in_session(db, tenant_b.id)
    db.add(
        Customer(
            tenant_id=tenant_b.id,
            email=email,
            full_name="Homeowner Jane",
            password_hash=get_password_hash("homeowner-pass-123"),
            is_active=True,
        )
    )
    await db.commit()

    # No slug supplied: the mobile app authenticates tenant-agnostically.
    login = await client.post(
        "/customer/login", json={"email": email, "password": "homeowner-pass-123"}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["customer"]["tenant_id"] == str(tenant_b.id)
    tenants = {entry["slug"]: entry for entry in body["tenants"]}
    assert set(tenants) == {slug_a, slug_b}
    assert tenants[slug_a]["is_current"] is False
    assert tenants[slug_b]["is_current"] is True

    # Wrong password reveals nothing (no tenant list, generic 401).
    bad = await client.post("/customer/login", json={"email": email, "password": "nope-nope-123"})
    assert bad.status_code == 401
    assert "tenants" not in bad.json()


async def test_quote_to_accountless_contact_persists_flagged_unregistered(
    client: AsyncClient, db: AsyncSession
) -> None:
    """C4: a quote sent to a contact with no account persists on the lead and
    reads back with has_account=False (email-only comms); once the homeowner
    registers with the same email, the same staff read flips to True."""
    slug = f"cust-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"lead-{uuid4().hex[:6]}@example.com"

    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Accountless Lead", email=email)
    db.add(contact)
    await db.flush()
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="EV charger install",
        status="sent",
        sent_at=datetime.utcnow(),
    )
    db.add(quote)
    await db.flush()
    quote_request = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        quote_id=quote.id,
        source="app",
        raw_text="EV charger on the driveway",
    )
    db.add(quote_request)

    # Staff session for the tenant.
    from app.models import User
    from app.security import get_password_hash

    password = "admin-password-123"
    db.add(
        User(
            tenant_id=tenant.id,
            email="owner@test.local",
            full_name="Owner",
            role="admin",
            password_hash=get_password_hash(password),
            is_active=True,
        )
    )
    await db.commit()
    login = await client.post(
        "/auth/login",
        headers={"host": f"{slug}.localhost"},
        json={"email": "owner@test.local", "password": password},
    )
    assert login.status_code == 200, login.text

    async def _lead_entry() -> dict[str, Any]:
        response = await client.get("/quote-requests", headers={"X-Tenant-ID": str(tenant.id)})
        assert response.status_code == 200, response.text
        return next(row for row in response.json() if row["id"] == str(quote_request.id))

    entry = await _lead_entry()
    # Quote + contact persist even though the customer never signed up…
    assert entry["quote"] is not None
    assert entry["quote"]["status"] == "sent"
    assert entry["customer"]["email"] == email
    # …and the unregistered flag tells the electrician comms are email-only.
    assert entry["customer"]["has_account"] is False

    # Homeowner registers with the same email → flag flips on the same read.
    reg = await client.post("/customer/register", json=_register_payload(slug, email))
    assert reg.status_code == 201, reg.text
    entry = await _lead_entry()
    assert entry["customer"]["has_account"] is True
