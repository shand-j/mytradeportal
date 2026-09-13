"""Tests for the tenant data export endpoint (F3, GET /export/my-data)."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.models import (
    Communication,
    Contact,
    Customer,
    Invoice,
    InvoiceLineItem,
    Job,
    Quote,
    QuoteLineItem,
    Tenant,
)
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

EXPECTED_TOP_LEVEL_KEYS = {
    "format_version",
    "generated_at",
    "tenant",
    "contacts",
    "customers",
    "quotes",
    "jobs",
    "invoices",
    "communications",
}


def _tenant_id(admin_client: AsyncClient) -> UUID:
    return UUID(admin_client.headers["X-Tenant-ID"])


async def _seed_tenant_records(db: AsyncSession, tenant_id: UUID) -> dict[str, UUID]:
    """Create one of each exportable record for the tenant. Returns the ids."""
    contact = Contact(
        tenant_id=tenant_id,
        name="Amy Homeowner",
        email="amy@example.com",
        phone="07123456789",
        postcode="SW1A 1AA",
    )
    db.add(contact)
    await db.flush()

    customer = Customer(
        tenant_id=tenant_id,
        contact_id=contact.id,
        email="amy@example.com",
        full_name="Amy Homeowner",
    )
    db.add(customer)

    quote = Quote(
        tenant_id=tenant_id,
        contact_id=contact.id,
        title="Consumer unit replacement",
        status="sent",
        sent_at=datetime.utcnow() - timedelta(days=2),
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )
    db.add(quote)
    await db.flush()
    quote_line = QuoteLineItem(
        tenant_id=tenant_id,
        quote_id=quote.id,
        description="Supply and fit 10-way RCBO consumer unit",
        quantity=Decimal("1.00"),
        unit="ea",
        unit_price=Decimal("500.00"),
        total=Decimal("500.00"),
    )
    db.add(quote_line)

    job = Job(
        tenant_id=tenant_id,
        contact_id=contact.id,
        quote_id=quote.id,
        title="Consumer unit replacement",
        status="scheduled",
    )
    db.add(job)
    await db.flush()

    invoice = Invoice(
        tenant_id=tenant_id,
        contact_id=contact.id,
        job_id=job.id,
        quote_id=quote.id,
        invoice_number=f"INV-{uuid4().hex[:6]}",
        status="sent",
        issue_date=datetime.utcnow() - timedelta(days=1),
        due_date=datetime.utcnow() + timedelta(days=13),
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )
    db.add(invoice)
    await db.flush()
    invoice_line = InvoiceLineItem(
        tenant_id=tenant_id,
        invoice_id=invoice.id,
        description="Consumer unit works as quoted",
        quantity=Decimal("1.00"),
        unit_price=Decimal("500.00"),
        total=Decimal("500.00"),
    )
    db.add(invoice_line)

    communication = Communication(
        tenant_id=tenant_id,
        contact_id=contact.id,
        channel="email",
        direction="outbound",
        sender_role="business",
        subject="Your quote",
        body="Please find your quote attached.",
    )
    db.add(communication)

    await db.commit()
    return {
        "contact_id": contact.id,
        "customer_id": customer.id,
        "quote_id": quote.id,
        "quote_line_id": quote_line.id,
        "job_id": job.id,
        "invoice_id": invoice.id,
        "invoice_line_id": invoice_line.id,
        "communication_id": communication.id,
    }


async def test_export_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/export/my-data")
    assert response.status_code == 401


async def test_export_shape_is_stable(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/export/my-data")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]

    payload = response.json()
    assert set(payload.keys()) == EXPECTED_TOP_LEVEL_KEYS
    assert payload["format_version"] == "1.0"
    assert payload["generated_at"].endswith("Z")
    for key in ("contacts", "customers", "quotes", "jobs", "invoices", "communications"):
        assert isinstance(payload[key], list)


async def test_export_contains_seeded_records(admin_client: AsyncClient, db: AsyncSession) -> None:
    tenant_id = _tenant_id(admin_client)
    ids = await _seed_tenant_records(db, tenant_id)

    response = await admin_client.get("/export/my-data")
    assert response.status_code == 200
    payload = response.json()

    assert payload["tenant"]["id"] == str(tenant_id)
    assert payload["tenant"]["slug"]

    assert [c["id"] for c in payload["contacts"]] == [str(ids["contact_id"])]
    assert payload["contacts"][0]["email"] == "amy@example.com"

    assert [c["id"] for c in payload["customers"]] == [str(ids["customer_id"])]
    # Credentials must never be exported.
    assert "password_hash" not in payload["customers"][0]
    assert "magic_link_token" not in payload["customers"][0]

    assert [q["id"] for q in payload["quotes"]] == [str(ids["quote_id"])]
    quote = payload["quotes"][0]
    assert quote["total"] == "600.00"
    assert [line["id"] for line in quote["line_items"]] == [str(ids["quote_line_id"])]

    assert [j["id"] for j in payload["jobs"]] == [str(ids["job_id"])]
    assert payload["jobs"][0]["quote_id"] == str(ids["quote_id"])

    assert [i["id"] for i in payload["invoices"]] == [str(ids["invoice_id"])]
    invoice = payload["invoices"][0]
    assert invoice["total"] == "600.00"
    assert [line["id"] for line in invoice["line_items"]] == [str(ids["invoice_line_id"])]
    assert "paddle_checkout_id" not in invoice
    assert "paddle_transaction_id" not in invoice

    assert [c["id"] for c in payload["communications"]] == [str(ids["communication_id"])]
    assert payload["communications"][0]["channel"] == "email"


async def test_export_excludes_other_tenants(admin_client: AsyncClient, db: AsyncSession) -> None:
    tenant_id = _tenant_id(admin_client)
    ids = await _seed_tenant_records(db, tenant_id)

    # Seed a second tenant with its own contact + quote, flipping the RLS
    # context so the inserts pass the tenant-isolation policy.
    other_tenant = Tenant(slug=f"other-{uuid4().hex[:8]}", name="Other Electrical")
    db.add(other_tenant)
    await db.flush()
    await set_tenant_in_session(db, other_tenant.id)
    other_contact = Contact(
        tenant_id=other_tenant.id,
        name="Bob Stranger",
        email="bob@other.example.com",
    )
    db.add(other_contact)
    await db.flush()
    other_quote = Quote(
        tenant_id=other_tenant.id,
        contact_id=other_contact.id,
        title="Other tenant quote",
        status="sent",
        sent_at=datetime.utcnow(),
        total=Decimal("999.00"),
    )
    db.add(other_quote)
    await db.commit()
    await set_tenant_in_session(db, tenant_id)

    response = await admin_client.get("/export/my-data")
    assert response.status_code == 200
    payload = response.json()

    assert payload["tenant"]["id"] == str(tenant_id)
    assert payload["tenant"]["id"] != str(other_tenant.id)

    contact_ids = {c["id"] for c in payload["contacts"]}
    assert str(ids["contact_id"]) in contact_ids
    assert str(other_contact.id) not in contact_ids
    assert all(c["email"] != "bob@other.example.com" for c in payload["contacts"])

    quote_ids = {q["id"] for q in payload["quotes"]}
    assert str(ids["quote_id"]) in quote_ids
    assert str(other_quote.id) not in quote_ids
