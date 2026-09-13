"""Tests for the customer (homeowner) invoice endpoints.

The customer sees only their own sent/paid/overdue invoices — never drafts,
never other customers' or tenants' invoices — and can request a Paddle
checkout URL to pay one.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.models import Contact, Customer, Invoice, InvoiceLineItem, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    tenant = Tenant(slug=slug, name=f"{slug} Electrical")
    db.add(tenant)
    await db.flush()
    return tenant


async def _create_customer(
    db: AsyncSession, tenant: Tenant, email: str, password: str = "homeowner-pass-123"
) -> Customer:
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Homeowner Jane", email=email)
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=email,
        full_name="Homeowner Jane",
        password_hash=get_password_hash(password),
    )
    db.add(customer)
    await db.commit()
    return customer


async def _login(client: AsyncClient, slug: str, email: str) -> dict[str, str]:
    resp = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email, "password": "homeowner-pass-123"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['accessToken']}"}


async def _create_invoice(
    db: AsyncSession,
    tenant: Tenant,
    customer: Customer,
    *,
    status: str = "sent",
    invoice_number: str | None = None,
) -> Invoice:
    await set_tenant_in_session(db, tenant.id)
    invoice = Invoice(
        tenant_id=tenant.id,
        contact_id=customer.contact_id,
        invoice_number=invoice_number or f"INV-{uuid4().hex[:6].upper()}",
        status=status,
        subtotal=Decimal("100.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
        notes="Consumer unit replacement",
    )
    db.add(invoice)
    await db.flush()
    db.add(
        InvoiceLineItem(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            description="Supply and fit consumer unit",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            total=Decimal("100.00"),
        )
    )
    await db.commit()
    return invoice


async def _setup(client: AsyncClient, db: AsyncSession) -> tuple[Tenant, Customer, dict[str, str]]:
    slug = f"custinv-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"jane-{uuid4().hex[:6]}@example.com"
    customer = await _create_customer(db, tenant, email)
    auth = await _login(client, slug, email)
    return tenant, customer, auth


async def test_list_returns_only_own_visible_invoices(
    client: AsyncClient, db: AsyncSession
) -> None:
    tenant, customer, auth = await _setup(client, db)

    sent = await _create_invoice(db, tenant, customer, status="sent")
    paid = await _create_invoice(db, tenant, customer, status="paid")
    overdue = await _create_invoice(db, tenant, customer, status="overdue")
    await _create_invoice(db, tenant, customer, status="draft")
    await _create_invoice(db, tenant, customer, status="cancelled")

    resp = await client.get("/customer/invoices", headers=auth)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    returned_ids = {row["id"] for row in rows}
    assert returned_ids == {str(sent.id), str(paid.id), str(overdue.id)}
    assert {row["status"] for row in rows} == {"sent", "paid", "overdue"}


async def test_list_excludes_other_customers_and_tenants(
    client: AsyncClient, db: AsyncSession
) -> None:
    tenant, customer, auth = await _setup(client, db)
    own = await _create_invoice(db, tenant, customer, status="sent")

    # Another customer of the same business.
    other = await _create_customer(db, tenant, f"other-{uuid4().hex[:6]}@example.com")
    await _create_invoice(db, tenant, other, status="sent")

    # Another tenant entirely.
    other_tenant = await _create_tenant(db, f"other-{uuid4().hex[:8]}")
    other_tenant_customer = await _create_customer(
        db, other_tenant, f"stranger-{uuid4().hex[:6]}@example.com"
    )
    await _create_invoice(db, other_tenant, other_tenant_customer, status="sent")

    resp = await client.get("/customer/invoices", headers=auth)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [row["id"] for row in rows] == [str(own.id)]


async def test_detail_shape_includes_line_items_and_branding(
    client: AsyncClient, db: AsyncSession
) -> None:
    tenant, customer, auth = await _setup(client, db)
    invoice = await _create_invoice(db, tenant, customer, status="sent")

    resp = await client.get(f"/customer/invoices/{invoice.id}", headers=auth)
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    assert body["id"] == str(invoice.id)
    assert body["invoice_number"] == invoice.invoice_number
    assert body["status"] == "sent"
    assert body["total"] == "120.00"
    assert body["vat_amount"] == "20.00"
    assert body["notes"] == "Consumer unit replacement"
    assert body["business_name"] == tenant.name
    assert "business_logo_url" in body
    assert body["business_primary_color"]
    assert len(body["line_items"]) == 1
    line = body["line_items"][0]
    assert line["description"] == "Supply and fit consumer unit"
    # Line money columns are Numeric(12, 4) — compare as decimals, not strings.
    assert Decimal(line["unit_price"]) == Decimal("100.00")
    assert Decimal(line["total"]) == Decimal("100.00")
    # Staff internals must not leak to the homeowner payload.
    assert "paddle_checkout_id" not in body
    assert "tenant_id" not in body


async def test_detail_404s_for_draft_and_other_tenants_invoice(
    client: AsyncClient, db: AsyncSession
) -> None:
    tenant, customer, auth = await _setup(client, db)
    draft = await _create_invoice(db, tenant, customer, status="draft")

    resp = await client.get(f"/customer/invoices/{draft.id}", headers=auth)
    assert resp.status_code == 404

    other_tenant = await _create_tenant(db, f"other-{uuid4().hex[:8]}")
    other_customer = await _create_customer(
        db, other_tenant, f"stranger-{uuid4().hex[:6]}@example.com"
    )
    foreign = await _create_invoice(db, other_tenant, other_customer, status="sent")

    resp = await client.get(f"/customer/invoices/{foreign.id}", headers=auth)
    assert resp.status_code == 404

    resp = await client.get(f"/customer/invoices/{uuid4()}", headers=auth)
    assert resp.status_code == 404


async def test_invoices_require_customer_token(client: AsyncClient) -> None:
    resp = await client.get("/customer/invoices")
    assert resp.status_code == 401


async def test_pay_returns_checkout_url(client: AsyncClient, db: AsyncSession) -> None:
    tenant, customer, auth = await _setup(client, db)
    invoice = await _create_invoice(db, tenant, customer, status="sent")

    fake = AsyncMock(
        return_value={"checkout_id": "chkt_test_1", "checkout_url": "https://pay.paddle.com/x"}
    )
    with patch("app.routers.customer_portal.create_checkout", new=fake):
        resp = await client.post(f"/customer/invoices/{invoice.id}/pay", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checkout_url"] == "https://pay.paddle.com/x"
    assert body["checkout_id"] == "chkt_test_1"

    # The checkout was created for this invoice with the customer's email.
    args, kwargs = fake.call_args
    assert args[0].id == invoice.id
    assert kwargs["customer_email"] == customer.email


async def test_pay_rejects_paid_and_foreign_invoices(client: AsyncClient, db: AsyncSession) -> None:
    tenant, customer, auth = await _setup(client, db)
    paid = await _create_invoice(db, tenant, customer, status="paid")

    fake = AsyncMock(
        return_value={"checkout_id": "chkt_test_1", "checkout_url": "https://pay.paddle.com/x"}
    )
    with patch("app.routers.customer_portal.create_checkout", new=fake):
        resp = await client.post(f"/customer/invoices/{paid.id}/pay", headers=auth)
        assert resp.status_code == 400

        other_tenant = await _create_tenant(db, f"other-{uuid4().hex[:8]}")
        other_customer = await _create_customer(
            db, other_tenant, f"stranger-{uuid4().hex[:6]}@example.com"
        )
        foreign = await _create_invoice(db, other_tenant, other_customer, status="sent")
        resp = await client.post(f"/customer/invoices/{foreign.id}/pay", headers=auth)
        assert resp.status_code == 404

    fake.assert_not_called()


async def test_pay_bubbles_paddle_failure_as_502(client: AsyncClient, db: AsyncSession) -> None:
    tenant, customer, auth = await _setup(client, db)
    invoice = await _create_invoice(db, tenant, customer, status="sent")

    fake = AsyncMock(side_effect=RuntimeError("paddle 500"))
    with patch("app.routers.customer_portal.create_checkout", new=fake):
        resp = await client.post(f"/customer/invoices/{invoice.id}/pay", headers=auth)
    assert resp.status_code == 502
