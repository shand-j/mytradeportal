"""Tests for Stripe Connect payments (ADR-003).

Covers the staff payments router (status/connect/onboarding-return/settings),
the invoice refund endpoint, and the public invoice ``payment_url`` contract
for the landing /pay page. No live Stripe calls: ``app.stripe_client``
functions are mocked throughout.
"""

import re
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.models import Invoice, StripeAccount, Tenant
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_TOKEN_RE = re.compile(r"https://www\.mytradeportal\.co\.uk/invoice/([A-Za-z0-9_-]+)")


def _tenant_id(admin_client: AsyncClient) -> UUID:
    return UUID(admin_client.headers["X-Tenant-ID"])


async def _create_invoice(admin_client: AsyncClient, tenant_id: UUID) -> dict[str, Any]:
    contact = await admin_client.post("/contacts", json={"name": "Card Payer"})
    assert contact.status_code == 201
    response = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact.json()["id"],
            "invoice_number": f"INV-{uuid4().hex[:6]}",
            "line_items": [
                {"description": "Fuse board works", "quantity": "1", "unit_price": "600.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


# ---------------------------------------------------------------------------
# GET /payments/status + PATCH /payments/settings
# ---------------------------------------------------------------------------


async def test_status_unconfigured_and_disconnected(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    response = await admin_client.get("/payments/status")
    assert response.status_code == 200
    data = response.json()
    assert data["stripe_configured"] is False
    assert data["connected"] is False
    assert data["charges_enabled"] is False
    assert data["accept_card_default"] is False


async def test_settings_patch_toggles_accept_card_default(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    response = await admin_client.patch("/payments/settings", json={"accept_card_default": True})
    assert response.status_code == 200
    assert response.json()["accept_card_default"] is True

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    assert tenant.settings["payments"]["accept_card_default"] is True

    response = await admin_client.patch("/payments/settings", json={"accept_card_default": False})
    assert response.status_code == 200
    assert response.json()["accept_card_default"] is False


# ---------------------------------------------------------------------------
# POST /payments/connect + GET /payments/onboarding-return
# ---------------------------------------------------------------------------


async def test_connect_503_when_stripe_unconfigured(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    response = await admin_client.post(
        "/payments/connect",
        json={"return_url": "https://app.example/ok", "refresh_url": "https://app.example/re"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "payments_not_configured"


async def test_connect_returns_onboarding_url_and_reuses_account(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_account = AsyncMock(return_value={"id": "acct_test_1"})
    account_link = AsyncMock(return_value="https://connect.stripe.com/setup/s/test")
    monkeypatch.setattr("app.stripe_client.create_express_account", create_account)
    monkeypatch.setattr("app.stripe_client.create_account_link", account_link)

    payload = {"return_url": "https://app.example/ok", "refresh_url": "https://app.example/re"}
    response = await admin_client.post("/payments/connect", json=payload)
    assert response.status_code == 200
    assert response.json()["onboarding_url"] == "https://connect.stripe.com/setup/s/test"

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    account = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id))
    assert account is not None
    assert account.stripe_account_id == "acct_test_1"
    assert account.onboarding_complete is False

    # A second connect reuses the existing Express account, only minting a
    # fresh onboarding link.
    response = await admin_client.post("/payments/connect", json=payload)
    assert response.status_code == 200
    create_account.assert_awaited_once()
    assert account_link.await_count == 2


async def test_onboarding_return_syncs_flags(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    retrieve = AsyncMock(
        return_value={
            "id": "acct_test_2",
            "details_submitted": True,
            "charges_enabled": True,
            "payouts_enabled": True,
        }
    )
    monkeypatch.setattr("app.stripe_client.retrieve_account", retrieve)

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    db.add(StripeAccount(tenant_id=tenant_id, stripe_account_id="acct_test_2"))
    await db.commit()

    response = await admin_client.get("/payments/onboarding-return")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Card payments are ready" in response.text

    account = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id))
    assert account is not None
    assert account.charges_enabled is True
    assert account.payouts_enabled is True
    assert account.onboarding_complete is True

    status = await admin_client.get("/payments/status")
    assert status.json()["connected"] is True
    assert status.json()["charges_enabled"] is True


# ---------------------------------------------------------------------------
# POST /invoices/{id}/refund
# ---------------------------------------------------------------------------


async def test_refund_rejects_manually_paid_invoice(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_refund = AsyncMock(return_value={"id": "re_1", "status": "succeeded"})
    monkeypatch.setattr("app.stripe_client.create_refund", create_refund)

    tenant_id = _tenant_id(admin_client)
    invoice = await _create_invoice(admin_client, tenant_id)
    paid = await admin_client.post(f"/invoices/{invoice['id']}/mark-paid")
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"

    # Manually marked-paid invoices are refunded outside the platform.
    response = await admin_client.post(f"/invoices/{invoice['id']}/refund")
    assert response.status_code == 409
    create_refund.assert_not_called()


async def test_refund_stripe_paid_invoice_then_double_refund_409(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_refund = AsyncMock(return_value={"id": "re_1", "status": "succeeded"})
    monkeypatch.setattr("app.stripe_client.create_refund", create_refund)

    tenant_id = _tenant_id(admin_client)
    invoice = await _create_invoice(admin_client, tenant_id)

    await set_tenant_in_session(db, tenant_id)
    row = await db.get(Invoice, UUID(invoice["id"]))
    assert row is not None
    row.status = "paid"
    row.paid_via = "stripe"
    row.stripe_payment_intent_id = "pi_refund_1"
    await db.commit()

    response = await admin_client.post(f"/invoices/{invoice['id']}/refund")
    assert response.status_code == 200
    assert response.json()["status"] == "refunded"
    create_refund.assert_awaited_once_with("pi_refund_1")

    response = await admin_client.post(f"/invoices/{invoice['id']}/refund")
    assert response.status_code == 409
    create_refund.assert_awaited_once()


# ---------------------------------------------------------------------------
# Public invoice payment_url (landing /pay page contract)
# ---------------------------------------------------------------------------


async def _setup_public_invoice(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    *,
    connected: bool = True,
    accept_default: bool = True,
    existing_intent: str | None = None,
) -> tuple[Tenant, dict[str, Any], str]:
    """Create a tenant + sent invoice and return (tenant, invoice, raw token)."""
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.invoices.send_email", send_email)

    tenant_resp = await client.post(
        "/tenants", json={"slug": f"pay-{uuid4().hex[:8]}", "name": "Pay Ltd"}
    )
    assert tenant_resp.status_code == 201
    tenant_id = tenant_resp.json()["id"]
    headers = {"X-Tenant-ID": tenant_id}

    contact = await client.post(
        "/contacts",
        headers=headers,
        json={"name": "Payer Homeowner", "email": "payer.homeowner@example.com"},
    )
    assert contact.status_code == 201
    invoice_resp = await client.post(
        "/invoices",
        headers=headers,
        json={
            "contact_id": contact.json()["id"],
            "invoice_number": f"INV-{uuid4().hex[:6]}",
            "line_items": [
                {"description": "Fuse board works", "quantity": "1", "unit_price": "600.00"},
            ],
        },
    )
    assert invoice_resp.status_code == 201
    invoice = invoice_resp.json()

    tenant_uuid = UUID(tenant_id)
    await set_tenant_in_session(db, tenant_uuid)
    tenant = await db.get(Tenant, tenant_uuid)
    assert tenant is not None
    tenant.settings = {"payments": {"accept_card_default": accept_default}}
    if connected:
        db.add(
            StripeAccount(
                tenant_id=tenant_uuid,
                stripe_account_id="acct_conn_1",
                details_submitted=True,
                charges_enabled=True,
                payouts_enabled=True,
                onboarding_complete=True,
            )
        )
    if existing_intent is not None:
        invoice_row = await db.get(Invoice, UUID(invoice["id"]))
        assert invoice_row is not None
        invoice_row.stripe_payment_intent_id = existing_intent
    await db.commit()

    sent = await client.post(f"/invoices/{invoice['id']}/send", headers=headers)
    assert sent.status_code == 200
    send_email.assert_awaited_once()
    assert send_email.await_args is not None
    html: str = send_email.await_args.kwargs["html_body"]
    match = _TOKEN_RE.search(html)
    assert match is not None
    return tenant, invoice, match.group(1)


async def test_public_invoice_payment_url_when_connected_and_enabled(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock(return_value={"id": "pi_123", "client_secret": "pi_123_secret_abc"})
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    tenant, invoice, raw = await _setup_public_invoice(client, db, monkeypatch)

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    payment_url = response.json()["payment_url"]
    assert payment_url == (
        f"https://www.mytradeportal.co.uk/pay/{raw}?pi=pi_123&cs=pi_123_secret_abc"
    )

    # Destination charge on the tenant's connected account, full invoice total.
    assert create_intent.await_args is not None
    kwargs = create_intent.await_args.kwargs
    assert kwargs["amount_pence"] == 60000
    assert kwargs["currency"] == "gbp"
    assert kwargs["connected_account_id"] == "acct_conn_1"
    assert kwargs["invoice_id"] == invoice["id"]
    assert kwargs["tenant_id"] == str(tenant.id)

    # The intent is persisted so later views reuse it.
    await set_tenant_in_session(db, tenant.id)
    invoice_row = await db.get(Invoice, UUID(invoice["id"]))
    assert invoice_row is not None
    assert invoice_row.stripe_payment_intent_id == "pi_123"


async def test_public_invoice_reuses_open_payment_intent(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock()
    retrieve_intent = AsyncMock(
        return_value={
            "id": "pi_existing",
            "client_secret": "cs_existing",
            "status": "requires_payment_method",
            "amount": 60000,
        }
    )
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)
    monkeypatch.setattr("app.stripe_client.retrieve_payment_intent", retrieve_intent)

    _, _, raw = await _setup_public_invoice(client, db, monkeypatch, existing_intent="pi_existing")

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] == (
        f"https://www.mytradeportal.co.uk/pay/{raw}?pi=pi_existing&cs=cs_existing"
    )
    create_intent.assert_not_called()


async def test_public_invoice_no_payment_url_when_toggle_off(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock()
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    _, _, raw = await _setup_public_invoice(client, db, monkeypatch, accept_default=False)

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] is None
    create_intent.assert_not_called()


async def test_public_invoice_no_payment_url_when_not_connected(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_intent = AsyncMock()
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)

    _, _, raw = await _setup_public_invoice(client, db, monkeypatch, connected=False)

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] is None
    create_intent.assert_not_called()


async def test_public_invoice_no_payment_url_when_stripe_unconfigured(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    _, _, raw = await _setup_public_invoice(client, db, monkeypatch)

    response = await client.get(f"/public/invoice/{raw}")
    assert response.status_code == 200
    assert response.json()["payment_url"] is None
