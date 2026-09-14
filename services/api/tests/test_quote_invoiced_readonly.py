"""Quote read-only once invoiced.

Once an invoice for a quote has been SENT (or paid), the quote is locked:
PATCH /quotes/{id} and POST /quotes/{id}/refine reject with 409
``quote_invoiced``. Draft invoices don't block — the electrician may still be
fixing the quote that seeded them.
"""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_contact(client: AsyncClient, tenant_id: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_quote(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Invoiced quote",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_draft_invoice(
    client: AsyncClient, tenant_id: str, contact_id: str, quote_id: str
) -> dict[str, Any]:
    response = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "quote_id": quote_id,
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _send_invoice(client: AsyncClient, tenant_id: str, invoice_id: str) -> None:
    response = await client.post(
        f"/invoices/{invoice_id}/send",
        headers={"X-Tenant-ID": tenant_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"


def _refine_patches() -> tuple[AsyncMock, AsyncMock]:
    generated = {
        "line_items": [
            {
                "description": "Regenerated labour",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 200.00,
            }
        ],
        "notes": "",
    }
    return (
        AsyncMock(return_value=([], "no_index")),
        AsyncMock(return_value=generated),
    )


async def test_update_quote_blocked_once_invoice_sent(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Locked Quote Owner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    invoice = await _create_draft_invoice(client, tenant["id"], contact["id"], quote["id"])
    await _send_invoice(client, tenant["id"], invoice["id"])

    response = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"title": "Sneaky post-invoice edit"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "quote_invoiced"


async def test_refine_quote_blocked_once_invoice_sent(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Locked Refine Owner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    invoice = await _create_draft_invoice(client, tenant["id"], contact["id"], quote["id"])
    await _send_invoice(client, tenant["id"], invoice["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/refine",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"instructions": "Regenerate the labour line"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "quote_invoiced"


async def test_update_quote_blocked_once_invoice_paid(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Paid Quote Owner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    invoice = await _create_draft_invoice(client, tenant["id"], contact["id"], quote["id"])
    await _send_invoice(client, tenant["id"], invoice["id"])
    paid = await client.post(
        f"/invoices/{invoice['id']}/mark-paid",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert paid.status_code == 200

    response = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"title": "Sneaky post-payment edit"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "quote_invoiced"


async def test_update_quote_allowed_with_draft_invoice(client: AsyncClient) -> None:
    """A draft invoice doesn't lock the quote — only a sent one does."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Draft Invoice Owner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    invoice = await _create_draft_invoice(client, tenant["id"], contact["id"], quote["id"])
    assert invoice["status"] == "draft"

    response = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "title": "Still editable",
            "line_items": [
                {"description": "Parts", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Still editable"


async def test_refine_quote_allowed_with_draft_invoice(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Draft Refine Owner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    invoice = await _create_draft_invoice(client, tenant["id"], contact["id"], quote["id"])
    assert invoice["status"] == "draft"

    search_mock, generate_mock = _refine_patches()
    with (
        patch("app.routers.quotes.search_cost_items_with_status", new=search_mock),
        patch("app.routers.quotes.generate_quote_from_prompt", new=generate_mock),
    ):
        response = await client.post(
            f"/quotes/{quote['id']}/refine",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"instructions": "Regenerate the labour line"},
        )

    assert response.status_code == 200, response.text
    descriptions = [li["description"] for li in response.json()["line_items"]]
    assert "Regenerated labour" in descriptions
