"""Tests for invoice creation and quote-to-invoice conversion."""

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
    assert invoice["vat_amount"] == "120.00"
    assert invoice["total"] == "720.00"
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
    assert invoice["total"] == "720.00"
    assert invoice["invoice_number"] == "INV-001"
