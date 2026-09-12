"""Tests for the quote-edit fine-tuning dataset capture + export (C9)."""

from decimal import Decimal

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_quote(admin_client: AsyncClient) -> str:
    contact = await admin_client.post("/contacts", json={"name": "Training Customer"})
    assert contact.status_code == 201
    response = await admin_client.post(
        "/quotes",
        json={
            "contact_id": contact.json()["id"],
            "title": "Rewire kitchen",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "400.00"},
            ],
        },
    )
    assert response.status_code == 201
    quote_id: str = response.json()["id"]
    return quote_id


async def test_training_events_empty_initially(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/quotes/training-events")
    assert response.status_code == 200
    assert response.json() == []


async def test_line_item_edit_captured_with_before_after(admin_client: AsyncClient) -> None:
    quote_id = await _create_quote(admin_client)

    edit = await admin_client.patch(
        f"/quotes/{quote_id}",
        json={
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "450.00"},
                {"description": "Materials", "quantity": "1", "unit_price": "120.00"},
            ]
        },
    )
    assert edit.status_code == 200

    response = await admin_client.get("/quotes/training-events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    event = events[0]
    assert event["eventType" if "eventType" in event else "event_type"] == "quote_lines_edited"
    entity_id = event.get("entityId", event.get("entity_id"))
    assert entity_id == quote_id
    payload = event["payload"]
    assert payload["title"] == "Rewire kitchen"
    assert len(payload["before"]) == 1
    assert Decimal(payload["before"][0]["unit_price"]) == Decimal("400.00")
    assert len(payload["after"]) == 2
    assert {li["description"] for li in payload["after"]} == {"Labour", "Materials"}


async def test_non_line_item_edit_not_captured(admin_client: AsyncClient) -> None:
    quote_id = await _create_quote(admin_client)
    edit = await admin_client.patch(
        f"/quotes/{quote_id}", json={"title": "Rewire kitchen (phase 1)"}
    )
    assert edit.status_code == 200

    response = await admin_client.get("/quotes/training-events")
    assert response.status_code == 200
    assert response.json() == []


async def test_training_events_require_auth(client: AsyncClient) -> None:
    response = await client.get("/quotes/training-events")
    assert response.status_code == 401
