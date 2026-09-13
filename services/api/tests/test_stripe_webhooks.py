"""Tests for the Stripe webhook endpoint (POST /webhooks/stripe).

No live Stripe: ``construct_event`` is mocked for payload-driven tests; the
signature tests exercise the real ``stripe.Webhook.construct_event`` via
monkeypatched config. The handlers run against the test database through
their own engine sessions (same pattern as the Paddle webhook), so fixtures
are seeded and cleaned up with committed sessions rather than the per-test
rollback client.
"""

import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.database import engine
from app.main import app
from app.models import (
    AiCallEvent,
    Contact,
    Invoice,
    Payment,
    ProcessedWebhook,
    Quote,
    StripeAccount,
    Tenant,
)
from app.rls import bypass_rls_in_session, set_tenant_in_session
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


def _event(event_id: str, event_type: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {"id": event_id, "type": event_type, "data": {"object": obj}}


async def _post_event(event: dict[str, Any]) -> Any:
    body = json.dumps(event).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=mocked", "Content-Type": "application/json"},
        )


async def _seed_invoice(*, paid: bool = False, intent_id: str = "pi_wh_1") -> dict[str, Any]:
    """Seed tenant → contact → AI-traced quote → invoice, committed for real."""
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        tenant = Tenant(slug=f"wh-{uuid4().hex[:8]}", name="Webhook Electrical")
        session.add(tenant)
        await session.flush()
        await set_tenant_in_session(session, tenant.id)
        contact = Contact(tenant_id=tenant.id, name="Webhook Homeowner", email="wh@example.com")
        session.add(contact)
        await session.flush()
        quote = Quote(
            tenant_id=tenant.id,
            contact_id=contact.id,
            title="Rewire",
            status="accepted",
            ai_metadata={"trace_id": f"trace-{uuid4().hex[:12]}"},
        )
        session.add(quote)
        await session.flush()
        invoice = Invoice(
            tenant_id=tenant.id,
            contact_id=contact.id,
            quote_id=quote.id,
            invoice_number=f"INV-{uuid4().hex[:6]}",
            status="paid" if paid else "sent",
            subtotal=Decimal("600.00"),
            total=Decimal("600.00"),
            paid_via="stripe" if paid else None,
            stripe_payment_intent_id=intent_id,
        )
        session.add(invoice)
        await session.flush()
        ids = {
            "tenant_id": tenant.id,
            "contact_id": contact.id,
            "quote_id": quote.id,
            "invoice_id": invoice.id,
        }
        await session.commit()
        return ids


async def _cleanup(ids: dict[str, Any], event_ids: list[str]) -> None:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        await session.execute(delete(AiCallEvent).where(AiCallEvent.quote_id == ids["quote_id"]))
        for event_id in event_ids:
            await session.execute(
                delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
            )
        await session.execute(delete(Tenant).where(Tenant.id == ids["tenant_id"]))
        await session.commit()


async def _outcome_count(invoice_quote_id: UUID) -> int:
    async with AsyncSession(engine) as session:
        result = await session.scalar(
            select(func.count())
            .select_from(AiCallEvent)
            .where(
                AiCallEvent.quote_id == invoice_quote_id,
                AiCallEvent.feature == "outcome",
            )
        )
        return int(result or 0)


async def _get_invoice(invoice_id: UUID) -> Invoice:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        invoice = await session.scalar(select(Invoice).where(Invoice.id == invoice_id))
        assert invoice is not None
        session.expunge(invoice)
        return invoice


# ---------------------------------------------------------------------------
# Signature / configuration handling (real stripe.Webhook.construct_event)
# ---------------------------------------------------------------------------


async def test_webhook_503_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    monkeypatch.setattr("app.config.STRIPE_WEBHOOK_SECRET", "")
    response = await _post_event(_event("evt_x", "payout.paid", {"id": "po_1"}))
    assert response.status_code == 503
    assert response.json()["detail"] == "payments_not_configured"


async def test_webhook_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr("app.config.STRIPE_WEBHOOK_SECRET", "whsec_test")
    body = b'{"id":"evt_bad","type":"payout.paid","data":{"object":{}}}'
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=forged", "Content-Type": "application/json"},
        )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# payment_intent.succeeded
# ---------------------------------------------------------------------------


async def test_payment_intent_succeeded_marks_invoice_paid_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed_invoice()
    event_id = f"evt_{uuid4().hex}"
    second_id = f"evt_{uuid4().hex}"
    event = _event(
        event_id,
        "payment_intent.succeeded",
        {
            "id": "pi_wh_1",
            "amount": 60000,
            "amount_received": 60000,
            "currency": "gbp",
            "metadata": {
                "invoice_id": str(ids["invoice_id"]),
                "tenant_id": str(ids["tenant_id"]),
            },
        },
    )
    monkeypatch.setattr("app.routers.stripe_webhooks.construct_event", lambda body, sig: event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        invoice = await _get_invoice(ids["invoice_id"])
        assert invoice.status == "paid"
        assert invoice.paid_via == "stripe"
        assert invoice.paid_at is not None

        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            payment = await session.scalar(
                select(Payment).where(Payment.invoice_id == ids["invoice_id"])
            )
            assert payment is not None
            assert payment.provider == "stripe"
            assert payment.amount == Decimal("600.00")
            assert payment.provider_transaction_id == "pi_wh_1"
        assert await _outcome_count(ids["quote_id"]) == 1

        # Replay of the same event id: deduped before the handler runs.
        response = await _post_event(event)
        assert response.json()["status"] == "duplicate"
        assert await _outcome_count(ids["quote_id"]) == 1

        # A distinct event id for the same intent: the handler's own
        # already-paid guard keeps side effects single-fire.
        second = dict(event, id=second_id)
        monkeypatch.setattr("app.routers.stripe_webhooks.construct_event", lambda body, sig: second)
        response = await _post_event(second)
        assert response.json()["status"] == "ok"
        assert await _outcome_count(ids["quote_id"]) == 1
        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            count = await session.scalar(
                select(func.count())
                .select_from(Payment)
                .where(Payment.invoice_id == ids["invoice_id"])
            )
            assert int(count or 0) == 1
    finally:
        await _cleanup(ids, [event_id, second_id])


# ---------------------------------------------------------------------------
# charge.refunded / charge.dispute.created / account.updated
# ---------------------------------------------------------------------------


async def test_charge_refunded_marks_invoice_refunded(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = await _seed_invoice(paid=True, intent_id="pi_wh_refund")
    event_id = f"evt_{uuid4().hex}"
    event = _event(
        event_id,
        "charge.refunded",
        {"id": "ch_1", "payment_intent": "pi_wh_refund"},
    )
    monkeypatch.setattr("app.routers.stripe_webhooks.construct_event", lambda body, sig: event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        invoice = await _get_invoice(ids["invoice_id"])
        assert invoice.status == "refunded"
    finally:
        await _cleanup(ids, [event_id])


async def test_dispute_created_sends_staff_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    send_alert = AsyncMock(return_value={})
    monkeypatch.setattr("app.routers.stripe_webhooks.send_alert", send_alert)
    event_id = f"evt_{uuid4().hex}"
    event = _event(
        event_id,
        "charge.dispute.created",
        {"id": "dp_1", "payment_intent": "pi_wh_1", "amount": 60000, "reason": "fraudulent"},
    )
    monkeypatch.setattr("app.routers.stripe_webhooks.construct_event", lambda body, sig: event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        send_alert.assert_awaited_once()
        assert send_alert.await_args is not None
        assert "dispute" in send_alert.await_args.args[0].lower()
    finally:
        async with AsyncSession(engine) as session:
            await session.execute(
                delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
            )
            await session.commit()


async def test_account_updated_syncs_stripe_account(monkeypatch: pytest.MonkeyPatch) -> None:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        tenant = Tenant(slug=f"wh-{uuid4().hex[:8]}", name="Account Electrical")
        session.add(tenant)
        await session.flush()
        await set_tenant_in_session(session, tenant.id)
        session.add(StripeAccount(tenant_id=tenant.id, stripe_account_id="acct_wh_1"))
        tenant_id = tenant.id
        await session.commit()

    event_id = f"evt_{uuid4().hex}"
    event = _event(
        event_id,
        "account.updated",
        {
            "id": "acct_wh_1",
            "details_submitted": True,
            "charges_enabled": True,
            "payouts_enabled": True,
        },
    )
    monkeypatch.setattr("app.routers.stripe_webhooks.construct_event", lambda body, sig: event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        async with AsyncSession(engine) as session:
            await set_tenant_in_session(session, tenant_id)
            account = await session.scalar(
                select(StripeAccount).where(StripeAccount.stripe_account_id == "acct_wh_1")
            )
            assert account is not None
            assert account.charges_enabled is True
            assert account.payouts_enabled is True
            assert account.onboarding_complete is True
    finally:
        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            await session.execute(
                delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
            )
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
