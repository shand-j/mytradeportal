"""Thin async wrapper around the Stripe SDK for Connect Express payments.

Customer → tradie invoice card payments run as **destination charges** on
Stripe Connect Express accounts (ADR-003): the platform creates the
PaymentIntent with ``transfer_data.destination`` set to the tradie's connected
account and **no** ``application_fee_amount`` (no platform take-rate). Stripe
hosts all card fields (Payment Element on the landing /pay page), so no PAN
ever touches our servers. UK consumer surcharging is not used.

Paddle remains for OUR SaaS subscription only; nothing here touches Paddle.

The ``stripe`` package is synchronous, so every call is dispatched with
:func:`asyncio.to_thread`. The SDK is imported lazily and the API key applied
per call, so an unconfigured environment (empty ``STRIPE_SECRET_KEY``) fails
with a clear :class:`PaymentsNotConfiguredError` instead of an import- or
startup-time crash — callers translate that to a 503 / a ``null`` payment URL.
"""

import asyncio
from typing import Any

import structlog

from app import config

logger = structlog.get_logger("api.stripe_client")

STRIPE_API_VERSION = "2025-08-27.basil"


class PaymentsNotConfiguredError(RuntimeError):
    """Raised when STRIPE_SECRET_KEY (or the webhook secret) is not set."""

    def __init__(self, detail: str = "payments_not_configured") -> None:
        super().__init__(detail)
        self.detail = detail


def is_configured() -> bool:
    """True when the secret key is present and Stripe calls can be made."""
    return bool(config.STRIPE_SECRET_KEY)


def _stripe() -> Any:
    """Return the configured ``stripe`` module, imported lazily."""
    if not config.STRIPE_SECRET_KEY:
        raise PaymentsNotConfiguredError()
    import stripe

    stripe.api_key = config.STRIPE_SECRET_KEY
    stripe.api_version = STRIPE_API_VERSION
    return stripe


async def create_express_account(
    *,
    email: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Create a Connect Express account for a tradie. Returns ``{"id": ...}``."""
    stripe = _stripe()
    payload: dict[str, Any] = {
        "type": "express",
        "country": "GB",
        "capabilities": {
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        "metadata": {"tenant_id": tenant_id or ""},
    }
    if email:
        payload["email"] = email
    account = await asyncio.to_thread(stripe.Account.create, **payload)
    return {"id": account["id"]}


async def create_account_link(
    account_id: str,
    *,
    return_url: str,
    refresh_url: str,
) -> str:
    """Create a one-time Express onboarding link. Returns the hosted URL."""
    stripe = _stripe()
    link = await asyncio.to_thread(
        stripe.AccountLink.create,
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return str(link["url"])


async def retrieve_account(account_id: str) -> dict[str, bool | str]:
    """Fetch the capability flags we mirror on ``StripeAccount``."""
    stripe = _stripe()
    account = await asyncio.to_thread(stripe.Account.retrieve, account_id)
    return {
        "id": account["id"],
        "details_submitted": bool(account.get("details_submitted", False)),
        "charges_enabled": bool(account.get("charges_enabled", False)),
        "payouts_enabled": bool(account.get("payouts_enabled", False)),
    }


async def create_payment_intent(
    *,
    amount_pence: int,
    currency: str,
    connected_account_id: str,
    invoice_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Create a destination-charge PaymentIntent for an invoice.

    The full amount settles to the tradie's connected account via
    ``transfer_data``; no ``application_fee_amount`` is set, so the platform
    takes nothing. Metadata carries the linkage the webhook needs to mark the
    invoice paid. Automatic payment methods keep Stripe hosting the fields.
    """
    if amount_pence < 1:
        raise ValueError("amount_pence must be >= 1")
    stripe = _stripe()
    intent = await asyncio.to_thread(
        stripe.PaymentIntent.create,
        amount=amount_pence,
        currency=currency.lower(),
        transfer_data={"destination": connected_account_id},
        automatic_payment_methods={"enabled": True},
        metadata={"invoice_id": invoice_id, "tenant_id": tenant_id},
    )
    return {"id": intent["id"], "client_secret": intent["client_secret"]}


async def retrieve_payment_intent(payment_intent_id: str) -> dict[str, Any]:
    """Fetch a PaymentIntent (used to reuse an open one for the /pay page)."""
    stripe = _stripe()
    intent = await asyncio.to_thread(stripe.PaymentIntent.retrieve, payment_intent_id)
    return {
        "id": intent["id"],
        "client_secret": intent["client_secret"],
        "status": intent["status"],
        "amount": int(intent["amount"]),
    }


async def create_refund(payment_intent_id: str) -> dict[str, Any]:
    """Refund a PaymentIntent in full. Returns ``{"id", "status"}``."""
    stripe = _stripe()
    refund = await asyncio.to_thread(
        stripe.Refund.create,
        payment_intent=payment_intent_id,
    )
    return {"id": refund["id"], "status": refund.get("status")}


def construct_event(body: bytes, signature_header: str) -> dict[str, Any]:
    """Verify the Stripe-Signature header and return the event payload.

    Raises :class:`PaymentsNotConfiguredError` when no webhook secret is set
    and :class:`ValueError` when the signature does not verify — the router
    maps those to 503 and 400 respectively.
    """
    if not config.STRIPE_WEBHOOK_SECRET:
        raise PaymentsNotConfiguredError()
    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(
            body,
            signature_header,
            config.STRIPE_WEBHOOK_SECRET,
        )
    except stripe.SignatureVerificationError as exc:
        raise ValueError("invalid stripe webhook signature") from exc
    # stripe-python >= 15 no longer subclasses dict (``dict(event)`` raises
    # TypeError); ``to_dict()`` exists across the pinned ``stripe>=10`` range,
    # with ``dict()`` kept as the fallback for any older release lacking it.
    to_dict = getattr(event, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return dict(event)
