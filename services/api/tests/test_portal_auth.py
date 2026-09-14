"""Tests for invisible (magic-link) customer auth and portal platform bits."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from app.limiter import limiter
from app.models import Contact, Customer, CustomerPortalToken, Invoice, Quote, Tenant
from app.portal_links import hash_portal_token, issue_portal_token, magic_link_url, portal_url
from app.rls import bypass_rls_in_session, set_tenant_in_session
from sqlalchemy import select, update

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    tenant = Tenant(slug=slug, name=f"{slug} Electrical")
    db.add(tenant)
    await db.flush()
    return tenant


async def _create_customer(db: AsyncSession, tenant: Tenant, email: str) -> Customer:
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Portal Pat", email=email)
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=email,
        full_name="Portal Pat",
    )
    db.add(customer)
    await db.flush()
    return customer


async def _exchange(client: AsyncClient, raw_token: str, **kwargs: Any) -> Any:
    return await client.post("/customer/auth/magic", json={"token": raw_token}, **kwargs)


async def test_portal_url_and_magic_link_shapes(db: AsyncSession) -> None:
    slug = f"portal-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    customer = await _create_customer(db, tenant, f"pat-{uuid4().hex[:6]}@example.com")

    assert portal_url(tenant, "/quotes") == f"https://{slug}.mytradeportal.co.uk/quotes"

    link = await magic_link_url(db, tenant, customer, "/quotes")
    assert link.startswith(f"https://{slug}.mytradeportal.co.uk/auth/magic?token=")
    assert link.endswith("&next=/quotes")


async def test_magic_token_round_trip(client: AsyncClient, db: AsyncSession) -> None:
    """A magic token exchanges for a customer JWT that works on the customer
    API but is rejected by the staff API (subject_type isolation)."""
    slug = f"portal-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"pat-{uuid4().hex[:6]}@example.com"
    customer = await _create_customer(db, tenant, email)
    raw = await issue_portal_token(db, customer)
    await db.commit()

    resp = await _exchange(client, raw, headers={"host": f"{slug}.localhost"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["customer"]["id"] == str(customer.id)
    assert body["customer"]["full_name"] == "Portal Pat"
    assert body["customer"]["email"] == email
    assert body["expires_at"]

    token = body["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    me = await client.get("/customer/me", headers=auth)
    assert me.status_code == 200
    assert me.json()["email"] == email

    # The same JWT must not authenticate against the staff API.
    staff = await client.get("/auth/me", headers=auth)
    assert staff.status_code == 401

    # The exchange stamps last_used_at on the token row.
    await bypass_rls_in_session(db)
    record = await db.scalar(
        select(CustomerPortalToken).where(CustomerPortalToken.token_hash == hash_portal_token(raw))
    )
    assert record is not None
    assert record.last_used_at is not None


async def test_magic_token_unknown_expired_uniform_401(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"portal-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    customer = await _create_customer(db, tenant, f"pat-{uuid4().hex[:6]}@example.com")
    raw = await issue_portal_token(db, customer)
    await db.execute(
        update(CustomerPortalToken)
        .where(CustomerPortalToken.token_hash == hash_portal_token(raw))
        .values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db.commit()

    unknown = await _exchange(client, "not-a-real-token")
    assert unknown.status_code == 401
    expired = await _exchange(client, raw)
    assert expired.status_code == 401
    assert unknown.json() == expired.json()


async def test_magic_reissue_revokes_previous_token(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"portal-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    customer = await _create_customer(db, tenant, f"pat-{uuid4().hex[:6]}@example.com")
    first = await issue_portal_token(db, customer)
    second = await issue_portal_token(db, customer)
    await db.commit()

    old = await _exchange(client, first)
    assert old.status_code == 401
    new = await _exchange(client, second)
    assert new.status_code == 200, new.text


async def test_magic_token_rejected_on_wrong_tenant_subdomain(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug_a = f"portal-{uuid4().hex[:8]}"
    tenant_a = await _create_tenant(db, slug_a)
    customer = await _create_customer(db, tenant_a, f"pat-{uuid4().hex[:6]}@example.com")
    slug_b = f"portal-{uuid4().hex[:8]}"
    await _create_tenant(db, slug_b)
    raw = await issue_portal_token(db, customer)
    await db.commit()

    wrong = await _exchange(client, raw, headers={"host": f"{slug_b}.localhost"})
    assert wrong.status_code == 401
    right = await _exchange(client, raw, headers={"host": f"{slug_a}.localhost"})
    assert right.status_code == 200, right.text


async def test_magic_request_sends_email_when_customer_exists(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"portal-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"pat-{uuid4().hex[:6]}@example.com"
    await _create_customer(db, tenant, email)
    await db.commit()

    sent: list[dict[str, Any]] = []

    async def fake_send(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("app.routers.customer_portal.send_event_email", fake_send)

    resp = await client.post(
        "/customer/auth/magic/request",
        headers={"host": f"{slug}.localhost"},
        json={"email": email},
    )
    assert resp.status_code == 202, resp.text
    assert "sign-in link" in resp.json()["detail"]
    assert len(sent) == 1
    assert sent[0]["to_email"] == email

    # The emailed link carries a working magic token.
    match = re.search(r"token=([^&\"]+)", sent[0]["html_body"])
    assert match, sent[0]["html_body"]
    consume = await _exchange(client, match.group(1), headers={"host": f"{slug}.localhost"})
    assert consume.status_code == 200, consume.text


async def test_magic_request_silent_for_unknown_email(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"portal-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    await db.commit()

    sent: list[dict[str, Any]] = []

    async def fake_send(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("app.routers.customer_portal.send_event_email", fake_send)

    resp = await client.post(
        "/customer/auth/magic/request",
        headers={"host": f"{slug}.localhost"},
        json={"email": f"nobody-{uuid4().hex[:6]}@example.com"},
    )
    # Identical generic response; no email fired, no account leaked.
    assert resp.status_code == 202, resp.text
    assert "sign-in link" in resp.json()["detail"]
    assert sent == []


async def _auth_headers_via_magic(
    client: AsyncClient, db: AsyncSession, customer: Customer
) -> dict[str, str]:
    raw = await issue_portal_token(db, customer)
    await db.commit()
    resp = await _exchange(client, raw)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_sent_quote(db: AsyncSession, tenant: Tenant, customer: Customer) -> Quote:
    await set_tenant_in_session(db, tenant.id)
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=customer.contact_id,
        title="Fuse board upgrade",
        status="sent",
        subtotal=Decimal("400.00"),
        vat_amount=Decimal("80.00"),
        total=Decimal("480.00"),
    )
    db.add(quote)
    await db.flush()
    return quote


async def test_accept_quote_preferred_dates_both_shapes(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The portal client sends [{date: "YYYY-MM-DD"}]; the app sends plain
    strings. Both must map onto the same accepted_dates storage."""
    slug = f"portal-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    customer = await _create_customer(db, tenant, f"pat-{uuid4().hex[:6]}@example.com")
    auth = await _auth_headers_via_magic(client, db, customer)

    quote = await _create_sent_quote(db, tenant, customer)
    await db.commit()
    resp = await client.post(
        f"/customer/quotes/{quote.id}/accept",
        headers=auth,
        json={"preferred_dates": [{"date": "2026-09-20"}, {"date": "2026-09-21"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted_dates"] == ["2026-09-20", "2026-09-21"]

    other = await _create_sent_quote(db, tenant, customer)
    await db.commit()
    resp = await client.post(
        f"/customer/quotes/{other.id}/accept",
        headers=auth,
        json={"preferred_dates": ["Fri 12 Sep"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted_dates"] == ["Fri 12 Sep"]


async def test_portal_invoice_payment_url_null_without_stripe(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without Stripe configured the invoice detail still renders with a null
    payment_url (no Pay hand-off)."""
    monkeypatch.setattr("app.stripe_client.is_configured", lambda: False)

    slug = f"portal-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    customer = await _create_customer(db, tenant, f"pat-{uuid4().hex[:6]}@example.com")
    auth = await _auth_headers_via_magic(client, db, customer)

    await set_tenant_in_session(db, tenant.id)
    invoice = Invoice(
        tenant_id=tenant.id,
        contact_id=customer.contact_id,
        invoice_number=f"INV-{uuid4().hex[:6].upper()}",
        status="sent",
        subtotal=Decimal("100.00"),
        vat_rate=Decimal("20.00"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
        issue_date=datetime.utcnow(),
    )
    db.add(invoice)
    await db.commit()

    resp = await client.get(f"/customer/invoices/{invoice.id}", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_url"] is None


async def test_reserved_slugs_rejected_on_tenant_create(
    client: AsyncClient, db: AsyncSession
) -> None:
    for reserved in ("www", "api", "portal", "pay"):
        resp = await client.post("/tenants", json={"slug": reserved, "name": "Reserved Ltd"})
        assert resp.status_code == 409, (reserved, resp.text)
        assert "reserved" in resp.json()["detail"]

    slug = f"real-{uuid4().hex[:8]}"
    ok = await client.post("/tenants", json={"slug": slug, "name": "Real Ltd"})
    assert ok.status_code == 201, ok.text


@pytest.fixture()
def _enable_rate_limiter() -> Iterator[None]:
    """Re-enable the limiter for these tests and clear its in-memory buckets."""
    previous = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()
        limiter.enabled = previous


async def test_magic_exchange_rate_limited(
    client: AsyncClient, db: AsyncSession, _enable_rate_limiter: None
) -> None:
    """The 11th rapid magic-token exchange from one IP must return 429."""
    for _ in range(10):
        resp = await _exchange(client, "not-a-real-token")
        assert resp.status_code == 401, resp.text
    eleventh = await _exchange(client, "not-a-real-token")
    assert eleventh.status_code == 429, eleventh.text


async def test_magic_request_rate_limited(
    client: AsyncClient, db: AsyncSession, _enable_rate_limiter: None
) -> None:
    """The 6th magic-link request from one IP within an hour must return 429."""
    slug = f"portal-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    await db.commit()
    headers = {"host": f"{slug}.localhost"}
    payload = {"email": f"pat-{uuid4().hex[:6]}@example.com"}

    for _ in range(5):
        resp = await client.post("/customer/auth/magic/request", headers=headers, json=payload)
        assert resp.status_code == 202, resp.text
    sixth = await client.post("/customer/auth/magic/request", headers=headers, json=payload)
    assert sixth.status_code == 429, sixth.text
