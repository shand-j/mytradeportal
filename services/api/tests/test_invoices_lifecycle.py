"""Tests for invoice lifecycle endpoints."""

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    return response.json()


async def _create_contact(client: AsyncClient, tenant_id: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    return response.json()


async def _create_invoice(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "invoice_number": "INV-LIFE-001",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "200.00"},
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_update_invoice(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"inv-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice Updater")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.patch(
        f"/invoices/{invoice['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"notes": "Updated note", "status": "sent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["notes"] == "Updated note"
    assert data["status"] == "sent"


async def test_send_invoice(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"inv-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice Sender")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/invoices/{invoice['id']}/send",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"


async def test_issue_invoice_maps_to_sent(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"inv-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice Issuer")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/invoices/{invoice['id']}/issue",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"


async def test_mark_invoice_paid(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"inv-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice Payer")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/invoices/{invoice['id']}/mark-paid",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "paid"
    assert data["paid_at"] is not None


async def test_cancel_invoice(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"inv-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice Canceller")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/invoices/{invoice['id']}/cancel",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_delete_invoice(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"inv-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice Deleter")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.delete(
        f"/invoices/{invoice['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 204

    get_response = await client.get(
        f"/invoices/{invoice['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert get_response.status_code == 404
