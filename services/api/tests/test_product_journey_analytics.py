"""Product analytics emitted by real tenant, quote, job and invoice workflows."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models import Event
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_core_journey_emits_product_funnel_events(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_customer_email(db: Any = None, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr("app.routers.quotes.send_customer_email", fake_customer_email)
    monkeypatch.setattr(
        "app.routers.invoices.send_payment_received_email",
        AsyncMock(return_value=True),
    )
    slug = f"journey-{uuid4().hex[:8]}"
    tenant_response = await client.post("/tenants", json={"slug": slug, "name": "Journey Ltd"})
    assert tenant_response.status_code == 201
    tenant_id = tenant_response.json()["id"]
    headers = {"X-Tenant-ID": tenant_id}

    contact_response = await client.post(
        "/contacts",
        headers=headers,
        json={"name": "Journey Customer", "email": "journey@example.com"},
    )
    assert contact_response.status_code == 201
    contact_id = contact_response.json()["id"]

    quote_response = await client.post(
        "/quotes",
        headers=headers,
        json={
            "contact_id": contact_id,
            "title": "Journey quote",
            "line_items": [{"description": "Work", "quantity": "1", "unit_price": "100.00"}],
        },
    )
    assert quote_response.status_code == 201
    quote_id = quote_response.json()["id"]

    assert (await client.post(f"/quotes/{quote_id}/send", headers=headers)).status_code == 200
    approved = await client.post(
        f"/quotes/{quote_id}/approve",
        headers=headers,
        json={"approved": True},
    )
    assert approved.status_code == 200

    job_response = await client.post(
        "/jobs",
        headers=headers,
        json={"contact_id": contact_id, "quote_id": quote_id, "title": "Journey job"},
    )
    assert job_response.status_code == 201

    invoice_response = await client.post(
        "/invoices",
        headers=headers,
        json={
            "contact_id": contact_id,
            "quote_id": quote_id,
            "line_items": [{"description": "Work", "quantity": "1", "unit_price": "100.00"}],
        },
    )
    assert invoice_response.status_code == 201
    invoice_id = invoice_response.json()["id"]
    paid = await client.post(f"/invoices/{invoice_id}/mark-paid", headers=headers)
    assert paid.status_code == 200

    events = (
        (
            await db.execute(
                select(Event).where(
                    Event.tenant_id == tenant_id,
                    Event.event_type.like("analytics.%"),
                )
            )
        )
        .scalars()
        .all()
    )
    names = {event.event_type for event in events}
    assert {
        "analytics.tenant_signup",
        "analytics.quote_created",
        "analytics.quote_sent",
        "analytics.quote_accepted",
        "analytics.job_created",
        "analytics.invoice_created",
        "analytics.invoice_paid",
    } <= names
    payloads = str([event.payload for event in events])
    assert "journey@example.com" not in payloads
    assert "Journey quote" not in payloads
