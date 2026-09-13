"""Tests for invoice creation and quote-to-invoice conversion."""

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

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
