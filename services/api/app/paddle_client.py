"""Async Paddle Billing client for checkout creation and webhook verification."""

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import httpx
from mtp_shared import get_settings

from app.models import Invoice

settings = get_settings()

PADDLE_SANDBOX_BASE = "https://sandbox-api.paddle.com"
PADDLE_PRODUCTION_BASE = "https://api.paddle.com"


def _paddle_base_url() -> str:
    return PADDLE_SANDBOX_BASE if settings.paddle_sandbox else PADDLE_PRODUCTION_BASE


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.paddle_api_key}",
        "Content-Type": "application/json",
    }


def _money_amount(amount: Decimal) -> str:
    """Convert Decimal to Paddle's integer minor-unit string."""
    return str(int((amount * 100).quantize(Decimal("1"))))


async def create_checkout(
    invoice: Invoice,
    success_url: str | None = None,
    customer_email: str | None = None,
) -> dict[str, str]:
    """Create a Paddle checkout for an invoice.

    Uses a non-catalog price so no Paddle product setup is required.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")

    items: list[dict[str, Any]] = []
    for line in invoice.line_items:
        items.append(
            {
                "price": {
                    "description": line.description[:255],
                    "unit_price": {
                        "amount": _money_amount(line.unit_price),
                        "currency_code": settings.paddle_default_currency_code,
                    },
                    "product": {
                        "name": invoice.invoice_number,
                        "tax_category": "standard",
                    },
                },
                "quantity": int(line.quantity),
            }
        )

    # Fallback item if no line items exist.
    if not items:
        items.append(
            {
                "price": {
                    "description": f"Invoice {invoice.invoice_number}",
                    "unit_price": {
                        "amount": _money_amount(invoice.total),
                        "currency_code": settings.paddle_default_currency_code,
                    },
                    "product": {
                        "name": "Electrical services",
                        "tax_category": "standard",
                    },
                },
                "quantity": 1,
            }
        )

    payload: dict[str, Any] = {
        "items": items,
        "custom_data": {
            "invoice_id": str(invoice.id),
            "tenant_id": str(invoice.tenant_id),
        },
    }
    if customer_email:
        payload["customer"] = {"email": customer_email}
    if success_url:
        payload["success_url"] = success_url

    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.post("/checkouts", json=payload)
        response.raise_for_status()
        data = response.json()["data"]
        return {
            "checkout_id": data["id"],
            "checkout_url": data["url"],
        }


async def get_or_create_customer(email: str, name: str | None = None) -> str:
    """Return the Paddle customer id for an email, creating the customer if needed.

    Binding a transaction to a customer makes the hosted checkout prefill the
    email and keeps it non-editable, so the subscription always belongs to the
    account that requested checkout. ``email`` filters are exact-match on
    Paddle's side; a create-then-conflict race is resolved with a retry.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:

        async def _lookup() -> str | None:
            response = await client.get("/customers", params={"email": email})
            response.raise_for_status()
            customers = response.json()["data"]
            return str(customers[0]["id"]) if customers else None

        existing = await _lookup()
        if existing:
            return existing

        payload: dict[str, Any] = {"email": email}
        if name:
            payload["name"] = name
        response = await client.post("/customers", json=payload)
        if response.status_code not in (200, 201):
            # Lost a create race (or the email filter missed a casing variant):
            # reconcile by looking the customer up again before failing.
            existing = await _lookup()
            if existing:
                return existing
            response.raise_for_status()
        return str(response.json()["data"]["id"])


async def create_subscription_transaction(
    price_id: str,
    tenant_id: str,
    plan_key: str,
    customer_email: str | None = None,
    success_url: str | None = None,
    discount_id: str | None = None,
    customer_id: str | None = None,
) -> dict[str, str]:
    """Create a Paddle Billing transaction for a subscription checkout.

    Returns the hosted checkout URL the client opens. Trials configured on
    the price are applied by Paddle automatically. ``customer_id`` binds the
    checkout to a Paddle customer so the email is prefilled and non-editable;
    when omitted, Paddle collects the email at checkout. ``discount_id``
    auto-applies a Paddle discount at checkout (used by the beta cohort to
    make plans free).
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    if not price_id:
        raise RuntimeError("Paddle price id is not configured for this plan")
    _ = customer_email  # contact email lives on the bound customer record

    payload: dict[str, Any] = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "collection_mode": "automatic",
        "custom_data": {
            "tenant_id": str(tenant_id),
            "plan_key": plan_key,
        },
    }
    if customer_id:
        payload["customer_id"] = customer_id
    if success_url:
        payload["checkout"] = {"url": success_url}
    if discount_id:
        payload["discount_id"] = discount_id

    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.post("/transactions", json=payload)
        response.raise_for_status()
        data = response.json()["data"]

    checkout_url = (data.get("checkout") or {}).get("url")
    if not checkout_url:
        raise RuntimeError("Paddle transaction created without a checkout URL")

    return {
        "transaction_id": data["id"],
        "checkout_url": checkout_url,
    }


def verify_webhook_signature(
    body: bytes,
    signature_header: str,
    secret: str | None = None,
) -> bool:
    """Verify a Paddle webhook signature using the configured webhook secret.

    Signature format: ts=<timestamp>;h1=<hex_signature>
    Signed payload: timestamp + ":" + raw_body
    """
    secret = secret or settings.paddle_webhook_secret
    if not secret:
        return False

    parts = dict(part.split("=") for part in signature_header.split(";") if "=" in part)
    timestamp = parts.get("ts")
    signature = parts.get("h1")
    if not timestamp or not signature:
        return False

    expected = hmac.new(
        secret.encode(),
        f"{timestamp}:".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_webhook_event(body: bytes) -> dict[str, Any]:
    """Parse a Paddle webhook payload."""
    return json.loads(body)  # type: ignore[no-any-return]
