"""Async Paddle Billing client for checkout creation and webhook verification."""

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import httpx
from mtp_shared import get_settings

from app.models import Invoice
from app.plans import OVERAGE_PRICE_PENCE

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


async def create_customer_portal_session(customer_id: str) -> str:
    """Create a Paddle customer portal session and return its overview URL.

    The overview URL is a one-time, short-lived link into Paddle's hosted
    customer portal (manage payment method, download invoices, cancel). Only
    the overview URL is returned — the raw session payload (customer id,
    per-subscription deep links) never leaves the server.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.post(f"/customers/{customer_id}/portal-sessions")
        response.raise_for_status()
        data = response.json()["data"]
    return str(data["urls"]["general"]["overview"])


async def create_subscription_transaction(
    price_id: str,
    tenant_id: str,
    plan_key: str,
    customer_email: str | None = None,
    success_url: str | None = None,
    discount_id: str | None = None,
    customer_id: str | None = None,
    quantity: int = 1,
) -> dict[str, str]:
    """Create a Paddle Billing transaction for a subscription checkout.

    Returns the hosted checkout URL the client opens. Trials configured on
    the price are applied by Paddle automatically. ``customer_id`` binds the
    checkout to a Paddle customer so the email is prefilled and non-editable;
    when omitted, Paddle collects the email at checkout. ``discount_id``
    auto-applies a Paddle discount at checkout (used by the beta cohort to
    make plans free). ``quantity`` is the seat count for per-seat prices
    (Team); it must respect the quantity limits set on the price.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    if not price_id:
        raise RuntimeError("Paddle price id is not configured for this plan")
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    _ = customer_email  # contact email lives on the bound customer record

    payload: dict[str, Any] = {
        "items": [{"price_id": price_id, "quantity": quantity}],
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


_METERED_EFFECTIVE_FROM = frozenset({"immediately", "next_billing_period"})


async def report_metered_usage(
    subscription_id: str,
    quantity: int,
    *,
    unit_price_pence: int | None = None,
    description: str | None = None,
    effective_from: str = "next_billing_period",
) -> dict[str, Any]:
    """Report metered AI-overage usage against a subscription.

    Paddle Billing has no native metered/usage-based price type (verified
    against the sandbox API 2026-09-12: price ``type`` only accepts
    ``standard``/``custom``, and native usage-based billing is waitlist-only).
    The supported overage pattern is a one-time charge on the subscription:
    ``POST /subscriptions/{id}/charge`` with a non-catalog price, billed with
    the next renewal by default (``effective_from="next_billing_period"``) or
    collected right away with ``"immediately"``. The catalog price
    ``PADDLE_PRICE_ID_AI_OVERAGE`` (£0.06/unit, recurring) documents the unit
    rate in the Paddle dashboard; the actual charge carries the same rate
    inline.

    ``quantity`` is the number of overage AI actions for the period;
    ``unit_price_pence`` defaults to the catalog overage rate
    (``plans.OVERAGE_PRICE_PENCE``). Returns the created transaction's id and
    status.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    if effective_from not in _METERED_EFFECTIVE_FROM:
        raise ValueError(f"effective_from must be one of {sorted(_METERED_EFFECTIVE_FROM)}")

    pence = unit_price_pence if unit_price_pence is not None else OVERAGE_PRICE_PENCE
    if pence < 1:
        raise ValueError("unit_price_pence must be >= 1")

    payload: dict[str, Any] = {
        "effective_from": effective_from,
        "items": [
            {
                "price": {
                    "description": (
                        description or f"AI overage — {quantity} actions @ £{pence / 100:.2f}"
                    )[:500],
                    "unit_price": {
                        "amount": str(pence),
                        "currency_code": settings.paddle_default_currency_code,
                    },
                    "product": {
                        "name": "My Trade Portal — AI Overage",
                        "tax_category": "saas",
                    },
                },
                "quantity": quantity,
            }
        ],
    }

    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.post(f"/subscriptions/{subscription_id}/charge", json=payload)
        response.raise_for_status()
        data = response.json()["data"]

    return {
        "transaction_id": data["id"],
        "status": data.get("status"),
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
