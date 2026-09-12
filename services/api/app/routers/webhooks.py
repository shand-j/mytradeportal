"""Paddle webhook endpoints.

Paddle delivers at-least-once with per-attempt HMAC signatures. This handler
verifies the signature, dedupes on ``event_id``, and routes the payload to
type-specific upsert handlers. Any non-2xx response is retried by Paddle on
the same budget, so signature failures return 401 and unexpected errors
return 500 — both cause a retry, which is what we want when a secret has
just been rotated or a downstream store blipped.
"""

import os
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
from app.config import settings
from app.database import engine
from app.models import Invoice, Payment, ProcessedWebhook, Quote, Subscription
from app.paddle_client import parse_webhook_event, verify_webhook_signature
from app.plans import PLANS, resolve_plan_key

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = structlog.get_logger("api.webhooks")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _first_item(event_data: dict[str, Any]) -> dict[str, Any]:
    items = event_data.get("items") or []
    return items[0] if items else {}


def _price_id_plan_map() -> dict[str, str]:
    """Map every configured Paddle price id to its current plan key.

    Covers the per-interval catalog vars (``PADDLE_PRICE_ID_{TIER}_{MONTH,
    YEAR}``, read from the process environment because the settings object
    predates them) and the legacy beta-era single-price vars. Values resolve
    to current catalog keys (``sole_trader``/``pro``/``team``).
    """
    mapping: dict[str, str] = {}
    for plan in PLANS:
        for env_name in (plan.monthly_price_env, plan.annual_price_env):
            price_id = os.environ.get(env_name, "").strip()
            if price_id:
                mapping[price_id] = plan.key
    legacy: tuple[tuple[str, str], ...] = (
        (settings.paddle_price_id_starter, "starter"),
        (settings.paddle_price_id_pro, "pro"),
        (settings.paddle_price_id_business, "business"),
    )
    for price_id, plan_key in legacy:
        if price_id and price_id not in mapping:
            mapping[price_id] = resolve_plan_key(plan_key)
    return mapping


def _plan_key_for_price_id(price_id: str | None) -> str | None:
    """Resolve a Paddle price id to a current plan key, or None if unknown."""
    if not price_id:
        return None
    return _price_id_plan_map().get(price_id)


def _is_overage_item(item: dict[str, Any]) -> bool:
    """Detect a metered AI-overage line on a transaction.

    Overage is billed via ``paddle_client.report_metered_usage`` (one-time
    charge, non-catalog price). A line counts as overage when its price id
    or product id matches the configured overage catalog entities, or when
    its (non-catalog) price carries the overage description prefix.
    """
    price = item.get("price") or {}
    overage_price_id = os.environ.get("PADDLE_PRICE_ID_AI_OVERAGE", "").strip()
    overage_product_id = os.environ.get("PADDLE_PRODUCT_ID_AI_OVERAGE", "").strip()
    if overage_price_id and price.get("id") == overage_price_id:
        return True
    if overage_product_id and price.get("product_id") == overage_product_id:
        return True
    description = str(price.get("description") or "")
    return description.startswith("AI overage")


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
        # Close the AI funnel when the paid invoice traces back to an
        # AI-drafted quote (fail-open; committed with this session).
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
                        "actor": "paddle_webhook",
                        "provider_transaction_id": transaction_id,
                    },
                )
        await session.commit()


async def _record_overage_billing(event_data: dict[str, Any]) -> None:
    """Record a billed metered-overage transaction on the subscription row.

    Triggered by ``transaction.billed`` for one-time charges created via
    ``paddle_client.report_metered_usage``. The usage/cost summary is folded
    into ``Subscription.provider_payload["ai_overage_billing"]`` (keyed on the
    Paddle transaction id, so at-least-once delivery is idempotent) — no new
    table. Transactions without overage line items (plain renewals) are
    ignored.
    """
    subscription_id = event_data.get("subscription_id")
    if not subscription_id:
        return

    overage_items = [item for item in (event_data.get("items") or []) if _is_overage_item(item)]
    if not overage_items:
        return

    quantity = sum(int(item.get("quantity") or 0) for item in overage_items)
    amount_pence = 0
    currency = event_data.get("currency_code", settings.paddle_default_currency_code)
    for item in overage_items:
        unit_price = ((item.get("price") or {}).get("unit_price")) or {}
        try:
            unit_amount = int(unit_price.get("amount") or 0)
        except (TypeError, ValueError):
            unit_amount = 0
        currency = unit_price.get("currency_code") or currency
        amount_pence += unit_amount * int(item.get("quantity") or 0)

    transaction_id = event_data.get("id") or "unknown"

    async with AsyncSession(engine) as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.paddle_subscription_id == subscription_id)
        )
        if sub is None:
            logger.warning(
                "paddle_overage_orphan",
                paddle_subscription_id=subscription_id,
                transaction_id=transaction_id,
            )
            return

        payload = dict(sub.provider_payload or {})
        ledger = dict(payload.get("ai_overage_billing") or {})
        ledger[str(transaction_id)] = {
            "transaction_id": transaction_id,
            "billed_at": event_data.get("billed_at") or event_data.get("updated_at"),
            # Raw ISO strings — provider_payload is JSONB, so no datetimes.
            "period_start": (event_data.get("billing_period") or {}).get("starts_at"),
            "period_end": (event_data.get("billing_period") or {}).get("ends_at"),
            "actions": quantity,
            "amount_pence": amount_pence,
            "currency_code": currency,
        }
        payload["ai_overage_billing"] = ledger
        sub.provider_payload = payload  # reassign so SQLAlchemy sees the change
        session.add(sub)
        log_tenant_id = str(sub.tenant_id)  # snapshot before commit expires the row
        await session.commit()

        logger.info(
            "paddle_overage_recorded",
            tenant_id=log_tenant_id,
            paddle_subscription_id=subscription_id,
            transaction_id=transaction_id,
            actions=quantity,
            amount_pence=amount_pence,
        )


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
        # The price id is the source of truth for the plan: re-derive on every
        # event so plan changes (upgrades/downgrades, annual switches) and
        # checkout-time drift self-heal. Unknown price ids keep the stored key.
        derived_plan_key = _plan_key_for_price_id(sub.paddle_price_id)
        if derived_plan_key:
            sub.plan_key = derived_plan_key
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
        # Preserve the locally-maintained overage ledger across payload
        # overwrites (subscription events carry Paddle's view, not ours).
        overage_ledger = (sub.provider_payload or {}).get("ai_overage_billing")
        sub.provider_payload = event_data
        if overage_ledger:
            sub.provider_payload = {**event_data, "ai_overage_billing": overage_ledger}
        session.add(sub)
        # Snapshot log fields before commit: commit() expires the ORM object
        # and post-commit attribute access would trigger a lazy refresh
        # outside a greenlet (MissingGreenlet).
        log_tenant_id = str(sub.tenant_id)
        log_status = sub.status
        log_plan_key = sub.plan_key
        await session.commit()

        logger.info(
            "paddle_subscription_synced",
            event_type=event_type,
            tenant_id=log_tenant_id,
            status=log_status,
            plan_key=log_plan_key,
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
    elif event_type == "transaction.billed":
        await _record_overage_billing(event_data)

    return {"status": "ok"}
