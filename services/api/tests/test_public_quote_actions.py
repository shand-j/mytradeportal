"""Tests for the token-authorized public quote actions and invoice fallback.

Covers: POST /public/quote/{token}/accept and /decline round-trips (state
transition, staff notification, outcome event, confirmation email, preferred
dates); uniform 404s for unknown/expired/kind-mismatched tokens; 409 on
non-actionable statuses; and the invoice payload's bank-details fallback when
Stripe card payment is not available.
"""

import re
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.models import DocumentAccessToken, Notification, Quote, Tenant
from app.rls import set_tenant_in_session
from app.routers.public_docs import hash_document_token
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_TOKEN_RE = re.compile(r"https://www\.mytradeportal\.co\.uk/(quote|invoice)/([A-Za-z0-9_-]+)")


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
            "title": "Fuse board replacement",
            "line_items": [
                {"description": "Consumer unit", "quantity": "1", "unit_price": "450.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_invoice(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "invoice_number": f"INV-{uuid4().hex[:6]}",
            "line_items": [
                {"description": "Fuse board works", "quantity": "1", "unit_price": "600.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


def _extract_token(html: str, kind: str) -> str:
    match = _TOKEN_RE.search(html)
    assert match is not None, f"no {kind} link found in email body"
    assert match.group(1) == kind
    return match.group(2)


async def _send_quote_and_get_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """Tenant, contact, quote and the raw emailed document token."""
    sent: dict[str, Any] = {}

    async def fake_send_customer_email(db: Any = None, **kwargs: Any) -> bool:
        sent.update(kwargs)
        return True

    monkeypatch.setattr("app.routers.quotes.send_customer_email", fake_send_customer_email)

    tenant = await _create_tenant(client, f"act-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Action Homeowner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200
    return tenant, contact, quote, _extract_token(sent["html_body"], "quote")


# ---------------------------------------------------------------------------
# Accept round-trip
# ---------------------------------------------------------------------------


async def test_public_accept_quote_round_trip(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, contact, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    confirmation: dict[str, Any] = {}

    async def fake_confirmation_email(db: Any = None, **kwargs: Any) -> bool:
        confirmation.update(kwargs)
        return True

    monkeypatch.setattr("app.quote_acceptance.send_customer_email", fake_confirmation_email)
    outcome = AsyncMock(return_value=None)
    monkeypatch.setattr("app.quote_acceptance.record_quote_outcome", outcome)

    response = await client.post(
        f"/public/quote/{raw}/accept",
        json={"preferred_dates": [{"date": "2026-09-21"}, {"date": "2026-09-23"}]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["kind"] == "quote"
    assert data["status"] == "approved"

    tenant_uuid = UUID(tenant["id"])
    await set_tenant_in_session(db, tenant_uuid)
    quote_row = await db.get(Quote, UUID(quote["id"]))
    assert quote_row is not None
    assert quote_row.status == "approved"
    assert quote_row.approved_at is not None
    assert quote_row.accepted_dates == ["2026-09-21", "2026-09-23"]

    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant_uuid,
            Notification.type == "quote_accepted",
        )
    )
    assert notification is not None
    assert notification.link == f"/quotes/{quote['id']}"
    assert "Action Homeowner" in notification.body
    assert "2026-09-21" in notification.body

    outcome.assert_awaited_once()
    assert outcome.await_args is not None
    assert outcome.await_args.kwargs["outcome"] == "quote_accepted"
    assert outcome.await_args.kwargs["extra_payload"]["channel"] == "email_link"

    # The acceptance-confirmation email goes to the token's recipient.
    assert confirmation["to_email"] == contact["email"]
    assert confirmation["event"] == "quote_accepted"
    assert tenant["name"] in confirmation["subject"]


async def test_public_accept_quote_without_body(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    monkeypatch.setattr("app.quote_acceptance.send_customer_email", AsyncMock(return_value=True))

    response = await client.post(f"/public/quote/{raw}/accept")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"

    await set_tenant_in_session(db, UUID(tenant["id"]))
    quote_row = await db.get(Quote, UUID(quote["id"]))
    assert quote_row is not None
    assert quote_row.status == "approved"
    assert not quote_row.accepted_dates


# ---------------------------------------------------------------------------
# Decline round-trip
# ---------------------------------------------------------------------------


async def test_public_decline_quote_round_trip(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)

    response = await client.post(f"/public/quote/{raw}/decline")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"

    await set_tenant_in_session(db, UUID(tenant["id"]))
    quote_row = await db.get(Quote, UUID(quote["id"]))
    assert quote_row is not None
    assert quote_row.status == "rejected"
    assert quote_row.approved_at is None


# ---------------------------------------------------------------------------
# 404 behaviour — no enumeration
# ---------------------------------------------------------------------------


async def test_public_action_unknown_token_404s(client: AsyncClient) -> None:
    token = "x" * 43
    assert (await client.post(f"/public/quote/{token}/accept")).status_code == 404
    assert (await client.post(f"/public/quote/{token}/decline")).status_code == 404


async def test_public_action_expired_token_404s(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    record = await db.scalar(
        select(DocumentAccessToken).where(
            DocumentAccessToken.token_hash == hash_document_token(raw)
        )
    )
    assert record is not None
    record.expires_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    assert (await client.post(f"/public/quote/{raw}/accept")).status_code == 404
    assert (await client.post(f"/public/quote/{raw}/decline")).status_code == 404


async def test_public_action_kind_mismatch_404s(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invoice token must not authorize quote actions."""
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.invoices.send_customer_email", send_email)
    tenant = await _create_tenant(client, f"act-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Mismatch Homeowner")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])
    response = await client.post(
        f"/invoices/{invoice['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200
    assert send_email.await_args is not None
    raw = _extract_token(send_email.await_args.kwargs["html_body"], "invoice")

    assert (await client.post(f"/public/quote/{raw}/accept")).status_code == 404
    assert (await client.post(f"/public/quote/{raw}/decline")).status_code == 404


# ---------------------------------------------------------------------------
# 409 on non-actionable statuses
# ---------------------------------------------------------------------------


async def test_public_re_accept_409(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    monkeypatch.setattr("app.quote_acceptance.send_customer_email", AsyncMock(return_value=True))

    first = await client.post(f"/public/quote/{raw}/accept")
    assert first.status_code == 200

    second = await client.post(f"/public/quote/{raw}/accept")
    assert second.status_code == 409
    decline = await client.post(f"/public/quote/{raw}/decline")
    assert decline.status_code == 409


async def test_public_accept_after_decline_409(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, raw = await _send_quote_and_get_token(client, monkeypatch)

    decline = await client.post(f"/public/quote/{raw}/decline")
    assert decline.status_code == 200
    accept = await client.post(f"/public/quote/{raw}/accept")
    assert accept.status_code == 409


async def test_public_accept_invoiced_quote_409(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, _, quote, raw = await _send_quote_and_get_token(client, monkeypatch)
    await set_tenant_in_session(db, UUID(tenant["id"]))
    quote_row = await db.get(Quote, UUID(quote["id"]))
    assert quote_row is not None
    quote_row.status = "invoiced"
    await db.commit()

    response = await client.post(f"/public/quote/{raw}/accept")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Invoice bank-details fallback
# ---------------------------------------------------------------------------


async def _sent_invoice_payload(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: dict[str, Any] | None,
) -> dict[str, Any]:
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.invoices.send_customer_email", send_email)
    tenant = await _create_tenant(client, f"act-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Payer Homeowner")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])
    if settings is not None:
        await set_tenant_in_session(db, UUID(tenant["id"]))
        tenant_row = await db.get(Tenant, UUID(tenant["id"]))
        assert tenant_row is not None
        tenant_row.settings = settings
        await db.commit()
    response = await client.post(
        f"/invoices/{invoice['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200
    assert send_email.await_args is not None
    raw = _extract_token(send_email.await_args.kwargs["html_body"], "invoice")

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    assert payload["invoice_number"] == invoice["invoice_number"]
    return payload


async def test_public_invoice_payload_includes_bank_details_when_configured(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = await _sent_invoice_payload(
        client,
        db,
        monkeypatch,
        settings={
            "bank_account_name": "Sparky Ltd",
            "bank_sort_code": "04-06-05",
            "bank_account_number": "12345678",
        },
    )
    # Stripe is unconfigured in tests, so the bank details are the only CTA.
    assert payload["payment_url"] is None
    assert payload["payment_details"] == {
        "account_name": "Sparky Ltd",
        "sort_code": "04-06-05",
        "account_number": "12345678",
        "reference": payload["invoice_number"],
    }


async def test_public_invoice_payload_payment_details_null_without_bank_settings(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = await _sent_invoice_payload(client, db, monkeypatch, settings=None)
    assert payload["payment_url"] is None
    assert payload["payment_details"] is None


async def test_public_quote_payload_has_no_payment_details(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    response = await client.get(f"/public/quote/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_details"] is None
