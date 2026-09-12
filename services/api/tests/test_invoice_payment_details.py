"""Tests for invoice bank-transfer payment details (tenant settings → invoice email)."""

from typing import Any

import pytest
from app.email_templates import invoice_sent as invoice_sent_template
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Template unit tests
# ---------------------------------------------------------------------------


def test_invoice_template_omits_payment_block_without_details() -> None:
    subject, html, text = invoice_sent_template(
        customer_name="Bob",
        business_name="Sparky Ltd",
        invoice_number="INV-001",
        invoice_total="£600.00",
    )
    assert subject == "Invoice INV-001 from Sparky Ltd"
    assert "bank transfer" not in html.lower()
    assert "bank transfer" not in text.lower()


def test_invoice_template_renders_payment_block() -> None:
    _, html, text = invoice_sent_template(
        customer_name="Bob",
        business_name="Sparky Ltd",
        invoice_number="INV-001",
        invoice_total="£600.00",
        payment_details={
            "account_name": "J Smith Electrical Ltd",
            "sort_code": "12-34-56",
            "account_number": "12345678",
            "reference": "INV-001",
        },
    )
    for value in ("J Smith Electrical Ltd", "12-34-56", "12345678", "INV-001"):
        assert value in html
        assert value in text
    assert "Account name" in html
    assert "Sort code" in html
    assert "Account number" in html
    assert "Payment reference" in html


def test_invoice_template_escapes_payment_details_html() -> None:
    _, html, _ = invoice_sent_template(
        customer_name="Bob",
        business_name="Sparky Ltd",
        invoice_number="INV-001",
        invoice_total="£600.00",
        payment_details={
            "account_name": "<script>alert(1)</script>",
            "sort_code": "",
            "account_number": "",
            "reference": "INV-001",
        },
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Integration: settings keys → invoice send email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoice_email_includes_tenant_bank_details(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id = admin_client.headers["X-Tenant-ID"]

    response = await admin_client.patch(
        "/tenants/me",
        json={
            "settings": {
                "bank_account_name": "Test Electrical Ltd",
                "bank_sort_code": "12-34-56",
                "bank_account_number": "12345678",
            }
        },
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["bank_account_name"] == "Test Electrical Ltd"
    assert settings["bank_sort_code"] == "12-34-56"
    assert settings["bank_account_number"] == "12345678"

    contact_response = await admin_client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": "Bob Builder", "email": "bob.builder@example.com"},
    )
    assert contact_response.status_code == 201
    contact = contact_response.json()

    invoice_response = await admin_client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact["id"],
            "line_items": [{"description": "Labour", "quantity": "1", "unit_price": "100.00"}],
        },
    )
    assert invoice_response.status_code == 201
    invoice = invoice_response.json()

    sent: list[dict[str, Any]] = []

    async def _fake_send_email(**kwargs: Any) -> dict[str, Any]:
        sent.append(kwargs)
        return {"id": "test"}

    monkeypatch.setattr("app.routers.invoices.send_email", _fake_send_email)

    send_response = await admin_client.post(
        f"/invoices/{invoice['id']}/send",
        headers={"X-Tenant-ID": tenant_id},
    )
    assert send_response.status_code == 200
    assert len(sent) == 1
    email = sent[0]
    for value in ("Test Electrical Ltd", "12-34-56", "12345678"):
        assert value in email["html_body"]
        assert value in email["text_body"]
    # Payment reference defaults to the invoice number.
    assert invoice["invoice_number"] in email["html_body"]
    assert "Payment reference" in email["html_body"]


@pytest.mark.asyncio
async def test_invoice_email_without_bank_details_omits_block(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id = admin_client.headers["X-Tenant-ID"]

    contact_response = await admin_client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": "Alice", "email": "alice@example.com"},
    )
    assert contact_response.status_code == 201
    contact = contact_response.json()

    invoice_response = await admin_client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact["id"],
            "line_items": [{"description": "Labour", "quantity": "1", "unit_price": "100.00"}],
        },
    )
    assert invoice_response.status_code == 201
    invoice = invoice_response.json()

    sent: list[dict[str, Any]] = []

    async def _fake_send_email(**kwargs: Any) -> dict[str, Any]:
        sent.append(kwargs)
        return {"id": "test"}

    monkeypatch.setattr("app.routers.invoices.send_email", _fake_send_email)

    send_response = await admin_client.post(
        f"/invoices/{invoice['id']}/send",
        headers={"X-Tenant-ID": tenant_id},
    )
    assert send_response.status_code == 200
    assert len(sent) == 1
    assert "bank transfer" not in sent[0]["html_body"].lower()
    assert "bank transfer" not in sent[0]["text_body"].lower()
