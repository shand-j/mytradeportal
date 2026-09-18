"""Tests for Stripe Connect payments (ADR-003).

Covers the staff payments router (status/connect/onboarding-return/settings),
the invoice refund endpoint, and the public invoice ``payment_url`` contract
for the landing /pay page. No live Stripe calls: ``app.stripe_client``
functions are mocked throughout.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.logging import configure_logging
from app.models import Invoice, Payment, StripeAccount, Tenant
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

# Route structlog through stdlib so caplog can assert the connect_failed log
# event. Import time is safe: pytest imports every test module during
# collection, before any test runs and therefore before any structlog logger
# proxy caches its factory (the app configures logging only in its lifespan).
configure_logging("INFO")

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


async def test_connect_503_payments_unavailable_when_stripe_rejects_account(
    admin_client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Platform not enrolled in Connect → clean 503 + connect_failed log, never a 500 (#115)."""
    from app import stripe_client

    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_account = AsyncMock(
        side_effect=stripe_client.StripeV2Error(
            400,
            "accounts_v2_access_blocked",
            "Accounts v2 is not enabled for your merchant.",
        )
    )
    monkeypatch.setattr("app.stripe_client.create_connected_account_v2", create_account)

    payload = {"return_url": "https://app.example/ok", "refresh_url": "https://app.example/re"}
    with caplog.at_level("ERROR", logger="api.payments"):
        response = await admin_client.post("/payments/connect", json=payload)

    assert response.status_code == 503
    assert response.json()["detail"] == "payments_unavailable"
    assert create_account.await_count == 1
    connect_failures = [
        record for record in caplog.records if "connect_failed" in record.getMessage()
    ]
    assert len(connect_failures) == 1
    assert "StripeV2Error" in connect_failures[0].getMessage()

    # No half-written StripeAccount row is left behind.
    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    account = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id))
    assert account is None


async def test_connect_returns_onboarding_url_and_reuses_account(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_account = AsyncMock(return_value={"id": "acct_test_1"})
    account_link = AsyncMock(return_value="https://connect.stripe.com/setup/s/test")
    monkeypatch.setattr("app.stripe_client.create_connected_account_v2", create_account)
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
# POST /payments/connect/session (embedded onboarding AccountSession)
# ---------------------------------------------------------------------------


async def test_connect_session_503_when_stripe_unconfigured(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    response = await admin_client.post("/payments/connect/session")
    assert response.status_code == 503
    assert response.json()["detail"] == "payments_not_configured"


async def test_connect_session_creates_account_and_returns_client_secret(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr("app.config.STRIPE_PUBLISHABLE_KEY", "pk_test_x")
    create_account = AsyncMock(return_value={"id": "acct_sess_1"})
    account_session = AsyncMock(
        return_value={"client_secret": "accs_secret_1", "expires_at": 1730000000}
    )
    monkeypatch.setattr("app.stripe_client.create_connected_account_v2", create_account)
    monkeypatch.setattr("app.stripe_client.create_account_session", account_session)

    response = await admin_client.post("/payments/connect/session")
    assert response.status_code == 200
    data = response.json()
    assert data["client_secret"] == "accs_secret_1"
    assert data["expires_at"] == 1730000000
    assert data["stripe_account_id"] == "acct_sess_1"
    assert data["publishable_key"] == "pk_test_x"

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    account = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id))
    assert account is not None
    assert account.stripe_account_id == "acct_sess_1"

    # A second call reuses the existing account and only mints a new session.
    response = await admin_client.post("/payments/connect/session")
    assert response.status_code == 200
    create_account.assert_awaited_once()
    assert account_session.await_count == 2


async def test_connect_session_503_payments_unavailable_when_stripe_rejects(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import stripe_client

    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_session = AsyncMock(
        side_effect=stripe_client.StripeV2Error(400, "unknown", "stripe blew up")
    )
    monkeypatch.setattr(
        "app.stripe_client.create_connected_account_v2",
        AsyncMock(return_value={"id": "acct_sess_2"}),
    )
    monkeypatch.setattr("app.stripe_client.create_account_session", create_session)

    response = await admin_client.post("/payments/connect/session")
    assert response.status_code == 503
    assert response.json()["detail"] == "payments_unavailable"


async def test_connect_prefills_known_business_fields(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Account creation pre-fills what onboarding already captured (#188)."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    create_account = AsyncMock(return_value={"id": "acct_prefill_1"})
    monkeypatch.setattr("app.stripe_client.create_connected_account_v2", create_account)
    monkeypatch.setattr(
        "app.stripe_client.create_account_link",
        AsyncMock(return_value="https://connect.stripe.com/setup/s/prefill"),
    )

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.structure = "sole_trader"
    tenant.settings = {"phone": "+447700900123", "postcode": "SK8 3NJ"}
    await db.commit()

    payload = {"return_url": "https://app.example/ok", "refresh_url": "https://app.example/re"}
    response = await admin_client.post("/payments/connect", json=payload)
    assert response.status_code == 200

    assert create_account.await_args is not None
    kwargs = create_account.await_args.kwargs
    assert kwargs["email"] == "admin@test.local"
    assert kwargs["display_name"] == "Test Electrical"
    assert kwargs["phone"] == "+447700900123"
    assert kwargs["postcode"] == "SK8 3NJ"
    assert kwargs["entity_type"] == "individual"


# ---------------------------------------------------------------------------
# GET /payments/status syncs mirrored flags from Stripe
# ---------------------------------------------------------------------------


async def test_status_syncs_flags_from_stripe(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    retrieve = AsyncMock(
        return_value={
            "id": "acct_sync_1",
            "details_submitted": True,
            "charges_enabled": True,
            "payouts_enabled": True,
        }
    )
    monkeypatch.setattr("app.stripe_client.retrieve_account", retrieve)

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    db.add(StripeAccount(tenant_id=tenant_id, stripe_account_id="acct_sync_1"))
    await db.commit()

    response = await admin_client.get("/payments/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["charges_enabled"] is True
    assert data["onboarding_complete"] is True

    account = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id))
    assert account is not None
    assert account.charges_enabled is True
    assert account.onboarding_complete is True


async def test_status_tolerates_stripe_sync_failure(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Stripe outage degrades to the mirrored flags instead of failing."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    retrieve = AsyncMock(side_effect=RuntimeError("stripe api down"))
    monkeypatch.setattr("app.stripe_client.retrieve_account", retrieve)

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    db.add(StripeAccount(tenant_id=tenant_id, stripe_account_id="acct_sync_2"))
    await db.commit()

    response = await admin_client.get("/payments/status")
    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["charges_enabled"] is False


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
    monkeypatch.setattr("app.routers.invoices.send_customer_email", send_email)

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
    # The send mints the intent; the view retrieves and reuses it.
    retrieve_intent = AsyncMock(
        return_value={
            "id": "pi_123",
            "client_secret": "pi_123_secret_abc",
            "status": "requires_payment_method",
            "amount": 60000,
        }
    )
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)
    monkeypatch.setattr("app.stripe_client.retrieve_payment_intent", retrieve_intent)

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


# ---------------------------------------------------------------------------
# Unconfigured Stripe: every remaining surface degrades cleanly (503, not 500)
# ---------------------------------------------------------------------------


async def test_onboarding_return_503_when_stripe_unconfigured(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    response = await admin_client.get("/payments/onboarding-return")
    assert response.status_code == 503
    assert response.json()["detail"] == "payments_not_configured"


# ---------------------------------------------------------------------------
# Onboarding return resilience
# ---------------------------------------------------------------------------


async def test_onboarding_return_tolerates_stripe_sync_failure(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If Stripe is unreachable when the tradie's browser returns, the page
    still renders (flags simply stay stale) instead of erroring."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    retrieve = AsyncMock(side_effect=RuntimeError("stripe api down"))
    monkeypatch.setattr("app.stripe_client.retrieve_account", retrieve)

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    db.add(StripeAccount(tenant_id=tenant_id, stripe_account_id="acct_sync_fail"))
    await db.commit()

    response = await admin_client.get("/payments/onboarding-return")
    assert response.status_code == 200
    assert "Almost there" in response.text

    account = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id))
    assert account is not None
    assert account.charges_enabled is False
    assert account.onboarding_complete is False


# ---------------------------------------------------------------------------
# GET /payments/invoice/{invoice_id}
# ---------------------------------------------------------------------------


async def test_list_invoice_payments(admin_client: AsyncClient, db: AsyncSession) -> None:
    tenant_id = _tenant_id(admin_client)
    invoice = await _create_invoice(admin_client, tenant_id)

    response = await admin_client.get(f"/payments/invoice/{invoice['id']}")
    assert response.status_code == 200
    assert response.json() == []

    await set_tenant_in_session(db, tenant_id)
    db.add(
        Payment(
            tenant_id=tenant_id,
            invoice_id=UUID(invoice["id"]),
            amount=Decimal("600.00"),
            currency_code="GBP",
            status="completed",
            provider="stripe",
            provider_transaction_id="pi_list_1",
            provider_payload={"id": "pi_list_1"},
            paid_at=datetime.utcnow(),
        )
    )
    await db.commit()
    # The first GET cached the invoice's empty payments collection in the
    # shared session's identity map; expire so the endpoint re-queries.
    db.expire_all()

    response = await admin_client.get(f"/payments/invoice/{invoice['id']}")
    assert response.status_code == 200
    payments = response.json()
    assert len(payments) == 1
    assert payments[0]["provider"] == "stripe"
    assert payments[0]["provider_transaction_id"] == "pi_list_1"
    assert payments[0]["amount"] == "600.00"

    # Payments are not leaked across invoices.
    other = await _create_invoice(admin_client, tenant_id)
    response = await admin_client.get(f"/payments/invoice/{other['id']}")
    assert response.status_code == 200
    assert response.json() == []
