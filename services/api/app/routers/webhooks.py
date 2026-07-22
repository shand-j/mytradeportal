"""Paddle webhook endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine
from app.models import Invoice, Payment
from app.paddle_client import parse_webhook_event, verify_webhook_signature

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


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
    event_type = event.get("event_type")
    event_data = event.get("data", {})

    custom_data = event_data.get("custom_data", {})
    invoice_id = custom_data.get("invoice_id")

    if event_type in {"transaction.completed", "transaction.paid"} and invoice_id:
        await _record_payment(invoice_id, event_data)

    return {"status": "ok"}
