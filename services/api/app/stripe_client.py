"""Thin async wrapper around Stripe for Connect Express payments (Accounts v2).

Customer → tradie invoice card payments run as **destination charges** on
Stripe Connect Express accounts (ADR-003): the platform creates the
PaymentIntent with ``transfer_data.destination`` set to the tradie's connected
account and **no** ``application_fee_amount`` (no platform take-rate). Stripe
hosts all card fields (Payment Element on the landing /pay page), so no PAN
ever touches our servers. UK consumer surcharging is not used.

Connected accounts are created with the **Accounts v2 API**
(``POST /v2/core/accounts``, recipient configuration) — Accounts v1 creation
is deprecated and fails on new platforms. stripe-python 15.x exposes only
webhook helpers under ``stripe.v2`` (no account services), so the v2 REST
endpoints are called directly with httpx; v1 SDK calls remain for
PaymentIntents, refunds, webhook verification, and account links (verified
against v2 account IDs in the Stripe sandbox).

Paddle remains for OUR SaaS subscription only; nothing here touches Paddle.

The ``stripe`` package is synchronous, so SDK calls are dispatched with
:func:`asyncio.to_thread`; v2 calls use httpx natively. The SDK is imported
lazily and the API key applied per call, so an unconfigured environment
(empty ``STRIPE_SECRET_KEY``) fails with a clear
:class:`PaymentsNotConfiguredError` instead of an import- or startup-time
crash — callers translate that to a 503 / a ``null`` payment URL.
"""

import asyncio
import contextlib
import sys
from typing import Any

import httpx
import structlog

from app import config

logger = structlog.get_logger("api.stripe_client")

STRIPE_API_VERSION = "2025-08-27.basil"
STRIPE_V2_BASE_URL = "https://api.stripe.com/v2"
# Accounts v2 creation is preview-gated: the endpoint requires a `.preview`
# Stripe-Version header (verified in the sandbox on 2026-09-15 — a missing
# header returns 400 "You did not provide an API version" and a non-preview
# pin returns 404 "must explicitly specify a .preview Stripe-Version"). The
# v2 GET endpoints accept any pin, so this one header covers create + retrieve.
STRIPE_V2_API_VERSION = "2026-08-26.preview"


class PaymentsNotConfiguredError(RuntimeError):
    """Raised when STRIPE_SECRET_KEY (or the webhook secret) is not set."""

    def __init__(self, detail: str = "payments_not_configured") -> None:
        super().__init__(detail)
        self.detail = detail


class StripeV2Error(RuntimeError):
    """An Accounts v2 call failed (non-2xx response from Stripe)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(f"stripe v2 error {status_code} ({code}): {message}")
        self.status_code = status_code
        self.code = code
        self.message = message


def is_stripe_error(exc: BaseException) -> bool:
    """True when ``exc`` is a Stripe-side failure from either API surface.

    Covers :class:`StripeV2Error` (httpx-called Accounts v2 endpoints) and
    ``stripe.StripeError`` from the lazily imported SDK, letting routers catch
    Stripe failures (e.g. the platform not enrolled in Connect) without
    importing ``stripe`` themselves.
    """
    if isinstance(exc, StripeV2Error):
        return True
    stripe = sys.modules.get("stripe")
    return stripe is not None and isinstance(exc, stripe.StripeError)


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


async def _v2_request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: list[tuple[str, str | int | float | bool | None]] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Call an Accounts v2 endpoint and return the decoded JSON body."""
    if not config.STRIPE_SECRET_KEY:
        raise PaymentsNotConfiguredError()
    headers = {
        "Authorization": f"Bearer {config.STRIPE_SECRET_KEY}",
        "Stripe-Version": STRIPE_V2_API_VERSION,
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(
            method,
            f"{STRIPE_V2_BASE_URL}{path}",
            json=json_body,
            params=params,
            headers=headers,
        )
    if response.status_code >= 400:
        error: dict[str, Any] = {}
        with contextlib.suppress(ValueError):
            error = response.json().get("error", {})
        raise StripeV2Error(
            response.status_code,
            str(error.get("code") or "unknown_error"),
            str(error.get("message") or response.text[:300]),
        )
    return dict(response.json())


async def create_connected_account_v2(
    *,
    email: str | None = None,
    display_name: str | None = None,
    tenant_id: str | None = None,
    phone: str | None = None,
    postcode: str | None = None,
    entity_type: str | None = None,
    business_url: str | None = None,
) -> dict[str, Any]:
    """Create a v2 connected Account with the recipient configuration (ADR-003).

    Marketplace defaults per the Accounts v2 guidance: ``dashboard: "express"``
    with the platform as both fees and losses collector (``"application"``),
    and the ``stripe_balance.stripe_transfers`` capability requested on the
    recipient configuration — the v2 go-live check for destination charges.
    No ``merchant``/``card_payments`` configuration is requested (that would
    only lengthen onboarding; the platform remains merchant of record).
    Returns ``{"id": ...}``.

    Everything we already know about the tradie is pre-filled (contact email,
    phone, trading name, postcode, entity type from their business structure)
    so Stripe's onboarding skips those steps. ``entity_type`` is the v2
    identity enum: ``"individual"`` for sole traders, ``"company"`` for
    ltd/LLP — passed only when known, never guessed.

    ``business_url`` (the tenant's customer portal URL) is pre-filled as the
    account's business website so hosted onboarding doesn't block tradespeople
    who have no site of their own. The v2 home for it is
    ``defaults.profile.url``: ``identity.business_details.url`` was removed in
    the 2025-09-30.clover preview, which the pinned ``STRIPE_V2_API_VERSION``
    post-dates.
    """
    identity: dict[str, Any] = {"country": "gb"}
    if entity_type:
        identity["entity_type"] = entity_type
    business_details: dict[str, Any] = {}
    if display_name:
        business_details["registered_name"] = display_name
    if postcode:
        business_details["address"] = {"country": "gb", "postal_code": postcode}
    if business_details:
        identity["business_details"] = business_details
    payload: dict[str, Any] = {
        "display_name": display_name or "My Trade Portal tradesperson",
        "identity": identity,
        "dashboard": "express",
        "defaults": {
            "responsibilities": {
                "fees_collector": "application",
                "losses_collector": "application",
            }
        },
        "configuration": {
            "recipient": {
                "capabilities": {
                    "stripe_balance": {"stripe_transfers": {"requested": True}},
                },
            },
        },
        "metadata": {"tenant_id": tenant_id or ""},
        "include": ["configuration.recipient", "requirements"],
    }
    if email:
        payload["contact_email"] = email
    if phone:
        payload["contact_phone"] = phone
    if business_url:
        payload["defaults"]["profile"] = {"url": business_url}
    account = await _v2_request(
        "POST",
        "/core/accounts",
        json_body=payload,
        # Same tenant-scoped key across retries returns the same account,
        # so a double-submit can never provision two connected accounts.
        idempotency_key=f"mtp-connect-{tenant_id}" if tenant_id else None,
    )
    return {"id": account["id"]}


async def create_account_link(
    account_id: str,
    *,
    return_url: str,
    refresh_url: str,
) -> str:
    """Create a one-time Express onboarding link. Returns the hosted URL.

    Despite the v1 path, Account Links are valid for Accounts v2 IDs — Stripe
    documents that a v2 account ID can be passed to Accounts v1 endpoints, and
    this was verified against a sandbox v2 account on 2026-09-15 (200,
    ``connect.stripe.com`` hosted URL). This keeps the hosted-onboarding UX
    without any embedded-component frontend work.
    """
    stripe = _stripe()
    link = await asyncio.to_thread(
        stripe.AccountLink.create,
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return str(link["url"])


async def create_account_session(account_id: str) -> dict[str, Any]:
    """Create an AccountSession for the embedded onboarding component.

    Returns ``{"client_secret": ..., "expires_at": ...}`` — the client secret
    authorises Stripe's embedded Connect components (RN SDK / Stripe.js) to
    run account onboarding natively in-app for this connected account. Only
    the ``account_onboarding`` component is enabled; payouts/balances stay in
    Stripe's hosted Express dashboard.
    """
    stripe = _stripe()
    session = await asyncio.to_thread(
        stripe.AccountSession.create,
        account=account_id,
        components={"account_onboarding": {"enabled": True}},
    )
    return {"client_secret": session["client_secret"], "expires_at": int(session["expires_at"])}


def _capability_flags(account: dict[str, Any]) -> dict[str, bool | str]:
    """Map a v2 Account's recipient capabilities onto our v1-era columns.

    v2 removed the v1 ``charges_enabled`` / ``payouts_enabled`` fields; the
    go-live check for a recipient (marketplace) account is
    ``configuration.recipient.capabilities.stripe_balance.stripe_transfers.status``.
    We mirror it onto ``charges_enabled`` (the account can receive the funds
    of a destination charge) and ``stripe_balance.payouts.status`` onto
    ``payouts_enabled`` (Stripe can pay the balance out to the tradie). The
    column names are kept to avoid a migration — the semantics are documented
    here and in the PR. ``details_submitted`` has no v2 equivalent; best
    effort, it is True once no requirement entry awaits user action.
    """
    recipient = (account.get("configuration") or {}).get("recipient") or {}
    capabilities = recipient.get("capabilities") or {}
    stripe_balance = capabilities.get("stripe_balance") or {}
    transfers_status = (stripe_balance.get("stripe_transfers") or {}).get("status")
    payouts_status = (stripe_balance.get("payouts") or {}).get("status")
    entries = (account.get("requirements") or {}).get("entries") or []
    awaiting_user = any(entry.get("awaiting_action_from") == "user" for entry in entries)
    return {
        "id": str(account["id"]),
        "details_submitted": not awaiting_user,
        "charges_enabled": transfers_status == "active",
        "payouts_enabled": payouts_status == "active",
    }


async def retrieve_account(account_id: str) -> dict[str, bool | str]:
    """Fetch the capability flags we mirror on ``StripeAccount`` (Accounts v2).

    Requests ``configuration.recipient`` and ``requirements`` via the v2
    ``include`` parameter — without it the response omits both.
    """
    account = await _v2_request(
        "GET",
        f"/core/accounts/{account_id}",
        params=[("include", "configuration.recipient"), ("include", "requirements")],
    )
    return _capability_flags(account)


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
