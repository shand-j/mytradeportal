"""End-to-end Stripe payment lifecycle test (ADR-003).

The full customer → tradie card-payment chain in one test, with every Stripe
call mocked:

1. Tenant connects a Stripe Express account (mocked account + onboarding
   link), then the ``account.updated`` webhook mirrors the capability flags.
2. The tenant opts in to card payments by default.
3. An invoice is created and sent; the public document endpoint issues a
   ``payment_url`` backed by a destination-charge PaymentIntent (mocked).
4. The recorded-shape ``payment_intent.succeeded`` webhook settles it:
   invoice paid via stripe, one Payment row, one outcome event, one staff
   notification.
5. The refund endpoint refunds it: status refunded, audit log written.

The webhook handlers open their own engine sessions, so the per-test rollback
client cannot be used: this test drives the API over a single shared
connection with REAL commits (tenant GUCs persist on the connection for the
whole test, mirroring production's pool + checkout-listener behaviour), and
cleans the tenant up at the end.
"""

import json
import re
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from app.database import engine, get_db
from app.main import app
from app.models import (
    AiCallEvent,
    AuditLog,
    Invoice,
    Notification,
    Payment,
    ProcessedWebhook,
    Quote,
    StripeAccount,
    Tenant,
    User,
)
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.security import get_password_hash
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.test_stripe_webhooks import account_updated_event, payment_intent_succeeded_event

pytestmark = pytest.mark.asyncio

_TOKEN_RE = re.compile(r"https://www\.mytradeportal\.co\.uk/invoice/([A-Za-z0-9_-]+)")
_PASSWORD = "lifecycle-password-123"


@pytest_asyncio.fixture(loop_scope="function")
async def http(test_database_url: str) -> AsyncIterator[AsyncClient]:
    """HTTP client over one shared connection with real commits.

    Like the conftest ``client`` fixture but without the rollback wrapper:
    commits are durable, so the webhook handlers (which open their own engine
    sessions) see everything the API requests wrote. The tenant GUC set with
    ``is_local=false`` survives commits on the single connection, so
    post-commit reads inside endpoints keep passing RLS.
    """
    shared_engine = create_async_engine(test_database_url, echo=False, poolclass=NullPool)
    async with shared_engine.connect() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)

        async def override_get_db() -> AsyncIterator[AsyncSession]:
            # Mimic a fresh per-request session: drop the identity map so
            # rows written by other sessions (webhook handlers) are seen.
            session.expire_all()
            yield session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
        app.dependency_overrides.clear()
        await session.close()
    await shared_engine.dispose()


async def _post_webhook(event: dict[str, Any]) -> Any:
    body = json.dumps(event).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=mocked", "Content-Type": "application/json"},
        )


def _patch_construct(monkeypatch: pytest.MonkeyPatch, event: dict[str, Any]) -> None:
    monkeypatch.setattr("app.routers.stripe_webhooks.construct_event", lambda body, sig: event)


async def test_full_stripe_payment_lifecycle(
    monkeypatch: pytest.MonkeyPatch, http: AsyncClient
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr("app.config.STRIPE_WEBHOOK_SECRET", "whsec_x")
    create_account = AsyncMock(return_value={"id": "acct_lc_1"})
    account_link = AsyncMock(return_value="https://connect.stripe.com/setup/s/lc")
    create_intent = AsyncMock(return_value={"id": "pi_lc_1", "client_secret": "pi_lc_1_secret"})
    create_refund = AsyncMock(return_value={"id": "re_lc_1", "status": "succeeded"})
    send_email = AsyncMock(return_value=True)
    monkeypatch.setattr("app.stripe_client.create_express_account", create_account)
    monkeypatch.setattr("app.stripe_client.create_account_link", account_link)
    monkeypatch.setattr("app.stripe_client.create_payment_intent", create_intent)
    monkeypatch.setattr("app.stripe_client.create_refund", create_refund)
    monkeypatch.setattr("app.routers.invoices.send_email", send_email)

    account_event_id = f"evt_{uuid4().hex}"
    succeeded_event_id = f"evt_{uuid4().hex}"

    # Seed tenant + admin user with a real commit so both the HTTP client
    # and the webhook handlers' own sessions can see them.
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        tenant = Tenant(slug=f"lc-{uuid4().hex[:8]}", name="Lifecycle Electrical")
        session.add(tenant)
        await session.flush()
        await set_tenant_in_session(session, tenant.id)
        user = User(
            tenant_id=tenant.id,
            email="owner@lifecycle.test",
            full_name="Lifecycle Owner",
            role="admin",
            password_hash=get_password_hash(_PASSWORD),
            is_active=True,
        )
        session.add(user)
        await session.flush()
        tenant_id = tenant.id
        tenant_slug = tenant.slug
        await session.commit()

    quote_id: UUID | None = None
    try:
        login = await http.post(
            "/auth/login",
            headers={"host": f"{tenant_slug}.localhost"},
            json={"email": "owner@lifecycle.test", "password": _PASSWORD},
        )
        assert login.status_code == 200
        http.headers["X-Tenant-ID"] = str(tenant_id)

        # 1. Connect: creates the Express account + onboarding link.
        connect = await http.post(
            "/payments/connect",
            json={
                "return_url": "https://app.example/ok",
                "refresh_url": "https://app.example/re",
            },
        )
        assert connect.status_code == 200
        assert connect.json()["onboarding_url"] == "https://connect.stripe.com/setup/s/lc"
        create_account.assert_awaited_once()

        # The account.updated webhook completes onboarding.
        account_event = account_updated_event(account_event_id, account_id="acct_lc_1")
        _patch_construct(monkeypatch, account_event)
        assert (await _post_webhook(account_event)).status_code == 200
        async with AsyncSession(engine) as session:
            await set_tenant_in_session(session, tenant_id)
            account = await session.scalar(
                select(StripeAccount).where(StripeAccount.tenant_id == tenant_id)
            )
            assert account is not None
            assert account.onboarding_complete is True

        # 2. Tenant opts in to card payments by default.
        settings = await http.patch("/payments/settings", json={"accept_card_default": True})
        assert settings.status_code == 200
        assert settings.json()["accept_card_default"] is True
        assert settings.json()["onboarding_complete"] is True

        # 3. Invoice created (linked to an AI-traced quote so the funnel
        # outcome event fires) and sent to the customer.
        contact = await http.post(
            "/contacts",
            json={"name": "Lifecycle Homeowner", "email": "lifecycle.homeowner@example.com"},
        )
        assert contact.status_code == 201
        invoice_resp = await http.post(
            "/invoices",
            json={
                "contact_id": contact.json()["id"],
                "invoice_number": f"INV-{uuid4().hex[:6]}",
                "line_items": [
                    {
                        "description": "Fuse board works",
                        "quantity": "1",
                        "unit_price": "600.00",
                    }
                ],
            },
        )
        assert invoice_resp.status_code == 201
        invoice = invoice_resp.json()
        invoice_id = UUID(invoice["id"])

        async with AsyncSession(engine) as session:
            await set_tenant_in_session(session, tenant_id)
            quote = Quote(
                tenant_id=tenant_id,
                contact_id=UUID(contact.json()["id"]),
                title="Rewire",
                status="accepted",
                ai_metadata={"trace_id": f"trace-{uuid4().hex[:12]}"},
            )
            session.add(quote)
            await session.flush()
            invoice_row = await session.get(Invoice, invoice_id)
            assert invoice_row is not None
            invoice_row.quote_id = quote.id
            quote_id = quote.id
            await session.commit()

        sent = await http.post(f"/invoices/{invoice['id']}/send")
        assert sent.status_code == 200
        assert sent.json()["status"] == "sent"
        send_email.assert_awaited_once()
        assert send_email.await_args is not None
        match = _TOKEN_RE.search(send_email.await_args.kwargs["html_body"])
        assert match is not None
        raw_token = match.group(1)

        # 4. Public document issues the payment_url (PaymentIntent created).
        public = await http.get(f"/public/invoice/{raw_token}")
        assert public.status_code == 200
        assert public.json()["payment_url"] == (
            f"https://www.mytradeportal.co.uk/pay/{raw_token}?pi=pi_lc_1&cs=pi_lc_1_secret"
        )
        assert create_intent.await_args is not None
        intent_kwargs = create_intent.await_args.kwargs
        assert intent_kwargs["amount_pence"] == 60000
        assert intent_kwargs["connected_account_id"] == "acct_lc_1"
        assert intent_kwargs["invoice_id"] == str(invoice_id)
        assert intent_kwargs["tenant_id"] == str(tenant_id)
        async with AsyncSession(engine) as session:
            await set_tenant_in_session(session, tenant_id)
            invoice_row = await session.get(Invoice, invoice_id)
            assert invoice_row is not None
            assert invoice_row.stripe_payment_intent_id == "pi_lc_1"

        # 5. The succeeded webhook settles the invoice.
        succeeded_event = payment_intent_succeeded_event(
            succeeded_event_id,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            intent_id="pi_lc_1",
            charge_id="ch_lc_1",
            destination_account="acct_lc_1",
        )
        _patch_construct(monkeypatch, succeeded_event)
        assert (await _post_webhook(succeeded_event)).status_code == 200

        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            invoice_row = await session.get(Invoice, invoice_id)
            assert invoice_row is not None
            assert invoice_row.status == "paid"
            assert invoice_row.paid_via == "stripe"
            assert invoice_row.paid_at is not None

            payment = await session.scalar(select(Payment).where(Payment.invoice_id == invoice_id))
            assert payment is not None
            assert payment.provider == "stripe"
            assert payment.amount == Decimal("600.00")
            assert payment.provider_transaction_id == "pi_lc_1"

            outcomes = await session.scalar(
                select(func.count())
                .select_from(AiCallEvent)
                .where(AiCallEvent.quote_id == quote_id, AiCallEvent.feature == "outcome")
            )
            assert int(outcomes or 0) == 1

            notifications = await session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.tenant_id == tenant_id, Notification.type == "invoice_paid")
            )
            assert int(notifications or 0) == 1

        # The staff payments list reflects the settlement.
        listed = await http.get(f"/payments/invoice/{invoice['id']}")
        assert listed.status_code == 200
        assert [p["provider_transaction_id"] for p in listed.json()] == ["pi_lc_1"]

        # 6. Refund endpoint: status refunded, Stripe refund issued,
        # audit log written.
        refund = await http.post(f"/invoices/{invoice['id']}/refund")
        assert refund.status_code == 200
        assert refund.json()["status"] == "refunded"
        create_refund.assert_awaited_once_with("pi_lc_1")

        async with AsyncSession(engine) as session:
            await set_tenant_in_session(session, tenant_id)
            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.action == "invoice.refunded",
                    AuditLog.entity_id == invoice_id,
                )
            )
            assert audit is not None
            assert audit.payload["stripe_refund_id"] == "re_lc_1"
    finally:
        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            if quote_id is not None:
                await session.execute(delete(AiCallEvent).where(AiCallEvent.quote_id == quote_id))
            for event_id in (account_event_id, succeeded_event_id):
                await session.execute(
                    delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
                )
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
