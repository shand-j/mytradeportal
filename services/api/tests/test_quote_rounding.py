"""Tests for the quote-total rounding setting (N22)."""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _set_rounding(admin_client: AsyncClient, value: int) -> None:
    response = await admin_client.patch("/tenants/me", json={"settings": {"quote_rounding": value}})
    assert response.status_code == 200
    assert response.json()["settings"]["quote_rounding"] == value


async def _create_contact(admin_client: AsyncClient) -> str:
    response = await admin_client.post("/contacts", json={"name": "Rounding Customer"})
    assert response.status_code == 201
    contact_id: str = response.json()["id"]
    return contact_id


def _quote_payload(contact_id: str) -> dict[str, Any]:
    # £863.00 ex VAT; the test tenant is not VAT-registered so total == subtotal.
    return {
        "contact_id": contact_id,
        "title": "Fuse board upgrade",
        "line_items": [
            {"description": "Consumer unit", "quantity": "1", "unit_price": "863.00"},
        ],
    }


async def test_rounding_off_by_default(admin_client: AsyncClient) -> None:
    contact_id = await _create_contact(admin_client)
    response = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    assert response.status_code == 201
    data = response.json()
    assert Decimal(data["total"]) == Decimal("863.00")
    assert Decimal(
        data["roundingAdjustment"] if "roundingAdjustment" in data else data["rounding_adjustment"]
    ) == Decimal("0.00")


async def test_rounding_to_nearest_10(admin_client: AsyncClient) -> None:
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    response = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    assert response.status_code == 201
    data = response.json()
    adjustment = data.get("roundingAdjustment", data.get("rounding_adjustment"))
    assert Decimal(data["total"]) == Decimal("870.00")
    assert Decimal(adjustment) == Decimal("7.00")


async def test_rounding_to_nearest_5(admin_client: AsyncClient) -> None:
    await _set_rounding(admin_client, 5)
    contact_id = await _create_contact(admin_client)
    response = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    assert response.status_code == 201
    data = response.json()
    adjustment = data.get("roundingAdjustment", data.get("rounding_adjustment"))
    assert Decimal(data["total"]) == Decimal("865.00")
    assert Decimal(adjustment) == Decimal("2.00")


async def test_rounding_invalid_value_treated_as_off(admin_client: AsyncClient) -> None:
    await _set_rounding(admin_client, 7)
    contact_id = await _create_contact(admin_client)
    response = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    assert response.status_code == 201
    assert Decimal(response.json()["total"]) == Decimal("863.00")


async def test_rounding_reapplied_on_line_item_update(admin_client: AsyncClient) -> None:
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    quote_id = created.json()["id"]

    response = await admin_client.patch(
        f"/quotes/{quote_id}",
        json={
            "line_items": [
                {"description": "Consumer unit", "quantity": "1", "unit_price": "863.00"},
                {"description": "Extra socket", "quantity": "1", "unit_price": "95.00"},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    adjustment = data.get("roundingAdjustment", data.get("rounding_adjustment"))
    # £958.00 → £960.00
    assert Decimal(data["total"]) == Decimal("960.00")
    assert Decimal(adjustment) == Decimal("2.00")


async def test_invoice_inherits_rounded_quote_total(admin_client: AsyncClient) -> None:
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    quote_id = created.json()["id"]
    assert Decimal(created.json()["total"]) == Decimal("870.00")

    response = await admin_client.post(f"/quotes/{quote_id}/convert-to-invoice", json={})
    assert response.status_code == 201
    invoice = response.json()
    adjustment = invoice.get("roundingAdjustment", invoice.get("rounding_adjustment"))
    assert Decimal(invoice["total"]) == Decimal("870.00")
    assert Decimal(adjustment) == Decimal("7.00")


async def test_invoice_from_scratch_is_not_rounded(admin_client: AsyncClient) -> None:
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    response = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "line_items": [
                {"description": "Call-out", "quantity": "1", "unit_price": "863.00"},
            ],
        },
    )
    assert response.status_code == 201
    invoice = response.json()
    adjustment = invoice.get("roundingAdjustment", invoice.get("rounding_adjustment"))
    assert Decimal(invoice["total"]) == Decimal("863.00")
    assert Decimal(adjustment) == Decimal("0.00")


async def test_rounding_persists_via_mobile_follow_up_payload(admin_client: AsyncClient) -> None:
    """Lock the exact contract the mobile Follow-ups screen puts on the wire.

    The app PATCHes the full follow-up settings block (camelCase keys are
    snakeized client-side, so this is the literal wire payload); the value
    must persist through a fresh GET and apply to newly created quotes.
    """
    payload = {
        "settings": {
            "quote_reminders_enabled": True,
            "quote_reminder_max": 3,
            "quote_reminder_interval_days": 3,
            "invoice_reminders_enabled": True,
            "invoice_reminder_interval_days": 7,
            "quote_rounding": 10,
        }
    }
    response = await admin_client.patch("/tenants/me", json=payload)
    assert response.status_code == 200
    assert response.json()["settings"]["quote_rounding"] == 10

    # Fresh read (what fetchFollowUpSettings does on screen load).
    fetched = await admin_client.get("/tenants/me")
    assert fetched.json()["settings"]["quote_rounding"] == 10

    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    assert created.status_code == 201
    assert Decimal(created.json()["total"]) == Decimal("870.00")
