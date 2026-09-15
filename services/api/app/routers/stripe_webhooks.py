"""Stripe webhook endpoint (customer → tradie card payments, ADR-003).

Separate from the Paddle webhook router (``app.routers.webhooks``) — Stripe
settles tradie receivables, Paddle only ever bills OUR subscription.

Stripe delivers at-least-once with per-attempt signatures. The handler
verifies ``Stripe-Signature``, dedupes on the event id via the shared
``processed_webhooks`` ledger (``provider="stripe"``), and routes to
type-specific handlers. Non-2xx responses are retried by Stripe, so a bad
signature returns 400 and an unconfigured secret returns 503 (loud, and the
event replays once the secret is set).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_telemetry import record_quote_outcome
from app.alerting import send_alert
from app.database import engine
from app.payment_notifications import send_payment_received_email
from app.models import Contact, Invoice, Payment, ProcessedWebhook, Quote, StripeAccount, Tenant
from app.push import notify_staff
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.stripe_client import PaymentsNotConfiguredError, construct_event

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = structlog.get_logger("api.stripe_webhooks")


async def _mark_event_seen(event_id: str, event_type: str) -> bool:
    """Insert into the dedup ledger. Returns False if already seen."""
    async with AsyncSession(engine) as session:
        session.add(ProcessedWebhook(provider="stripe", event_id=event_id, event_type=event_type))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
    return True


async def _handle_payment_intent_succeeded(event_data: dict[str, Any]) -> None:
    """Mark the linked invoice paid (idempotently) and notify the tradie."""
    metadata = event_data.get("metadata") or {}
    invoice_id = metadata.get("invoice_id")
    tenant_id_raw = metadata.get("tenant_id")
    if not invoice_id:
        logger.warning("stripe_intent_without_invoice", intent_id=event_data.get("id"))
        return
    try:
        invoice_uuid = UUID(str(invoice_id))
    except ValueError:
        logger.warning("stripe_intent_bad_invoice_id", invoice_id=invoice_id)
        return

    async with AsyncSession(engine) as session:
        # Webhook requests carry no tenant context; the metadata tenant scopes
        # the session once known, but the initial lookup must bypass RLS
        # (trusted server-side context, transaction-local) or FORCE RLS hides
        # every row.
        await bypass_rls_for_transaction(session)
        if tenant_id_raw:
            try:
                await set_tenant_in_session(session, UUID(str(tenant_id_raw)))
            except ValueError:
                logger.warning("stripe_intent_bad_tenant", tenant_id=tenant_id_raw)
        invoice = await session.scalar(select(Invoice).where(Invoice.id == invoice_uuid))
        if invoice is None:
            logger.warning("stripe_intent_orphan", invoice_id=invoice_id)
            return

        if invoice.status == "paid":
            # Replay (or a staff mark-paid raced us): nothing to re-apply.
            logger.info("stripe_invoice_already_paid", invoice_id=str(invoice.id))
            return
        if invoice.status == "refunded":
            # Out-of-order delivery: the refund already won; a late succeeded
            # event must never resurrect the invoice to paid.
            logger.info("stripe_invoice_already_refunded", invoice_id=str(invoice.id))
            return

        intent_id = str(event_data.get("id") or "")
        amount_pence = event_data.get("amount_received") or event_data.get("amount") or 0
        invoice.status = "paid"
        invoice.paid_at = datetime.utcnow()
        invoice.paid_via = "stripe"
        invoice.stripe_payment_intent_id = invoice.stripe_payment_intent_id or intent_id
        session.add(invoice)
        session.add(
            Payment(
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.id,
                amount=Decimal(int(amount_pence)) / 100,
                currency_code=str(event_data.get("currency") or "gbp").upper(),
                status="completed",
                provider="stripe",
                provider_transaction_id=intent_id,
                provider_payload=event_data,
                paid_at=datetime.utcnow(),
            )
        )
        await notify_staff(
            session,
            invoice.tenant_id,
            kind="invoice_paid",
            title="Invoice paid",
            body=(
                f"Invoice {invoice.invoice_number} for £{invoice.total} "
                "has been paid online by card."
            ),
            link=f"/invoices/{invoice.id}",
        )
        # Close the AI funnel when the paid invoice traces back to an
        # AI-drafted quote (no-op for manual quotes — they carry no trace id).
        if invoice.quote_id is not None:
            source_quote = await session.get(Quote, invoice.quote_id)
            if source_quote is not None:
                await record_quote_outcome(
                    session,
                    outcome="invoice_paid",
                    tenant_id=invoice.tenant_id,
                    quote=source_quote,
                    extra_payload={
                        "invoice_id": str(invoice.id),
                        "actor": "stripe_webhook",
                        "provider_transaction_id": intent_id,
                    },
                )
        # Snapshot before commit: commit() expires the ORM object and lazy
        # refresh outside a greenlet raises MissingGreenlet.
        log_invoice_id = str(invoice.id)
        # Confirm the payment to the customer (thank-you + review prompt).
        # Best-effort: runs pre-commit while the session's RLS context is
        # live, and never raises — the webhook 200 must not depend on it.
        await send_payment_received_email(session, invoice, card_payment=True)
        await session.commit()
        logger.info("stripe_invoice_paid", invoice_id=log_invoice_id)


async def _handle_charge_refunded(event_data: dict[str, Any]) -> None:
    """Mark the invoice refunded when Stripe confirms the refund."""
    intent_id = event_data.get("payment_intent")
    if not intent_id:
        return
    async with AsyncSession(engine) as session:
        # No tenant context on webhook requests: bypass RLS (transaction-local)
        # to locate the invoice by its payment intent, then scope the session.
        await bypass_rls_for_transaction(session)
        invoice = await session.scalar(
            select(Invoice).where(Invoice.stripe_payment_intent_id == str(intent_id))
        )
        if invoice is None:
            logger.warning("stripe_refund_orphan", payment_intent_id=intent_id)
            return
        await set_tenant_in_session(session, invoice.tenant_id)
        if invoice.status == "refunded":
            return
        invoice.status = "refunded"
        session.add(invoice)
        # Snapshot before commit: commit() expires the ORM object and lazy
        # refresh outside a greenlet raises MissingGreenlet.
        log_invoice_id = str(invoice.id)
        await session.commit()
        logger.info("stripe_invoice_refunded", invoice_id=log_invoice_id)


async def _handle_dispute_created(event_data: dict[str, Any]) -> None:
    """Page ops: a cardholder disputed a tradie payment."""
    intent_id = event_data.get("payment_intent") or "unknown"
    amount = event_data.get("amount") or 0
    reason = event_data.get("reason") or "unspecified"
    await send_alert(
        "Stripe dispute opened",
        (
            f"Dispute on payment {intent_id}: £{int(amount) / 100:.2f} "
            f"(reason: {reason}). Review in the Stripe dashboard."
        ),
    )
    logger.warning("stripe_dispute_created", payment_intent_id=intent_id, reason=reason)


async def _handle_account_updated(event_data: dict[str, Any]) -> None:
    """Mirror Stripe's capability flags onto our StripeAccount row."""
    account_id = event_data.get("id")
    if not account_id:
        return
    async with AsyncSession(engine) as session:
        # No tenant context on webhook requests: bypass RLS (transaction-local)
        # to locate the connected account, then scope the session.
        await bypass_rls_for_transaction(session)
        account = await session.scalar(
            select(StripeAccount).where(StripeAccount.stripe_account_id == str(account_id))
        )
        if account is None:
            logger.warning("stripe_account_orphan", stripe_account_id=account_id)
            return
        await set_tenant_in_session(session, account.tenant_id)
        account.details_submitted = bool(event_data.get("details_submitted", False))
        account.charges_enabled = bool(event_data.get("charges_enabled", False))
        account.payouts_enabled = bool(event_data.get("payouts_enabled", False))
        account.onboarding_complete = account.charges_enabled and account.payouts_enabled
        session.add(account)
        await session.commit()


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
) -> dict[str, str]:
    """Receive and verify Stripe webhook events."""
    body = await request.body()

    try:
        event = construct_event(body, stripe_signature)
    except PaymentsNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payments_not_configured",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        ) from exc

    event_type = str(event.get("type") or "")
    event_id = str(event.get("id") or "")
    raw_data = (event.get("data") or {}).get("object")
    event_data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

    if event_id and not await _mark_event_seen(event_id, event_type):
        return {"status": "duplicate"}

    if event_type == "payment_intent.succeeded":
        await _handle_payment_intent_succeeded(event_data)
    elif event_type == "charge.refunded":
        await _handle_charge_refunded(event_data)
    elif event_type == "charge.dispute.created":
        await _handle_dispute_created(event_data)
    elif event_type == "account.updated":
        await _handle_account_updated(event_data)
    elif event_type == "payout.paid":
        # Informational: funds landed in the tradie's bank. Nothing to mirror.
        logger.info("stripe_payout_paid", payout_id=event_data.get("id"))

    return {"status": "ok"}
