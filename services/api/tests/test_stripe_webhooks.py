"""Tests for the Stripe webhook endpoint (POST /webhooks/stripe).

No live Stripe: ``construct_event`` is mocked for payload-driven tests; the
signature tests exercise the real ``stripe.Webhook.construct_event`` via
monkeypatched config. The handlers run against the test database through
their own engine sessions (same pattern as the Paddle webhook), so fixtures
are seeded and cleaned up with committed sessions rather than the per-test
rollback client.

Event payloads are built by the ``*_event`` builders below, which reproduce
the shapes Stripe actually sends (API version 2025-08-27.basil): full event
envelopes (``api_version``/``livemode``/``request``/``pending_webhooks``) and
full ``data.object`` payloads (``latest_charge`` on the PaymentIntent, the
``refunds`` list on a refunded charge, capability blocks on the account).
Handlers must parse these recorded shapes, not hand-waved minimal dicts.
"""

import hashlib
import hmac
import json
import time
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
    Notification,
    Payment,
    ProcessedWebhook,
    Quote,
    StripeAccount,
    Tenant,
)
from app.rls import bypass_rls_in_session, clear_rls_session, set_tenant_in_session
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_EVENT_CREATED = 1757800000


# ---------------------------------------------------------------------------
# Recorded Stripe event fixtures (shaped exactly like Stripe sends them)
# ---------------------------------------------------------------------------


def _envelope(event_id: str, event_type: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event_id,
        "object": "event",
        "api_version": "2025-08-27.basil",
        "created": _EVENT_CREATED,
        "livemode": False,
        "type": event_type,
        "pending_webhooks": 1,
        "request": {"id": f"req_{event_id[-12:]}", "idempotency_key": None},
        "data": {"object": obj},
    }


def payment_intent_succeeded_event(
    event_id: str,
    *,
    invoice_id: UUID,
    tenant_id: UUID,
    intent_id: str = "pi_wh_1",
    charge_id: str = "ch_wh_1",
    amount_pence: int = 60000,
    destination_account: str = "acct_conn_1",
) -> dict[str, Any]:
    """Full ``payment_intent.succeeded`` for a destination charge."""
    return _envelope(
        event_id,
        "payment_intent.succeeded",
        {
            "id": intent_id,
            "object": "payment_intent",
            "amount": amount_pence,
            "amount_capturable": 0,
            "amount_received": amount_pence,
            "application_fee_amount": None,
            "automatic_payment_methods": {"enabled": True},
            "capture_method": "automatic",
            "confirmation_method": "automatic",
            "currency": "gbp",
            "customer": None,
            "latest_charge": charge_id,
            "livemode": False,
            "payment_method": "pm_card_visa",
            "payment_method_types": ["card"],
            "status": "succeeded",
            "transfer_data": {"destination": destination_account},
            "metadata": {"invoice_id": str(invoice_id), "tenant_id": str(tenant_id)},
        },
    )


def charge_refunded_event(
    event_id: str,
    *,
    intent_id: str,
    charge_id: str = "ch_wh_1",
    amount_pence: int = 60000,
) -> dict[str, Any]:
    """Full ``charge.refunded`` with the nested refunds list."""
    return _envelope(
        event_id,
        "charge.refunded",
        {
            "id": charge_id,
            "object": "charge",
            "amount": amount_pence,
            "amount_captured": amount_pence,
            "amount_refunded": amount_pence,
            "currency": "gbp",
            "livemode": False,
            "paid": True,
            "refunded": True,
            "status": "succeeded",
            "payment_intent": intent_id,
            "payment_method_details": {
                "type": "card",
                "card": {"brand": "visa", "last4": "4242", "exp_month": 4, "exp_year": 2030},
            },
            "refunds": {
                "object": "list",
                "has_more": False,
                "data": [
                    {
                        "id": "re_wh_1",
                        "object": "refund",
                        "amount": amount_pence,
                        "currency": "gbp",
                        "status": "succeeded",
                        "payment_intent": intent_id,
                    }
                ],
            },
        },
    )


def dispute_created_event(
    event_id: str,
    *,
    intent_id: str,
    charge_id: str = "ch_wh_1",
    amount_pence: int = 60000,
    reason: str = "fraudulent",
) -> dict[str, Any]:
    """Full ``charge.dispute.created`` payload."""
    return _envelope(
        event_id,
        "charge.dispute.created",
        {
            "id": f"dp_{event_id[-12:]}",
            "object": "dispute",
            "amount": amount_pence,
            "charge": charge_id,
            "payment_intent": intent_id,
            "currency": "gbp",
            "livemode": False,
            "reason": reason,
            "status": "warning_needs_response",
            "evidence_details": {
                "due_by": _EVENT_CREATED + 604800,
                "has_evidence": False,
                "submission_count": 0,
            },
        },
    )


def account_updated_event(
    event_id: str,
    *,
    account_id: str,
    details_submitted: bool = True,
    charges_enabled: bool = True,
    payouts_enabled: bool = True,
) -> dict[str, Any]:
    """Full ``account.updated`` for a Connect Express account."""
    capability = "active" if charges_enabled else "pending"
    return _envelope(
        event_id,
        "account.updated",
        {
            "id": account_id,
            "object": "account",
            "country": "GB",
            "type": "express",
            "details_submitted": details_submitted,
            "charges_enabled": charges_enabled,
            "payouts_enabled": payouts_enabled,
            "capabilities": {"card_payments": capability, "transfers": capability},
            "requirements": {
                "currently_due": [],
                "eventually_due": [],
                "past_due": [],
                "disabled_reason": None,
            },
            "business_profile": {"mcc": "1731", "product_description": "Electrical services"},
        },
    )


def payout_paid_event(
    event_id: str,
    *,
    payout_id: str = "po_wh_1",
    amount_pence: int = 60000,
) -> dict[str, Any]:
    """Full ``payout.paid`` payload (informational — nothing to mirror)."""
    return _envelope(
        event_id,
        "payout.paid",
        {
            "id": payout_id,
            "object": "payout",
            "amount": amount_pence,
            "currency": "gbp",
            "arrival_date": _EVENT_CREATED,
            "automatic": True,
            "destination": "ba_wh_1",
            "livemode": False,
            "method": "standard",
            "status": "paid",
        },
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _post_event(event: dict[str, Any]) -> Any:
    body = json.dumps(event).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=mocked", "Content-Type": "application/json"},
        )


def _patch_construct(monkeypatch: pytest.MonkeyPatch, event: dict[str, Any]) -> None:
    monkeypatch.setattr("app.routers.stripe_webhooks.construct_event", lambda body, sig: event)


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


async def _staff_notification_count(tenant_id: UUID, kind: str) -> int:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        result = await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.tenant_id == tenant_id, Notification.type == kind)
        )
        return int(result or 0)


async def _payment_count(invoice_id: UUID) -> int:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        result = await session.scalar(
            select(func.count()).select_from(Payment).where(Payment.invoice_id == invoice_id)
        )
        return int(result or 0)


async def _dedupe_row_exists(event_id: str) -> bool:
    async with AsyncSession(engine) as session:
        row = await session.scalar(
            select(ProcessedWebhook).where(
                ProcessedWebhook.provider == "stripe",
                ProcessedWebhook.event_id == event_id,
            )
        )
        return row is not None


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
    response = await _post_event(payout_paid_event("evt_unconfigured", payout_id="po_1"))
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


def _stripe_signature_header(body: bytes, secret: str) -> str:
    """Build a genuine Stripe-Signature header (t=...,v1=...) exactly the way
    Stripe computes it: HMAC-SHA256 of ``"<timestamp>.<raw body>"``."""
    timestamp = str(int(time.time()))
    signed = f"{timestamp}.".encode() + body
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


async def test_construct_event_verifies_real_signature_and_returns_plain_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path with a REAL signature: stripe-python 15.x no longer
    subclasses dict, so ``construct_event`` must convert via ``to_dict()``.

    Sync body: declared async only because the module-level ``pytestmark``
    applies ``pytest.mark.asyncio`` to every test in this file."""
    from app.stripe_client import construct_event

    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr("app.config.STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    payload = {
        "id": "evt_real_sig",
        "object": "event",
        "type": "payout.paid",
        "livemode": False,
        "data": {"object": {"id": "po_1", "object": "payout", "status": "paid"}},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()

    event = construct_event(body, _stripe_signature_header(body, "whsec_test_123"))

    assert type(event) is dict
    assert event["id"] == "evt_real_sig"
    assert type(event["data"]["object"]) is dict
    assert event["data"]["object"]["id"] == "po_1"


async def test_construct_event_rejects_forged_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.stripe_client import construct_event

    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr("app.config.STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    body = b'{"id":"evt_forged","type":"payout.paid","data":{"object":{}}}'

    with pytest.raises(ValueError, match="invalid stripe webhook signature"):
        construct_event(body, _stripe_signature_header(body, "whsec_WRONG"))


# ---------------------------------------------------------------------------
# payment_intent.succeeded
# ---------------------------------------------------------------------------


async def test_payment_intent_succeeded_marks_invoice_paid_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed_invoice()
    event_id = f"evt_{uuid4().hex}"
    second_id = f"evt_{uuid4().hex}"
    event = payment_intent_succeeded_event(
        event_id, invoice_id=ids["invoice_id"], tenant_id=ids["tenant_id"]
    )
    _patch_construct(monkeypatch, event)
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
            assert payment.currency_code == "GBP"
            assert payment.provider_transaction_id == "pi_wh_1"
            # The recorded full-shape payload is persisted verbatim.
            assert payment.provider_payload["latest_charge"] == "ch_wh_1"
            assert payment.provider_payload["transfer_data"]["destination"] == "acct_conn_1"
        assert await _outcome_count(ids["quote_id"]) == 1
        assert await _staff_notification_count(ids["tenant_id"], "invoice_paid") == 1
        assert await _dedupe_row_exists(event_id)

        # Replay of the same event id: deduped before the handler runs.
        response = await _post_event(event)
        assert response.json()["status"] == "duplicate"
        assert await _outcome_count(ids["quote_id"]) == 1

        # A distinct event id for the same intent: the handler's own
        # already-paid guard keeps side effects single-fire.
        second = dict(event, id=second_id)
        _patch_construct(monkeypatch, second)
        response = await _post_event(second)
        assert response.json()["status"] == "ok"
        assert await _outcome_count(ids["quote_id"]) == 1
        assert await _payment_count(ids["invoice_id"]) == 1
        assert await _staff_notification_count(ids["tenant_id"], "invoice_paid") == 1
    finally:
        await _cleanup(ids, [event_id, second_id])


async def test_payment_intent_succeeded_bypasses_rls_without_tenant_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: webhook requests carry no tenant GUC; FORCE RLS would hide
    every row, so the handler must bypass RLS (transaction-local) to find the
    invoice at all."""
    ids = await _seed_invoice()
    # Prove the setup: with neither a tenant GUC nor a bypass, RLS hides the
    # invoice even though it exists.
    async with AsyncSession(engine) as session:
        await clear_rls_session(session)
        hidden = await session.scalar(select(Invoice).where(Invoice.id == ids["invoice_id"]))
        assert hidden is None

    event_id = f"evt_{uuid4().hex}"
    event = payment_intent_succeeded_event(
        event_id, invoice_id=ids["invoice_id"], tenant_id=ids["tenant_id"]
    )
    _patch_construct(monkeypatch, event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        invoice = await _get_invoice(ids["invoice_id"])
        assert invoice.status == "paid"
        assert await _payment_count(ids["invoice_id"]) == 1
    finally:
        await _cleanup(ids, [event_id])


async def test_out_of_order_refund_then_succeeded_keeps_invoice_refunded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stripe delivers at-least-once with no ordering guarantee. If the
    ``charge.refunded`` event lands before ``payment_intent.succeeded``, the
    refund must win: the late succeeded event must not resurrect the invoice
    to paid or re-fire side effects."""
    ids = await _seed_invoice(paid=False, intent_id="pi_wh_ooo")
    refund_id = f"evt_{uuid4().hex}"
    succeeded_id = f"evt_{uuid4().hex}"
    refund_event = charge_refunded_event(refund_id, intent_id="pi_wh_ooo")
    succeeded_event = payment_intent_succeeded_event(
        succeeded_id,
        invoice_id=ids["invoice_id"],
        tenant_id=ids["tenant_id"],
        intent_id="pi_wh_ooo",
    )
    try:
        _patch_construct(monkeypatch, refund_event)
        response = await _post_event(refund_event)
        assert response.status_code == 200
        invoice = await _get_invoice(ids["invoice_id"])
        assert invoice.status == "refunded"

        _patch_construct(monkeypatch, succeeded_event)
        response = await _post_event(succeeded_event)
        assert response.status_code == 200

        invoice = await _get_invoice(ids["invoice_id"])
        assert invoice.status == "refunded"
        assert invoice.paid_at is None
        assert await _payment_count(ids["invoice_id"]) == 0
        assert await _staff_notification_count(ids["tenant_id"], "invoice_paid") == 0
        assert await _outcome_count(ids["quote_id"]) == 0
    finally:
        await _cleanup(ids, [refund_id, succeeded_id])


async def test_payment_intent_succeeded_without_metadata_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Foreign PaymentIntents (not created by us) carry no linkage metadata;
    the handler must ack them without side effects."""
    event_id = f"evt_{uuid4().hex}"
    event = _envelope(
        event_id,
        "payment_intent.succeeded",
        {
            "id": "pi_foreign_1",
            "object": "payment_intent",
            "amount": 1000,
            "amount_received": 1000,
            "currency": "gbp",
            "status": "succeeded",
            "latest_charge": "ch_foreign_1",
            "metadata": {},
        },
    )
    _patch_construct(monkeypatch, event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert await _dedupe_row_exists(event_id)
    finally:
        async with AsyncSession(engine) as session:
            await session.execute(
                delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
            )
            await session.commit()


async def test_payment_intent_succeeded_orphan_invoice_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata pointing at a deleted/unknown invoice must ack, not 500 —
    otherwise Stripe retries forever."""
    event_id = f"evt_{uuid4().hex}"
    event = payment_intent_succeeded_event(
        event_id, invoice_id=uuid4(), tenant_id=uuid4(), intent_id="pi_orphan_1"
    )
    _patch_construct(monkeypatch, event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        async with AsyncSession(engine) as session:
            await session.execute(
                delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
            )
            await session.commit()


# ---------------------------------------------------------------------------
# charge.refunded / charge.dispute.created / account.updated / payout.paid
# ---------------------------------------------------------------------------


async def test_charge_refunded_marks_invoice_refunded(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = await _seed_invoice(paid=True, intent_id="pi_wh_refund")
    event_id = f"evt_{uuid4().hex}"
    event = charge_refunded_event(event_id, intent_id="pi_wh_refund")
    _patch_construct(monkeypatch, event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        invoice = await _get_invoice(ids["invoice_id"])
        assert invoice.status == "refunded"
    finally:
        await _cleanup(ids, [event_id])


async def test_charge_refunded_replay_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same refund delivered twice (same id, then a distinct retry id):
    the invoice stays refunded and neither delivery 500s."""
    ids = await _seed_invoice(paid=True, intent_id="pi_wh_refund_replay")
    event_id = f"evt_{uuid4().hex}"
    retry_id = f"evt_{uuid4().hex}"
    event = charge_refunded_event(event_id, intent_id="pi_wh_refund_replay")
    try:
        _patch_construct(monkeypatch, event)
        assert (await _post_event(event)).status_code == 200
        assert (await _get_invoice(ids["invoice_id"])).status == "refunded"

        # Exact replay: deduped.
        response = await _post_event(event)
        assert response.json()["status"] == "duplicate"

        # Distinct retry id for the same refund: handler no-ops on status.
        retry = dict(event, id=retry_id)
        _patch_construct(monkeypatch, retry)
        response = await _post_event(retry)
        assert response.status_code == 200
        assert (await _get_invoice(ids["invoice_id"])).status == "refunded"
    finally:
        await _cleanup(ids, [event_id, retry_id])


async def test_dispute_created_sends_staff_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    send_alert = AsyncMock(return_value={})
    monkeypatch.setattr("app.routers.stripe_webhooks.send_alert", send_alert)
    event_id = f"evt_{uuid4().hex}"
    event = dispute_created_event(event_id, intent_id="pi_wh_1", reason="fraudulent")
    _patch_construct(monkeypatch, event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        send_alert.assert_awaited_once()
        assert send_alert.await_args is not None
        assert "dispute" in send_alert.await_args.args[0].lower()
        # Alert body renders the recorded amount and reason.
        body = send_alert.await_args.args[1]
        assert "£600.00" in body
        assert "fraudulent" in body
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
    event = account_updated_event(event_id, account_id="acct_wh_1")
    _patch_construct(monkeypatch, event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        async with AsyncSession(engine) as session:
            await set_tenant_in_session(session, tenant_id)
            account = await session.scalar(
                select(StripeAccount).where(StripeAccount.stripe_account_id == "acct_wh_1")
            )
            assert account is not None
            assert account.details_submitted is True
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


async def test_payout_paid_is_acknowledged_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """payout.paid is informational: acked, deduped, and touches nothing."""
    event_id = f"evt_{uuid4().hex}"
    event = payout_paid_event(event_id, payout_id="po_info_1")
    _patch_construct(monkeypatch, event)
    try:
        response = await _post_event(event)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert await _dedupe_row_exists(event_id)

        # Replay dedupes too.
        response = await _post_event(event)
        assert response.json()["status"] == "duplicate"
    finally:
        async with AsyncSession(engine) as session:
            await session.execute(
                delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
            )
            await session.commit()
