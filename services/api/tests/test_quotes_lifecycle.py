"""Tests for quote lifecycle endpoints."""

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from app.models import BillOfQuantities, Quote
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
            "title": "Initial quote",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def test_update_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Updater")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "title": "Updated quote",
            "status": "sent",
            "line_items": [
                {"description": "Parts", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated quote"
    assert data["status"] == "sent"
    assert data["subtotal"] == "100.00"
    assert len(data["line_items"]) == 1
    assert data["line_items"][0]["description"] == "Parts"


async def test_send_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Sender")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/send",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["sent_at"] is not None


async def test_reject_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Rejecter")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/reject",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


async def test_refine_quote_placeholder(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Refiner")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/refine",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["id"] == quote["id"]


async def test_delete_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Deleter")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.delete(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 204

    get_response = await client.get(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert get_response.status_code == 404


async def test_list_quotes_handles_malformed_boq_json(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Legacy Data")
    quote_data = await _create_quote(client, tenant["id"], contact["id"])

    quote = (
        await db.execute(
            select(Quote).where(Quote.id == quote_data["id"], Quote.tenant_id == tenant["id"])
        )
    ).scalar_one()
    quote.bill_of_quantities = BillOfQuantities(
        tenant_id=quote.tenant_id,
        quote_id=quote.id,
        status="draft",
        subtotal=Decimal("100.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
        confidence=0.85,
        warnings=[],
        regulatory_citations=[],
        compliance_warnings=[],
        customer_summary_lines=[
            {"description": "Missing total"},
            {"description": "Valid line", "total": "100.00"},
            "bad-entry",
        ],
        margin_indicator={},
        retrieval_evidence={},
        line_items=[],
    )
    await db.commit()

    response = await client.get("/quotes", headers={"X-Tenant-ID": tenant["id"]})
    assert response.status_code == 200

    fetched_quote = response.json()[0]
    assert fetched_quote["id"] == quote_data["id"]
    assert fetched_quote["bill_of_quantities"]["customer_summary_lines"] == [
        {"description": "Valid line", "total": "100.00"}
    ]
    assert fetched_quote["bill_of_quantities"]["margin_indicator"] is None
    assert fetched_quote["bill_of_quantities"]["retrieval_evidence"] is None
