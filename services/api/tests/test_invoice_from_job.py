"""Tests for creating an invoice from a job with an attributed quote.

Covers the quote → job → invoice money flow: convert-to-job keeps the quote
link, and POST /invoices with only a job_id prefills the quote's line items
and mirrors its totals exactly (including the rounding uplift — never
re-rounded).
"""

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
    response = await admin_client.post("/contacts", json={"name": "Job Invoice Customer"})
    assert response.status_code == 201
    contact_id: str = response.json()["id"]
    return contact_id


async def _create_approved_quote(admin_client: AsyncClient, contact_id: str) -> dict[str, Any]:
    # £863.00 ex VAT; the test tenant is not VAT-registered so total == subtotal.
    response = await admin_client.post(
        "/quotes",
        json={
            "contact_id": contact_id,
            "title": "Fuse board upgrade",
            "line_items": [
                {"description": "Consumer unit", "quantity": "1", "unit_price": "863.00"},
            ],
        },
    )
    assert response.status_code == 201
    quote = response.json()
    approved = await admin_client.post(f"/quotes/{quote['id']}/approve", json={})
    assert approved.status_code == 200
    return quote  # type: ignore[no-any-return]


async def _convert_to_job(admin_client: AsyncClient, quote_id: str) -> dict[str, Any]:
    response = await admin_client.post(f"/quotes/{quote_id}/convert-to-job", json={})
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


def _rounding_adjustment(invoice: dict[str, Any]) -> Decimal:
    value = invoice.get("roundingAdjustment", invoice.get("rounding_adjustment"))
    return Decimal(str(value))


async def test_convert_to_job_carries_quote_line_items(admin_client: AsyncClient) -> None:
    """convert-to-job links the quote, and an invoice raised with ONLY the
    job_id prefills the quote's lines and exact totals (rounding uplift
    included) — the £0.00 empty-invoice regression."""
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    quote = await _create_approved_quote(admin_client, contact_id)
    assert Decimal(quote["total"]) == Decimal("870.00")

    job = await _convert_to_job(admin_client, quote["id"])
    assert job["quote_id"] == quote["id"]

    response = await admin_client.post(
        "/invoices",
        json={"contact_id": contact_id, "job_id": job["id"]},
    )
    assert response.status_code == 201
    invoice = response.json()
    assert invoice["job_id"] == job["id"]
    assert invoice["quote_id"] == quote["id"]
    assert [li["description"] for li in invoice["line_items"]] == ["Consumer unit"]
    assert Decimal(invoice["subtotal"]) == Decimal("863.00")
    assert Decimal(invoice["total"]) == Decimal("870.00")
    assert _rounding_adjustment(invoice) == Decimal("7.00")


async def test_invoice_from_job_without_rounding_mirrors_quote(
    admin_client: AsyncClient,
) -> None:
    contact_id = await _create_contact(admin_client)
    quote = await _create_approved_quote(admin_client, contact_id)
    job = await _convert_to_job(admin_client, quote["id"])

    response = await admin_client.post(
        "/invoices",
        json={"contact_id": contact_id, "job_id": job["id"]},
    )
    assert response.status_code == 201
    invoice = response.json()
    assert Decimal(invoice["total"]) == Decimal("863.00")
    assert _rounding_adjustment(invoice) == Decimal("0.00")


async def test_invoice_from_job_with_quoted_lines_is_not_rerounded(
    admin_client: AsyncClient,
) -> None:
    """The app prefills the quote's lines for review; when they come back
    unchanged the invoice mirrors the quote — the uplift is inherited once,
    never applied twice."""
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    quote = await _create_approved_quote(admin_client, contact_id)
    job = await _convert_to_job(admin_client, quote["id"])

    response = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "job_id": job["id"],
            "quote_id": quote["id"],
            "line_items": [
                {"description": "Consumer unit", "quantity": "1", "unit_price": "863.00"},
            ],
        },
    )
    assert response.status_code == 201
    invoice = response.json()
    assert Decimal(invoice["subtotal"]) == Decimal("863.00")
    assert Decimal(invoice["total"]) == Decimal("870.00")
    assert _rounding_adjustment(invoice) == Decimal("7.00")


async def test_invoice_from_job_with_edited_lines_recomputes_without_uplift(
    admin_client: AsyncClient,
) -> None:
    """Editing the prefilled lines before creating recomputes totals from the
    edited lines; the stale uplift is dropped and the quote-linked invoice is
    never re-rounded server-side."""
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    quote = await _create_approved_quote(admin_client, contact_id)
    job = await _convert_to_job(admin_client, quote["id"])

    response = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "job_id": job["id"],
            "line_items": [
                {"description": "Consumer unit", "quantity": "1", "unit_price": "863.00"},
                {"description": "Extra socket", "quantity": "1", "unit_price": "50.00"},
            ],
        },
    )
    assert response.status_code == 201
    invoice = response.json()
    assert invoice["quote_id"] == quote["id"]
    assert Decimal(invoice["subtotal"]) == Decimal("913.00")
    assert Decimal(invoice["total"]) == Decimal("913.00")
    assert _rounding_adjustment(invoice) == Decimal("0.00")


async def test_invoice_from_quoteless_job_keeps_scratch_behaviour(
    admin_client: AsyncClient,
) -> None:
    """Quote-less jobs are scratch invoices: rounded once at creation per the
    tenant setting, with no quote link."""
    await _set_rounding(admin_client, 10)
    contact_id = await _create_contact(admin_client)
    job_response = await admin_client.post(
        "/jobs",
        json={"contact_id": contact_id, "title": "Quote-less job"},
    )
    assert job_response.status_code == 201
    job = job_response.json()
    assert job["quote_id"] is None

    response = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "job_id": job["id"],
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "863.00"},
            ],
        },
    )
    assert response.status_code == 201
    invoice = response.json()
    assert invoice["quote_id"] is None
    assert invoice["job_id"] == job["id"]
    assert Decimal(invoice["total"]) == Decimal("870.00")
    assert _rounding_adjustment(invoice) == Decimal("7.00")
