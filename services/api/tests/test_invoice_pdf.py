"""Tests for the invoice PDF endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:
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
            "invoice_number": "INV-PDF-001",
            "line_items": [
                {"description": "Emergency callout 🚨", "quantity": "1", "unit_price": "200.00"},
                {
                    "description": "Kitchen socket install — Δ",
                    "quantity": "2",
                    "unit_price": "55.00",
                },
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_invoice_pdf_endpoint_returns_valid_pdf(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"invpdf-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice PDF Customer")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.get(
        f"/invoices/{invoice['id']}/pdf",
        headers={"X-Tenant-ID": tenant["id"]},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers.get("content-disposition", "")
    body = response.content
    assert body.startswith(b"%PDF-"), body[:8]
    assert b"%%EOF" in body[-1024:]


async def test_invoice_pdf_is_tenant_scoped(client: AsyncClient) -> None:
    tenant_a = await _create_tenant(client, f"invpdf-a-{uuid4().hex[:8]}")
    tenant_b = await _create_tenant(client, f"invpdf-b-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant_a["id"], "Tenant A Customer")
    invoice = await _create_invoice(client, tenant_a["id"], contact["id"])

    response = await client.get(
        f"/invoices/{invoice['id']}/pdf",
        headers={"X-Tenant-ID": tenant_b["id"]},
    )

    assert response.status_code == 404
