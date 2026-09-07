"""Paddle webhook endpoints.

Paddle delivers at-least-once with per-attempt HMAC signatures. This handler
verifies the signature, dedupes on ``event_id``, and routes the payload to
type-specific upsert handlers. Any non-2xx response is retried by Paddle on
the same budget, so signature failures return 401 and unexpected errors
return 500 — both cause a retry, which is what we want when a secret has
just been rotated or a downstream store blipped.
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

from app.config import settings
from app.database import engine
from app.models import Invoice, Payment, ProcessedWebhook, Subscription
from app.paddle_client import parse_webhook_event, verify_webhook_signature

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = structlog.get_logger("api.webhooks")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _first_item(event_data: dict[str, Any]) -> dict[str, Any]:
    items = event_data.get("items") or []
    return items[0] if items else {}


async def _record_payment(invoice_id: str, event_data: dict[str, Any]) -> None:
    """Persist a Paddle payment against the matching invoice."""
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
        invoice = result.scalar_one_or_none()
        if invoice is None:
            return

        total = event_data.get("details", {}).get("totals", {}).get("total", "0")
        currency = event_data.get("currency_code", settings.paddle_default_currency_code)
        transaction_id = event_data.get("id")
        checkout_id = event_data.get("checkout", {}).get("id")

        payment = Payment(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            amount=Decimal(total) / 100 if isinstance(total, (int, str)) else Decimal("0.00"),
            currency_code=currency,
            status="completed",
            provider_transaction_id=transaction_id,
            provider_checkout_id=checkout_id,
            provider_payload=event_data,
            paid_at=datetime.utcnow(),
        )
        invoice.status = "paid"
        invoice.paid_at = datetime.utcnow()
        invoice.paddle_transaction_id = transaction_id
        session.add(payment)
        session.add(invoice)
        await session.commit()


async def _upsert_subscription(event_type: str, event_data: dict[str, Any]) -> None:
    """Mirror a Paddle subscription onto our ``subscriptions`` row.

    Keyed on ``custom_data.tenant_id`` (set at checkout) so the initial
    ``subscription.created`` event finds the pre-existing ``incomplete`` row
    written by ``POST /billing/checkout``. Subsequent updates re-key on
    ``paddle_subscription_id`` if custom_data was stripped.
    """
    custom_data = event_data.get("custom_data") or {}
    tenant_id_raw = custom_data.get("tenant_id")
    paddle_subscription_id = event_data.get("id")

    async with AsyncSession(engine) as session:
        sub: Subscription | None = None
        if tenant_id_raw:
            try:
                tenant_uuid = UUID(tenant_id_raw)
            except ValueError:
                tenant_uuid = None
            if tenant_uuid is not None:
                sub = await session.scalar(
                    select(Subscription).where(Subscription.tenant_id == tenant_uuid)
                )
        if sub is None and paddle_subscription_id:
            sub = await session.scalar(
                select(Subscription).where(
                    Subscription.paddle_subscription_id == paddle_subscription_id
                )
            )
        if sub is None:
            logger.warning(
                "paddle_subscription_orphan",
                event_type=event_type,
                paddle_subscription_id=paddle_subscription_id,
                tenant_id=tenant_id_raw,
            )
            return

        first_item = _first_item(event_data)
        price = first_item.get("price") or {}
        current_billing_period = event_data.get("current_billing_period") or {}
        scheduled_change = event_data.get("scheduled_change") or {}

        sub.paddle_subscription_id = paddle_subscription_id or sub.paddle_subscription_id
        sub.paddle_customer_id = event_data.get("customer_id") or sub.paddle_customer_id
        sub.paddle_price_id = price.get("id") or sub.paddle_price_id
        sub.paddle_product_id = price.get("product_id") or sub.paddle_product_id
        sub.status = event_data.get("status") or sub.status
        trial_dates = first_item.get("trial_dates") or {}
        if trial_dates.get("ends_at"):
            sub.trial_ends_at = _parse_dt(trial_dates.get("ends_at"))
        if current_billing_period.get("starts_at"):
            sub.current_period_start = _parse_dt(current_billing_period.get("starts_at"))
        if current_billing_period.get("ends_at"):
            sub.current_period_end = _parse_dt(current_billing_period.get("ends_at"))
        sub.scheduled_change_action = scheduled_change.get("action")
        sub.scheduled_change_at = _parse_dt(scheduled_change.get("effective_at"))
        if event_type == "subscription.canceled":
            sub.canceled_at = _parse_dt(event_data.get("canceled_at")) or datetime.utcnow()
        sub.provider_payload = event_data
        session.add(sub)
        await session.commit()

        logger.info(
            "paddle_subscription_synced",
            event_type=event_type,
            tenant_id=str(sub.tenant_id),
            status=sub.status,
            plan_key=sub.plan_key,
        )


async def _mark_event_seen(event_id: str, event_type: str) -> bool:
    """Insert into the dedup ledger. Returns False if already seen."""
    async with AsyncSession(engine) as session:
        session.add(ProcessedWebhook(event_id=event_id, event_type=event_type))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
    return True


_SUBSCRIPTION_EVENTS = frozenset(
    {
        "subscription.created",
        "subscription.updated",
        "subscription.canceled",
        "subscription.activated",
        "subscription.paused",
        "subscription.resumed",
        "subscription.past_due",
        "subscription.trialing",
    }
)


@router.post("/paddle")
async def paddle_webhook(
    request: Request,
    paddle_signature: str = Header(..., alias="Paddle-Signature"),
) -> dict[str, str]:
    """Receive and verify Paddle webhook events."""
    body = await request.body()

    if not verify_webhook_signature(body, paddle_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    event = parse_webhook_event(body)
    event_type = event.get("event_type") or ""
    event_id = event.get("event_id") or event.get("id") or ""
    raw_data = event.get("data")
    event_data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

    if event_id and not await _mark_event_seen(event_id, event_type):
        return {"status": "duplicate"}

    if event_type in _SUBSCRIPTION_EVENTS:
        await _upsert_subscription(event_type, event_data)
    elif event_type in {"transaction.completed", "transaction.paid"}:
        custom_data = event_data.get("custom_data") or {}
        invoice_id = custom_data.get("invoice_id")
        if invoice_id:
            await _record_payment(invoice_id, event_data)

    return {"status": "ok"}
