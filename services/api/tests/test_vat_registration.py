"""Regression tests for backlog C1: tenant VAT registration must drive VAT rates.

A tenant that is NOT VAT registered (captured in the onboarding Tax step) must
get 0% VAT on quotes and invoices; a registered tenant gets their configured
rate (or the UK standard 20%). The create schemas default ``vat_rate`` to
0.20, so the routers must only honour the field when the client actually sent
it (``model_fields_set``) — otherwise every quote/invoice silently used 20%.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

STANDARD_VAT = Decimal("0.20")
ZERO_VAT = Decimal("0")


async def _set_vat_registered(client: AsyncClient, registered: bool) -> None:
    response = await client.patch(
        "/onboarding/step/tax",
        json={"step": "tax", "value": {"vat_registered": registered}},
    )
    assert response.status_code == 200, response.text


async def _create_contact(client: AsyncClient) -> str:
    response = await client.post(
        "/contacts",
        json={"name": "Vat Tester", "email": f"vat-{uuid4().hex[:8]}@example.com"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _create_quote(
    client: AsyncClient, contact_id: str, vat_rate: str | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "contact_id": contact_id,
        "title": "VAT check quote",
        "line_items": [{"description": "Labour", "quantity": "1", "unit_price": "100.00"}],
    }
    if vat_rate is not None:
        payload["vat_rate"] = vat_rate
    response = await client.post("/quotes", json=payload)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _create_invoice(client: AsyncClient, contact_id: str) -> dict[str, object]:
    response = await client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "line_items": [{"description": "Labour", "quantity": "1", "unit_price": "100.00"}],
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _rate(body: dict[str, object]) -> Decimal:
    return Decimal(str(body["vat_rate"]))


async def test_onboarding_tax_step_persists_vat_registered(
    admin_client: AsyncClient,
) -> None:
    """The onboarding Tax step answer survives in the tenant's onboarding
    progress and drives the tenant-level VAT rate used downstream."""
    await _set_vat_registered(admin_client, True)
    status = await admin_client.get("/onboarding/status")
    assert status.status_code == 200
    assert status.json()["onboarding_progress"]["tax"]["value"]["vat_registered"] is True

    await _set_vat_registered(admin_client, False)
    status = await admin_client.get("/onboarding/status")
    assert status.json()["onboarding_progress"]["tax"]["value"]["vat_registered"] is False


async def test_non_vat_registered_tenant_quote_has_zero_vat(admin_client: AsyncClient) -> None:
    await _set_vat_registered(admin_client, False)
    contact_id = await _create_contact(admin_client)

    quote = await _create_quote(admin_client, contact_id)

    assert _rate(quote) == ZERO_VAT
    assert Decimal(str(quote["subtotal"])) == Decimal("100.00")
    assert Decimal(str(quote["vat_amount"])) == Decimal("0.00")
    assert Decimal(str(quote["total"])) == Decimal("100.00")


async def test_non_vat_registered_tenant_invoice_has_zero_vat(admin_client: AsyncClient) -> None:
    await _set_vat_registered(admin_client, False)
    contact_id = await _create_contact(admin_client)

    invoice = await _create_invoice(admin_client, contact_id)

    assert _rate(invoice) == ZERO_VAT
    assert Decimal(str(invoice["total"])) == Decimal("100.00")


async def test_quote_to_invoice_conversion_keeps_zero_vat(admin_client: AsyncClient) -> None:
    await _set_vat_registered(admin_client, False)
    contact_id = await _create_contact(admin_client)
    quote = await _create_quote(admin_client, contact_id)

    response = await admin_client.post(f"/quotes/{quote['id']}/convert-to-invoice", json={})

    assert response.status_code == 201, response.text
    invoice = response.json()
    assert _rate(invoice) == ZERO_VAT
    assert Decimal(str(invoice["total"])) == Decimal("100.00")


async def test_vat_registered_tenant_quote_uses_standard_rate(admin_client: AsyncClient) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)

    quote = await _create_quote(admin_client, contact_id)

    assert _rate(quote) == STANDARD_VAT
    assert Decimal(str(quote["vat_amount"])) == Decimal("20.00")
    assert Decimal(str(quote["total"])) == Decimal("120.00")


async def test_vat_registered_tenant_invoice_uses_standard_rate(admin_client: AsyncClient) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)

    invoice = await _create_invoice(admin_client, contact_id)

    assert _rate(invoice) == STANDARD_VAT
    assert Decimal(str(invoice["total"])) == Decimal("120.00")


async def test_explicit_vat_rate_is_still_honoured(admin_client: AsyncClient) -> None:
    """A client that explicitly sends a rate overrides the tenant default."""
    await _set_vat_registered(admin_client, False)
    contact_id = await _create_contact(admin_client)

    quote = await _create_quote(admin_client, contact_id, vat_rate="0.05")

    assert _rate(quote) == Decimal("0.05")
    assert Decimal(str(quote["total"])) == Decimal("105.00")


# --- Per-quote/per-invoice VAT opt-out (issue #110) -------------------------


async def test_vat_registered_quote_opt_out_to_zero(admin_client: AsyncClient) -> None:
    """A VAT-registered tenant can zero-rate a quote (e.g. a new build):
    totals drop to the ex-VAT base, persist, and re-fetch stays consistent."""
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    quote = await _create_quote(admin_client, contact_id)
    assert _rate(quote) == STANDARD_VAT
    assert Decimal(str(quote["vat_amount"])) == Decimal("20.00")
    assert Decimal(str(quote["total"])) == Decimal("120.00")

    response = await admin_client.patch(f"/quotes/{quote['id']}", json={"vat_rate": "0"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert _rate(data) == ZERO_VAT
    assert Decimal(str(data["subtotal"])) == Decimal("100.00")
    assert Decimal(str(data["vat_amount"])) == Decimal("0.00")
    assert Decimal(str(data["total"])) == Decimal("100.00")

    # Re-fetch what a fresh GET returns — stored totals must match.
    fetched = await admin_client.get(f"/quotes/{quote['id']}")
    assert fetched.status_code == 200
    assert _rate(fetched.json()) == ZERO_VAT
    assert Decimal(str(fetched.json()["total"])) == Decimal("100.00")


async def test_vat_registered_quote_opt_out_is_reversible(admin_client: AsyncClient) -> None:
    """Setting exactly the tenant rate back is a no-op-safe restore."""
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    quote = await _create_quote(admin_client, contact_id)

    response = await admin_client.patch(f"/quotes/{quote['id']}", json={"vat_rate": "0"})
    assert response.status_code == 200
    response = await admin_client.patch(f"/quotes/{quote['id']}", json={"vat_rate": "0.20"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert _rate(data) == STANDARD_VAT
    assert Decimal(str(data["vat_amount"])) == Decimal("20.00")
    assert Decimal(str(data["total"])) == Decimal("120.00")


async def test_quote_vat_rate_above_tenant_rate_rejected(admin_client: AsyncClient) -> None:
    """A quote must never charge MORE VAT than the tenant's registered rate."""
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    quote = await _create_quote(admin_client, contact_id)

    response = await admin_client.patch(f"/quotes/{quote['id']}", json={"vat_rate": "0.25"})
    assert response.status_code == 400
    assert "registered VAT rate" in response.json()["detail"]

    # The rejected write must not have touched the quote.
    fetched = await admin_client.get(f"/quotes/{quote['id']}")
    assert _rate(fetched.json()) == STANDARD_VAT
    assert Decimal(str(fetched.json()["total"])) == Decimal("120.00")


async def test_vat_registered_invoice_opt_out_to_zero(admin_client: AsyncClient) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    invoice = await _create_invoice(admin_client, contact_id)
    assert _rate(invoice) == STANDARD_VAT
    assert Decimal(str(invoice["total"])) == Decimal("120.00")

    response = await admin_client.patch(f"/invoices/{invoice['id']}", json={"vat_rate": "0"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert _rate(data) == ZERO_VAT
    assert Decimal(str(data["vat_amount"])) == Decimal("0.00")
    assert Decimal(str(data["total"])) == Decimal("100.00")

    fetched = await admin_client.get(f"/invoices/{invoice['id']}")
    assert fetched.status_code == 200
    assert Decimal(str(fetched.json()["total"])) == Decimal("100.00")


async def test_invoice_vat_rate_above_tenant_rate_rejected(admin_client: AsyncClient) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    invoice = await _create_invoice(admin_client, contact_id)

    response = await admin_client.patch(f"/invoices/{invoice['id']}", json={"vat_rate": "0.25"})
    assert response.status_code == 400
    assert "registered VAT rate" in response.json()["detail"]

    fetched = await admin_client.get(f"/invoices/{invoice['id']}")
    assert _rate(fetched.json()) == STANDARD_VAT


async def test_non_vat_registered_tenant_cannot_raise_vat_on_update(
    admin_client: AsyncClient,
) -> None:
    """A non-registered tenant's registered rate is 0%, so any positive
    per-document override is above the limit; their existing behaviour
    (no vat_rate sent → nothing changes) is untouched."""
    await _set_vat_registered(admin_client, False)
    contact_id = await _create_contact(admin_client)
    quote = await _create_quote(admin_client, contact_id)
    assert _rate(quote) == ZERO_VAT

    response = await admin_client.patch(f"/quotes/{quote['id']}", json={"vat_rate": "0.20"})
    assert response.status_code == 400

    invoice = await _create_invoice(admin_client, contact_id)
    response = await admin_client.patch(f"/invoices/{invoice['id']}", json={"vat_rate": "0.05"})
    assert response.status_code == 400

    # Omitting vat_rate keeps the update path unchanged.
    response = await admin_client.patch(f"/quotes/{quote['id']}", json={"title": "No VAT change"})
    assert response.status_code == 200
    assert _rate(response.json()) == ZERO_VAT
