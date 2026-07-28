"""Tests for transactional email notifications on quote/invoice send."""

from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    return cast("dict[str, Any]", response.json())


async def _create_contact(
    client: AsyncClient, tenant_id: str, name: str, email: str | None = None
) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": email or f"test-{uuid4().hex[:8]}@example.com"},
    )
    assert response.status_code == 201
    return cast("dict[str, Any]", response.json())


async def _create_quote(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Rewire kitchen circuits",
            "line_items": [{"description": "Labour", "quantity": "1", "unit_price": "250.00"}],
        },
    )
    assert response.status_code == 201
    return cast("dict[str, Any]", response.json())


async def _create_invoice(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "line_items": [{"description": "Labour", "quantity": "1", "unit_price": "250.00"}],
        },
    )
    assert response.status_code == 201
    return cast("dict[str, Any]", response.json())


async def test_send_quote_triggers_email(client: AsyncClient) -> None:
    """Sending a quote should call send_email with the contact's address."""
    tenant = await _create_tenant(client, f"email-q-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Alice Smith")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    with patch("app.routers.quotes.send_email", new_callable=AsyncMock) as mock_send:
        response = await client.post(
            f"/quotes/{quote['id']}/send",
            headers={"X-Tenant-ID": tenant["id"]},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.kwargs["to_email"] == contact["email"]
    assert tenant["name"] in call_kwargs.kwargs["subject"]
    # PDF attachment included
    attachments = call_kwargs.kwargs["attachments"]
    assert len(attachments) == 1
    assert attachments[0][1] == "application/pdf"


async def test_send_quote_no_email_contact(client: AsyncClient) -> None:
    """Sending a quote for a contact with no email should not raise."""
    tenant = await _create_tenant(client, f"email-qn-{uuid4().hex[:8]}")
    # Create a contact without an email
    response_no_email = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"name": "No Email Bob"},  # no email key
    )
    assert response_no_email.status_code == 201
    no_email_contact = response_no_email.json()
    quote = await _create_quote(client, tenant["id"], no_email_contact["id"])

    with patch("app.routers.quotes.send_email", new_callable=AsyncMock) as mock_send:
        response = await client.post(
            f"/quotes/{quote['id']}/send",
            headers={"X-Tenant-ID": tenant["id"]},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    mock_send.assert_not_awaited()


async def test_send_quote_email_failure_does_not_fail_request(client: AsyncClient) -> None:
    """An SMTP failure should not cause the endpoint to return an error."""
    tenant = await _create_tenant(client, f"email-qf-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Charlie Brown")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    with patch(
        "app.routers.quotes.send_email",
        new_callable=AsyncMock,
        side_effect=Exception("SMTP unavailable"),
    ):
        response = await client.post(
            f"/quotes/{quote['id']}/send",
            headers={"X-Tenant-ID": tenant["id"]},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"


async def test_send_invoice_triggers_email(client: AsyncClient) -> None:
    """Sending an invoice should call send_email with the contact's address."""
    tenant = await _create_tenant(client, f"email-i-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Diana Prince")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    with patch("app.routers.invoices.send_email", new_callable=AsyncMock) as mock_send:
        response = await client.post(
            f"/invoices/{invoice['id']}/send",
            headers={"X-Tenant-ID": tenant["id"]},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.kwargs["to_email"] == contact["email"]
    assert invoice["invoice_number"] in call_kwargs.kwargs["subject"]
    attachments = call_kwargs.kwargs["attachments"]
    assert len(attachments) == 1
    assert attachments[0][1] == "application/pdf"


async def test_send_invoice_email_failure_does_not_fail_request(client: AsyncClient) -> None:
    """An SMTP failure should not cause the invoice send endpoint to return an error."""
    tenant = await _create_tenant(client, f"email-if-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Eve Adams")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    with patch(
        "app.routers.invoices.send_email",
        new_callable=AsyncMock,
        side_effect=OSError("Connection refused"),
    ):
        response = await client.post(
            f"/invoices/{invoice['id']}/send",
            headers={"X-Tenant-ID": tenant["id"]},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
