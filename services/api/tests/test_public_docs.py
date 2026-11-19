"""Tests for the public quote/invoice web-view endpoints and token issuing.

Covers: send_quote/send_invoice mint a DocumentAccessToken and email the
landing-site link; GET /public/{kind}/{token} returns a safe render payload;
unknown/expired/revoked/kind-mismatched tokens all 404 indistinguishably;
re-sending revokes the previous link.
"""

import re
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.models import DocumentAccessToken, Invoice, StripeAccount, Tenant
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
                {"description": "Labour", "quantity": "2", "unit_price": "75.00"},
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


def _awaited_html(send_email: AsyncMock) -> str:
    call = send_email.await_args
    assert call is not None
    html: str = call.kwargs["html_body"]
    return html


# ---------------------------------------------------------------------------
# Token issuing at send time
# ---------------------------------------------------------------------------


async def test_send_quote_mints_token_and_emails_landing_link(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: dict[str, Any] = {}

    async def fake_send_customer_email(db: Any = None, **kwargs: Any) -> bool:
        sent.update(kwargs)
        return True

    monkeypatch.setattr("app.routers.quotes.send_customer_email", fake_send_customer_email)

    tenant = await _create_tenant(client, f"pub-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Homeowner")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200

    raw = _extract_token(sent["html_body"], "quote")
    record = await db.scalar(
        select(DocumentAccessToken).where(
            DocumentAccessToken.token_hash == hash_document_token(raw)
        )
    )
    assert record is not None
    assert record.kind == "quote"
    assert str(record.document_id) == quote["id"]
    assert str(record.tenant_id) == tenant["id"]
    assert record.contact_email == contact["email"]
    assert record.revoked_at is None
    assert record.expires_at > datetime.utcnow() + timedelta(days=29)


async def test_send_invoice_mints_token_and_emails_landing_link(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.invoices.send_customer_email", send_email)

    tenant = await _create_tenant(client, f"pub-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Invoice Homeowner")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/invoices/{invoice['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200

    send_email.assert_awaited_once()
    raw = _extract_token(_awaited_html(send_email), "invoice")
    record = await db.scalar(
        select(DocumentAccessToken).where(
            DocumentAccessToken.token_hash == hash_document_token(raw)
        )
    )
    assert record is not None
    assert record.kind == "invoice"
    assert str(record.document_id) == invoice["id"]


async def test_resend_revokes_previous_token(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    bodies: list[str] = []

    async def fake_send_customer_email(db: Any = None, **kwargs: Any) -> bool:
        bodies.append(kwargs["html_body"])
        return True

    monkeypatch.setattr("app.routers.quotes.send_customer_email", fake_send_customer_email)

    tenant = await _create_tenant(client, f"pub-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Resend Homeowner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    headers = {"X-Tenant-ID": tenant["id"]}

    assert (await client.post(f"/quotes/{quote['id']}/send", headers=headers)).status_code == 200
    assert (await client.post(f"/quotes/{quote['id']}/send", headers=headers)).status_code == 200

    first = _extract_token(bodies[0], "quote")
    second = _extract_token(bodies[1], "quote")
    assert first != second

    # Only the newest link opens the document.
    assert (await client.get(f"/public/quote/{first}")).status_code == 404
    assert (await client.get(f"/public/quote/{second}")).status_code == 200


# ---------------------------------------------------------------------------
# Public render endpoint
# ---------------------------------------------------------------------------


async def _send_quote_and_get_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], dict[str, Any], str]:
    sent: dict[str, Any] = {}

    async def fake_send_customer_email(db: Any = None, **kwargs: Any) -> bool:
        sent.update(kwargs)
        return True

    monkeypatch.setattr("app.routers.quotes.send_customer_email", fake_send_customer_email)

    tenant = await _create_tenant(client, f"pub-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "View Homeowner")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200
    return tenant, quote, _extract_token(sent["html_body"], "quote")


async def test_public_quote_payload_is_safe(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, quote, raw = await _send_quote_and_get_token(client, monkeypatch)

    response = await client.get(f"/public/quote/{raw}")
    assert response.status_code == 200
    data = response.json()

    assert data["kind"] == "quote"
    assert data["status"] == "sent"
    assert data["title"] == "Fuse board replacement"
    assert data["customer_first_name"] == "View"
    assert data["tenant"]["name"] == tenant["name"]
    assert data["tenant"]["brand_color"]
    assert data["subtotal"] == "600.00"
    # Test tenants are not VAT-registered, so VAT is 0 — just assert the
    # totals are internally consistent.
    assert float(data["total"]) == float(data["subtotal"]) + float(data["vat_amount"])
    assert len(data["lines"]) == 2
    assert data["lines"][0]["description"] == "Consumer unit"
    assert data["payment_url"] is None

    # No internal ids or contact PII beyond the first name.
    assert quote["id"] not in response.text
    assert tenant["id"] not in response.text
    assert "view.homeowner@example.com" not in response.text
    assert "contact_id" not in data
    assert "document_id" not in data


async def test_public_invoice_payload_without_paddle_has_no_payment_url(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.invoices.send_customer_email", send_email)
    # Paddle is unconfigured in tests, so checkout creation must degrade to
    # payment_url=None rather than break the page.
    tenant = await _create_tenant(client, f"pub-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Payer Homeowner")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])
    response = await client.post(
        f"/invoices/{invoice['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200
    raw = _extract_token(_awaited_html(send_email), "invoice")

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    data = response.json()
    assert data["kind"] == "invoice"
    assert data["status"] == "sent"
    assert data["invoice_number"] == invoice["invoice_number"]
    assert data["total"] == invoice["total"]
    assert data["payment_url"] is None
    assert data["customer_first_name"] == "Payer"


async def test_public_invoice_paid_has_no_payment_url(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.invoices.send_customer_email", send_email)
    tenant = await _create_tenant(client, f"pub-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Paid Homeowner")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])
    headers = {"X-Tenant-ID": tenant["id"]}
    assert (
        await client.post(f"/invoices/{invoice['id']}/send", headers=headers)
    ).status_code == 200
    raw = _extract_token(_awaited_html(send_email), "invoice")
    assert (
        await client.post(f"/invoices/{invoice['id']}/mark-paid", headers=headers)
    ).status_code == 200

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "paid"
    assert data["paid_at"] is not None
    assert data["payment_url"] is None


# ---------------------------------------------------------------------------
# 404 behaviour — no enumeration
# ---------------------------------------------------------------------------


async def test_public_doc_unknown_token_404s(client: AsyncClient) -> None:
    response = await client.get("/public/quote/" + "x" * 43)
    assert response.status_code == 404


async def test_public_doc_kind_mismatch_404s(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    # A valid quote token presented as an invoice must not leak anything.
    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 404


async def test_public_doc_expired_token_404s(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, raw = await _send_quote_and_get_token(client, monkeypatch)
    record = await db.scalar(
        select(DocumentAccessToken).where(
            DocumentAccessToken.token_hash == hash_document_token(raw)
        )
    )
    assert record is not None
    record.expires_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    response = await client.get(f"/public/quote/{raw}")
    assert response.status_code == 404


async def test_public_doc_bad_kind_404s(client: AsyncClient) -> None:
    response = await client.get("/public/contract/" + "x" * 43)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# payment_url contract matrix (Stripe Connect /pay page)
# ---------------------------------------------------------------------------


async def _sent_card_invoice(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    *,
    connected: bool = True,
    charges_enabled: bool = True,
    accept_default: bool = True,
) -> tuple[str, dict[str, Any], str]:
    """Tenant + (optional) Stripe Connect account + sent invoice + raw token."""
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.invoices.send_customer_email", send_email)

    tenant = await _create_tenant(client, f"pay-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Matrix Homeowner")
    invoice = await _create_invoice(client, tenant["id"], contact["id"])

    tenant_uuid = UUID(tenant["id"])
    await set_tenant_in_session(db, tenant_uuid)
    tenant_row = await db.get(Tenant, tenant_uuid)
    assert tenant_row is not None
    tenant_row.settings = {"payments": {"accept_card_default": accept_default}}
    if connected:
        db.add(
            StripeAccount(
                tenant_id=tenant_uuid,
                stripe_account_id="acct_matrix_1",
                details_submitted=True,
                charges_enabled=charges_enabled,
                payouts_enabled=charges_enabled,
                onboarding_complete=charges_enabled,
            )
        )
    await db.commit()

    response = await client.post(
        f"/invoices/{invoice['id']}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert response.status_code == 200
    raw = _extract_token(_awaited_html(send_email), "invoice")
    return tenant["id"], invoice, raw


async def test_payment_url_null_when_account_not_charges_enabled(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock()
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    _, _, raw = await _sent_card_invoice(client, db, monkeypatch, charges_enabled=False)

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] is None
    create_intent.assert_not_called()


async def test_payment_url_null_when_tenant_default_on_but_invoice_override_off(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock()
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    tenant_id, invoice, raw = await _sent_card_invoice(client, db, monkeypatch)
    response = await client.patch(
        f"/invoices/{invoice['id']}",
        headers={"X-Tenant-ID": tenant_id},
        json={"accept_card_payments": False},
    )
    assert response.status_code == 200
    assert response.json()["accept_card_payments"] is False

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] is None
    # The send minted the intent while the tenant default was still on; the
    # override-off view must not mint another one.
    create_intent.assert_called_once()


async def test_payment_url_present_when_tenant_default_off_but_invoice_override_on(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock(return_value={"id": "pi_override", "client_secret": "cs_override"})
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    tenant_id, invoice, raw = await _sent_card_invoice(
        client, db, monkeypatch, accept_default=False
    )
    response = await client.patch(
        f"/invoices/{invoice['id']}",
        headers={"X-Tenant-ID": tenant_id},
        json={"accept_card_payments": True},
    )
    assert response.status_code == 200

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] == (
        f"https://www.mytradeportal.co.uk/pay/{raw}?pi=pi_override&cs=cs_override"
    )


async def test_payment_url_null_when_invoice_cancelled(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock()
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    tenant_id, invoice, raw = await _sent_card_invoice(client, db, monkeypatch)
    response = await client.post(
        f"/invoices/{invoice['id']}/cancel", headers={"X-Tenant-ID": tenant_id}
    )
    assert response.status_code == 200

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"
    assert data["payment_url"] is None
    # The send minted the intent while the invoice was still payable; the
    # cancelled view must not mint another one.
    create_intent.assert_called_once()


async def test_payment_url_null_when_invoice_refunded(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock()
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    tenant_id, invoice, raw = await _sent_card_invoice(client, db, monkeypatch)
    await set_tenant_in_session(db, UUID(tenant_id))
    invoice_row = await db.get(Invoice, UUID(invoice["id"]))
    assert invoice_row is not None
    invoice_row.status = "refunded"
    await db.commit()

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refunded"
    assert data["payment_url"] is None
    # The send minted the intent while the invoice was still payable; the
    # refunded view must not mint another one.
    create_intent.assert_called_once()


async def test_payment_url_null_not_500_when_stripe_client_raises(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Stripe outage must degrade to a missing Pay button, never break the
    public document page."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock(side_effect=RuntimeError("stripe api down"))
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    _, _, raw = await _sent_card_invoice(client, db, monkeypatch)

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] is None


async def test_payment_url_reuses_open_intent_on_second_fetch(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The send creates the PaymentIntent; later views reuse the open one —
    no duplicate intents for the same unpaid invoice."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock(return_value={"id": "pi_reuse", "client_secret": "cs_reuse"})
    retrieve_intent = AsyncMock(
        return_value={
            "id": "pi_reuse",
            "client_secret": "cs_reuse",
            "status": "requires_payment_method",
            "amount": 60000,
        }
    )
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)
    monkeypatch.setattr("app.stripe_client.retrieve_payment_intent", retrieve_intent)

    _, _, raw = await _sent_card_invoice(client, db, monkeypatch)

    first = await client.get(f"/public/invoice/{raw}")
    second = await client.get(f"/public/invoice/{raw}")
    assert first.status_code == 200
    assert second.status_code == 200
    expected = f"https://www.mytradeportal.co.uk/pay/{raw}?pi=pi_reuse&cs=cs_reuse"
    assert first.json()["payment_url"] == expected
    assert second.json()["payment_url"] == expected
    create_intent.assert_awaited_once()
    # Both views reuse the open intent minted at send time.
    assert retrieve_intent.await_count == 2
    retrieve_intent.assert_awaited_with("pi_reuse")


async def test_payment_url_creates_fresh_intent_when_existing_one_abandoned(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A canceled/terminal stored intent must not be reused — a fresh one is
    created and re-persisted."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock(return_value={"id": "pi_fresh", "client_secret": "cs_fresh"})
    retrieve_intent = AsyncMock(
        return_value={
            "id": "pi_dead",
            "client_secret": "cs_dead",
            "status": "canceled",
            "amount": 60000,
        }
    )
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)
    monkeypatch.setattr("app.stripe_client.retrieve_payment_intent", retrieve_intent)

    tenant_id, invoice, raw = await _sent_card_invoice(client, db, monkeypatch)
    await set_tenant_in_session(db, UUID(tenant_id))
    invoice_row = await db.get(Invoice, UUID(invoice["id"]))
    assert invoice_row is not None
    invoice_row.stripe_payment_intent_id = "pi_dead"
    await db.commit()

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] == (
        f"https://www.mytradeportal.co.uk/pay/{raw}?pi=pi_fresh&cs=cs_fresh"
    )
    # One mint at send, a second when the stored intent turned out to be dead.
    assert create_intent.await_count == 2
