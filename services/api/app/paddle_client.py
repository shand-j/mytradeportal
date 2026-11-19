"""Async Paddle Billing client for subscription checkout and webhook verification.

Paddle bills OUR SaaS subscription only. Tradie receivables (customer invoice
card payments) run through Stripe Connect (ADR-003, ``app.stripe_client``) and
never touch Paddle.
"""

import asyncio
import hashlib
import hmac
import json
from typing import Any

import httpx
import structlog
from mtp_shared import get_settings

settings = get_settings()

logger = structlog.get_logger("api.paddle_client")

PADDLE_SANDBOX_BASE = "https://sandbox-api.paddle.com"
PADDLE_PRODUCTION_BASE = "https://api.paddle.com"


def _paddle_base_url() -> str:
    return PADDLE_SANDBOX_BASE if settings.paddle_sandbox else PADDLE_PRODUCTION_BASE


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.paddle_api_key}",
        "Content-Type": "application/json",
    }


def _raise_for_status(response: httpx.Response, context: str) -> None:
    """``raise_for_status`` plus a log line carrying Paddle's response body.

    Paddle's error bodies are machine-readable ``{"error": {code, detail}}``
    JSON with no customer PII — and they are the only way to diagnose the
    intermittent 502s surfaced by ``/billing/checkout`` (the bare
    ``HTTPStatusError`` message carries just the status line). Bodies are
    truncated and never include request payloads.
    """
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        body = getattr(response, "text", None)
        if not body:
            try:
                body = json.dumps(response.json())
            except Exception:
                body = ""
        logger.error(
            "paddle_api_error",
            context=context,
            status_code=response.status_code,
            body=body[:500],
        )
        raise


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
            _raise_for_status(response, "get_customer")
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
            _raise_for_status(response, "create_customer")
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
        _raise_for_status(response, "create_portal_session")
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
) -> dict[str, str]:
    """Create a Paddle Billing transaction for a card-required checkout.

    Returns the hosted checkout URL the client opens. One flat subscription
    per business: there is no seat or quantity logic — the Paddle price is the
    whole tier, so every checkout is a single unit of one price. Trials
    configured on the price are applied by Paddle automatically.
    ``customer_id`` binds the checkout to a Paddle customer so the email is
    prefilled and non-editable; when omitted, Paddle collects the email at
    checkout. ``discount_id`` auto-applies a Paddle discount at checkout (used
    by the beta cohort to make plans free).

    Only usable for prices whose trial (if any) REQUIRES a payment method.
    Paddle rejects a rendered checkout for a cardless-trial price
    (``requires_payment_method: false``) with "Cardless trial transaction is
    not linked to a subscription" — those prices go through
    :func:`create_cardless_trial_transaction` +
    :func:`get_payment_method_update_transaction` instead.
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
        _raise_for_status(response, "create_subscription_transaction")
        data = response.json()["data"]

    checkout_url = (data.get("checkout") or {}).get("url")
    if not checkout_url:
        raise RuntimeError("Paddle transaction created without a checkout URL")

    return {
        "transaction_id": data["id"],
        "checkout_url": checkout_url,
    }


async def update_subscription(
    subscription_id: str,
    price_id: str,
    proration_billing_mode: str = "prorated_immediately",
) -> dict[str, Any]:
    """Move a subscription to a new flat-tier price, prorating immediately.

    ``PATCH /subscriptions/{id}`` with an items array that *replaces* the
    subscription's line items (Paddle semantics: never append — appending
    bills the business for both plans at once). ``prorated_immediately``
    charges/credits the difference for the remainder of the current period
    now, so a mid-cycle plan change takes effect right away; the resulting
    ``subscription.updated`` webhook re-syncs the mirror (the plan key is
    re-derived from the new price id). If the prorated charge fails Paddle
    defaults to ``prevent_change``: the plan is NOT moved, the API errors,
    and the caller surfaces that to the user.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    payload: dict[str, Any] = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "proration_billing_mode": proration_billing_mode,
    }
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.patch(f"/subscriptions/{subscription_id}", json=payload)
        _raise_for_status(response, "update_subscription")
        return response.json()["data"]  # type: ignore[no-any-return]


async def get_price(price_id: str) -> dict[str, Any]:
    """Fetch a price entity; used to inspect its trial configuration."""
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.get(f"/prices/{price_id}")
        _raise_for_status(response, "get_price")
        return response.json()["data"]  # type: ignore[no-any-return]


async def cancel_subscription(subscription_id: str) -> None:
    """Cancel a subscription immediately (tenant offboarding).

    ``POST /subscriptions/{id}/cancel`` with ``effective_from=immediately``
    stops billing at once; the resulting ``subscription.canceled`` webhook
    re-syncs the local mirror. Callers treat this as best-effort — an
    unconfigured key or a Paddle outage must never block offboarding.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.post(
            f"/subscriptions/{subscription_id}/cancel",
            json={"effective_from": "immediately"},
        )
        _raise_for_status(response, "cancel_subscription")


async def create_customer_address(
    customer_id: str,
    country_code: str = "GB",
    postal_code: str | None = None,
) -> str:
    """Create a billing address for a Paddle customer and return its id.

    Billed transactions (including the zero-value transaction that fulfils a
    cardless trial) require an address for currency/tax determination.
    Businesses are UK trades by definition, so the country defaults to GB.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    payload: dict[str, Any] = {"country_code": country_code}
    if postal_code:
        payload["postal_code"] = postal_code
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.post(f"/customers/{customer_id}/addresses", json=payload)
        _raise_for_status(response, "create_customer_address")
        data = response.json()["data"]
    return str(data["id"])


async def create_cardless_trial_transaction(
    price_id: str,
    tenant_id: str,
    plan_key: str,
    customer_id: str,
    address_id: str,
) -> str:
    """Create a cardless-trial subscription server-side; return the transaction id.

    Paddle never renders a signup checkout for a price whose trial has
    ``requires_payment_method: false`` — the subscription must be created via
    the API: a transaction with ``status: "billed"`` is auto-completed (no
    payment due) and Paddle creates the trialing subscription for its items.
    The subscription id appears on the transaction shortly afterwards; resolve
    it with :func:`await_transaction_subscription_id`.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    payload: dict[str, Any] = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "customer_id": customer_id,
        "address_id": address_id,
        "collection_mode": "automatic",
        "status": "billed",
        "custom_data": {
            "tenant_id": str(tenant_id),
            "plan_key": plan_key,
        },
    }
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.post("/transactions", json=payload)
        _raise_for_status(response, "create_cardless_trial_transaction")
        data = response.json()["data"]
    return str(data["id"])


async def get_transaction_subscription_id(transaction_id: str) -> str | None:
    """Return the subscription id Paddle created for a transaction, if any.

    Transaction completion is asynchronous (typically < 1s), so a freshly
    billed cardless-trial transaction may not have ``subscription_id`` set
    yet — callers poll via :func:`await_transaction_subscription_id`.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.get(f"/transactions/{transaction_id}")
        _raise_for_status(response, "get_transaction")
        data = response.json()["data"]
    subscription_id = data.get("subscription_id")
    return str(subscription_id) if subscription_id else None


async def await_transaction_subscription_id(
    transaction_id: str,
    *,
    attempts: int = 8,
    delay_seconds: float = 0.5,
) -> str:
    """Poll a billed transaction until Paddle attaches the created subscription id."""
    for attempt in range(attempts):
        subscription_id = await get_transaction_subscription_id(transaction_id)
        if subscription_id:
            return subscription_id
        if attempt < attempts - 1:
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(
        f"Paddle did not attach a subscription to transaction {transaction_id} "
        f"after {attempts} attempts"
    )


async def update_subscription_custom_data(
    subscription_id: str,
    custom_data: dict[str, Any],
) -> None:
    """Stamp ``custom_data`` onto a subscription (fields omitted from the PATCH
    are untouched, so this never alters items or billing).

    Subscription webhook events key our mirror row on ``custom_data.tenant_id``;
    stamping it at creation makes that keying deterministic regardless of
    whether Paddle propagates the originating transaction's ``custom_data``.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.patch(
            f"/subscriptions/{subscription_id}",
            json={"custom_data": custom_data},
        )
        _raise_for_status(response, "update_subscription_custom_data")


async def get_payment_method_update_transaction(subscription_id: str) -> dict[str, str]:
    """Return ``{transaction_id, checkout_url}`` for a subscription-linked
    payment-method checkout.

    This is the only rendered checkout Paddle supports for a cardless trial:
    a zero-value transaction bound to the subscription, which must be opened
    with the one-page Paddle.js variant (the checkout page does this). The
    customer is not charged — the stored payment method takes over when the
    trial ends.
    """
    if not settings.paddle_api_key:
        raise RuntimeError("Paddle API key is not configured")
    async with httpx.AsyncClient(base_url=_paddle_base_url(), headers=_headers()) as client:
        response = await client.get(
            f"/subscriptions/{subscription_id}/update-payment-method-transaction"
        )
        _raise_for_status(response, "get_payment_method_update_transaction")
        data = response.json()["data"]

    checkout_url = (data.get("checkout") or {}).get("url")
    if not checkout_url:
        raise RuntimeError("Paddle did not return a checkout URL for the payment method update")

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
