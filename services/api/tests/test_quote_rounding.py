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


async def test_invoice_from_scratch_is_rounded_per_setting(admin_client: AsyncClient) -> None:
    """Scratch invoices (no source quote) are rounded once, at creation."""
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
    assert Decimal(invoice["total"]) == Decimal("870.00")
    assert Decimal(adjustment) == Decimal("7.00")


async def test_read_endpoints_return_rounded_totals(admin_client: AsyncClient) -> None:
    """Quote/invoice read endpoints return the rounded total (issue #173).

    The rounding uplift is baked into the stored ``total``; every read surface
    (detail + list, quote + invoice) must return the same rounded value so no
    UI ever shows the unrounded amount.
    """
    await _set_rounding(admin_client, 5)
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    quote_id = created.json()["id"]
    assert Decimal(created.json()["total"]) == Decimal("865.00")

    quote_detail = await admin_client.get(f"/quotes/{quote_id}")
    assert quote_detail.status_code == 200
    assert Decimal(quote_detail.json()["total"]) == Decimal("865.00")
    adjustment = quote_detail.json().get(
        "roundingAdjustment", quote_detail.json().get("rounding_adjustment")
    )
    assert Decimal(adjustment) == Decimal("2.00")

    quote_list = await admin_client.get("/quotes")
    assert quote_list.status_code == 200
    listed_quote = next(q for q in quote_list.json() if q["id"] == quote_id)
    assert Decimal(listed_quote["total"]) == Decimal("865.00")

    converted = await admin_client.post(f"/quotes/{quote_id}/convert-to-invoice", json={})
    assert converted.status_code == 201
    invoice_id = converted.json()["id"]

    invoice_detail = await admin_client.get(f"/invoices/{invoice_id}")
    assert invoice_detail.status_code == 200
    assert Decimal(invoice_detail.json()["total"]) == Decimal("865.00")
    adjustment = invoice_detail.json().get(
        "roundingAdjustment", invoice_detail.json().get("rounding_adjustment")
    )
    assert Decimal(adjustment) == Decimal("2.00")

    invoice_list = await admin_client.get("/invoices")
    assert invoice_list.status_code == 200
    listed_invoice = next(i for i in invoice_list.json() if i["id"] == invoice_id)
    assert Decimal(listed_invoice["total"]) == Decimal("865.00")

    scratch = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "line_items": [
                {"description": "Call-out", "quantity": "1", "unit_price": "863.00"},
            ],
        },
    )
    assert scratch.status_code == 201
    scratch_detail = await admin_client.get(f"/invoices/{scratch.json()['id']}")
    assert Decimal(scratch_detail.json()["total"]) == Decimal("865.00")


async def test_unrounded_legacy_quote_is_mirrored_not_rerounded(
    admin_client: AsyncClient,
) -> None:
    """A quote created before the setting existed keeps its exact total on the
    invoice: enabling rounding later must NOT inflate the invoice past the
    total the customer accepted."""
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    quote_id = created.json()["id"]
    assert Decimal(created.json()["total"]) == Decimal("863.00")

    # The tenant switches rounding on after the quote was issued.
    await _set_rounding(admin_client, 10)

    response = await admin_client.post(f"/quotes/{quote_id}/convert-to-invoice", json={})
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


async def _set_vat_registered(admin_client: AsyncClient) -> None:
    response = await admin_client.patch(
        "/onboarding/step/tax",
        json={"step": "tax", "value": {"vat_registered": True}},
    )
    assert response.status_code == 200, response.text


async def test_vat_opt_out_reapplies_rounding_to_new_total(admin_client: AsyncClient) -> None:
    """Zero-rating a rounded quote re-runs create-time math: totals rebuild
    from the line items at 0% VAT, then the £10 increment re-rounds the new
    VAT-inclusive total (issue #110)."""
    await _set_rounding(admin_client, 10)
    await _set_vat_registered(admin_client)
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    quote_id = created.json()["id"]
    # £863.00 + 20% VAT = £1035.60 → £1040.00
    assert Decimal(created.json()["total"]) == Decimal("1040.00")
    adjustment = created.json().get("roundingAdjustment", created.json().get("rounding_adjustment"))
    assert Decimal(adjustment) == Decimal("4.40")

    response = await admin_client.patch(f"/quotes/{quote_id}", json={"vat_rate": "0"})
    assert response.status_code == 200, response.text
    data = response.json()
    # £863.00 ex VAT → £870.00; stored totals re-fetch identically.
    assert Decimal(data["total"]) == Decimal("870.00")
    adjustment = data.get("roundingAdjustment", data.get("rounding_adjustment"))
    assert Decimal(adjustment) == Decimal("7.00")

    fetched = await admin_client.get(f"/quotes/{quote_id}")
    assert fetched.status_code == 200
    assert Decimal(fetched.json()["total"]) == Decimal("870.00")
    adjustment = fetched.json().get("roundingAdjustment", fetched.json().get("rounding_adjustment"))
    assert Decimal(adjustment) == Decimal("7.00")


async def test_vat_opt_out_combined_with_line_item_update(admin_client: AsyncClient) -> None:
    """One PATCH carrying both line_items and vat_rate applies both before
    the totals recompute, exactly like create-time math."""
    await _set_vat_registered(admin_client)
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_quote_payload(contact_id))
    quote_id = created.json()["id"]
    assert Decimal(created.json()["total"]) == Decimal("1035.60")

    response = await admin_client.patch(
        f"/quotes/{quote_id}",
        json={
            "vat_rate": "0",
            "line_items": [
                {"description": "Consumer unit", "quantity": "1", "unit_price": "863.00"},
                {"description": "Extra socket", "quantity": "1", "unit_price": "95.00"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    # £958.00 ex VAT at 0% → no rounding configured → £958.00.
    assert Decimal(data["subtotal"]) == Decimal("958.00")
    assert Decimal(data["vat_amount"]) == Decimal("0.00")
    assert Decimal(data["total"]) == Decimal("958.00")
