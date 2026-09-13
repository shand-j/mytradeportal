"""Tests for invoice creation, quote-to-invoice conversion, and refund guards."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.models import AuditLog, Invoice, Notification
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


async def _create_contact(client: AsyncClient, tenant_id: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


async def _create_quote(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Rewire quote",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "500.00"},
                {"description": "Parts", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


async def test_convert_quote_to_invoice(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"sparky-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Bob Builder")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-invoice",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )

    assert response.status_code == 201
    invoice = response.json()
    assert invoice["quote_id"] == quote["id"]
    assert invoice["contact_id"] == contact["id"]
    assert invoice["tenant_id"] == tenant["id"]
    assert invoice["subtotal"] == "600.00"
    # The bootstrap-created tenant never answered the onboarding Tax step, so
    # it is not VAT registered and charges 0% VAT.
    assert invoice["vat_amount"] == "0.00"
    assert invoice["total"] == "600.00"
    assert invoice["invoice_number"].startswith("INV-")
    assert len(invoice["line_items"]) == 2

    quote_response = await client.get(
        f"/quotes/{quote['id']}", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert quote_response.json()["status"] == "invoiced"


async def test_cannot_convert_quote_twice(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"sparky-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Alice")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    first = await client.post(
        f"/quotes/{quote['id']}/convert-to-invoice",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/quotes/{quote['id']}/convert-to-invoice",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert second.status_code == 400


async def test_invoice_number_auto_increments(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"sparky-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Carol")

    quote1 = await _create_quote(client, tenant["id"], contact["id"])
    quote2 = await _create_quote(client, tenant["id"], contact["id"])

    inv1 = await client.post(
        f"/quotes/{quote1['id']}/convert-to-invoice",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    inv2 = await client.post(
        f"/quotes/{quote2['id']}/convert-to-invoice",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )

    assert inv1.json()["invoice_number"] == "INV-001"
    assert inv2.json()["invoice_number"] == "INV-002"


async def test_create_invoice_from_quote_without_line_items(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"sparky-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Dave")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "quote_id": quote["id"]},
    )

    assert response.status_code == 201
    invoice = response.json()
    assert invoice["quote_id"] == quote["id"]
    # Not VAT registered (no onboarding Tax answer) → 0% VAT.
    assert invoice["total"] == "600.00"
    assert invoice["invoice_number"] == "INV-001"


async def test_create_invoice_for_quoteless_job(client: AsyncClient) -> None:
    """A job with no attributed quote can still be invoiced (backlog N18).

    The app's job detail screen guards the empty-lines case client-side, but the
    endpoint must accept quote-less jobs and never 5xx.
    """
    tenant = await _create_tenant(client, f"sparky-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Eve")
    job_response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Quote-less job"},
    )
    assert job_response.status_code == 201
    job = job_response.json()
    assert job["quote_id"] is None

    # Manual line items supplied by the electrician.
    response = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "job_id": job["id"],
            "line_items": [
                {"description": "Labour", "quantity": "2", "unit_price": "45.00"},
            ],
        },
    )
    assert response.status_code == 201
    invoice = response.json()
    assert invoice["quote_id"] is None
    assert invoice["job_id"] == job["id"]
    assert invoice["subtotal"] == "90.00"
    # The VAT-inclusive total depends on the tenant's VAT registration; require
    # the invoice to be internally consistent instead of a fixed rate.
    assert Decimal(invoice["total"]) == Decimal(invoice["subtotal"]) + Decimal(
        invoice["vat_amount"]
    )

    send_response = await client.post(
        f"/invoices/{invoice['id']}/send",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert send_response.status_code == 200
    assert send_response.json()["status"] == "sent"


async def test_create_invoice_rejects_unknown_job_with_400(client: AsyncClient) -> None:
    """Invalid job/contact/quote references are clear 400s, not 500s."""
    tenant = await _create_tenant(client, f"sparky-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Frank")

    response = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "job_id": str(uuid4())},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid job"


async def test_invoice_accept_card_payments_toggle_round_trip(client: AsyncClient) -> None:
    """Per-invoice card toggle: set → clear restores tenant-default inheritance."""
    tenant = await _create_tenant(client, f"sparky-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Grace")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    created = await client.post(
        f"/quotes/{quote['id']}/convert-to-invoice",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert created.status_code == 201
    invoice = created.json()
    # New invoices inherit the tenant default: no per-invoice override yet.
    assert invoice["accept_card_payments"] is None
    assert invoice["paid_via"] is None

    headers = {"X-Tenant-ID": tenant["id"]}
    enabled = await client.patch(
        f"/invoices/{invoice['id']}", headers=headers, json={"accept_card_payments": True}
    )
    assert enabled.status_code == 200
    assert enabled.json()["accept_card_payments"] is True

    disabled = await client.patch(
        f"/invoices/{invoice['id']}", headers=headers, json={"accept_card_payments": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["accept_card_payments"] is False

    cleared = await client.patch(
        f"/invoices/{invoice['id']}", headers=headers, json={"accept_card_payments": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["accept_card_payments"] is None

    # The override survives reads from the detail endpoint too.
    detail = await client.get(f"/invoices/{invoice['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["accept_card_payments"] is None


# ---------------------------------------------------------------------------
# Refund guards (POST /invoices/{id}/refund) — Stripe-paid invoices only
# ---------------------------------------------------------------------------


async def _create_scratch_invoice(admin_client: AsyncClient) -> dict[str, Any]:
    contact = await admin_client.post("/contacts", json={"name": "Refund Homeowner"})
    assert contact.status_code == 201
    response = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact.json()["id"],
            "invoice_number": f"INV-{uuid4().hex[:6]}",
            "line_items": [
                {"description": "Fuse board works", "quantity": "1", "unit_price": "600.00"},
            ],
        },
    )
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


async def _make_stripe_paid(db: AsyncSession, tenant_id: UUID, invoice_id: str) -> None:
    await set_tenant_in_session(db, tenant_id)
    row = await db.get(Invoice, UUID(invoice_id))
    assert row is not None
    row.status = "paid"
    row.paid_via = "stripe"
    row.stripe_payment_intent_id = "pi_guard_1"
    await db.commit()


async def test_refund_unpaid_invoice_409(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_refund = AsyncMock()
    monkeypatch.setattr("app.stripe_client.create_refund", create_refund)

    invoice = await _create_scratch_invoice(admin_client)
    response = await admin_client.post(f"/invoices/{invoice['id']}/refund")
    assert response.status_code == 409
    create_refund.assert_not_called()


async def test_refund_503_when_stripe_unconfigured(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refunding a Stripe-paid invoice after the key was removed: clean 503,
    never a 500, and the invoice stays paid. The real ``create_refund``
    raises ``PaymentsNotConfiguredError`` before any network call."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    invoice = await _create_scratch_invoice(admin_client)
    await _make_stripe_paid(db, tenant_id, invoice["id"])

    response = await admin_client.post(f"/invoices/{invoice['id']}/refund")
    assert response.status_code == 503
    assert response.json()["detail"] == "payments_not_configured"

    row = await db.get(Invoice, UUID(invoice["id"]))
    assert row is not None
    assert row.status == "paid"


async def test_refund_sets_status_writes_audit_log_and_notifies_staff(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_refund = AsyncMock(return_value={"id": "re_guard_1", "status": "succeeded"})
    monkeypatch.setattr("app.stripe_client.create_refund", create_refund)

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    invoice = await _create_scratch_invoice(admin_client)
    await _make_stripe_paid(db, tenant_id, invoice["id"])

    response = await admin_client.post(f"/invoices/{invoice['id']}/refund")
    assert response.status_code == 200
    assert response.json()["status"] == "refunded"
    create_refund.assert_awaited_once_with("pi_guard_1")

    await set_tenant_in_session(db, tenant_id)
    audit = await db.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "invoice.refunded",
            AuditLog.entity_id == UUID(invoice["id"]),
        )
    )
    assert audit is not None
    assert audit.payload["stripe_refund_id"] == "re_guard_1"
    assert audit.payload["stripe_payment_intent_id"] == "pi_guard_1"

    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.type == "invoice_refunded",
        )
    )
    assert notification is not None
    assert invoice["invoice_number"] in notification.body
