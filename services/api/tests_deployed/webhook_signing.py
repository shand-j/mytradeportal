"""Webhook signature forgery + payload builders for the deployed write suite.

These mirror the exact verification logic in the production routers
(``app.routers.stripe_webhooks`` via ``stripe.Webhook.construct_event``,
``app.paddle_client.verify_webhook_signature`` and
``app.routers.resend_webhooks._verify_svix_signature``) so tests can deliver
syntactically authentic events against the real endpoints using the
environment's webhook secrets.

Only used against throwaway tenants on staging / PR environments. Never
against production.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Stripe (Stripe-Signature: t=<ts>,v1=<hmac>)
# ---------------------------------------------------------------------------


def stripe_signature(body: bytes, secret: str, timestamp: int | None = None) -> str:
    t = timestamp if timestamp is not None else int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def stripe_payment_intent_succeeded(
    *,
    invoice_id: str,
    tenant_id: str,
    amount_pence: int,
    intent_id: str | None = None,
    currency: str = "gbp",
) -> dict[str, Any]:
    resolved_intent = intent_id or f"pi_test_{uuid.uuid4().hex[:12]}"
    return {
        "id": f"evt_test_{uuid.uuid4().hex[:12]}",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": resolved_intent,
                "amount_received": amount_pence,
                "currency": currency,
                "metadata": {"invoice_id": invoice_id, "tenant_id": tenant_id},
            }
        },
    }


def stripe_charge_refunded(*, payment_intent_id: str) -> dict[str, Any]:
    return {
        "id": f"evt_test_{uuid.uuid4().hex[:12]}",
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": f"ch_test_{uuid.uuid4().hex[:12]}",
                "payment_intent": payment_intent_id,
            }
        },
    }


def stripe_account_updated(
    *, account_id: str, details_submitted: bool, charges_enabled: bool, payouts_enabled: bool
) -> dict[str, Any]:
    return {
        "id": f"evt_test_{uuid.uuid4().hex[:12]}",
        "type": "account.updated",
        "data": {
            "object": {
                "id": account_id,
                "details_submitted": details_submitted,
                "charges_enabled": charges_enabled,
                "payouts_enabled": payouts_enabled,
            }
        },
    }


# ---------------------------------------------------------------------------
# Paddle (Paddle-Signature: ts=<ts>;h1=<hmac>)
# ---------------------------------------------------------------------------


def paddle_signature(body: bytes, secret: str, timestamp: str | None = None) -> str:
    ts = timestamp if timestamp is not None else str(int(time.time()))
    h1 = hmac.new(secret.encode(), ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    return f"ts={ts};h1={h1}"


def paddle_subscription_event(
    *,
    event_type: str,
    tenant_id: str,
    status: str,
    price_id: str | None = None,
    event_id: str | None = None,
    subscription_id: str | None = None,
) -> dict[str, Any]:
    """Minimal subscription event matching Paddle Billing webhook shape.

    ``data.custom_data.tenant_id`` keys the upsert to our subscription row;
    ``data.items[0].price.id`` re-derives the plan key when the price id is
    one the api recognises.
    """
    item: dict[str, Any] = {"price": {"id": price_id} if price_id else {}}
    return {
        "event_id": event_id or f"evt_test_{uuid.uuid4().hex[:12]}",
        "event_type": event_type,
        "data": {
            "id": subscription_id or f"sub_test_{uuid.uuid4().hex[:12]}",
            "status": status,
            "custom_data": {"tenant_id": tenant_id},
            "items": [item],
        },
    }


# ---------------------------------------------------------------------------
# Resend (Svix: svix-id / svix-timestamp / svix-signature headers)
# ---------------------------------------------------------------------------


def resend_svix_headers(body: bytes, secret: str, event_id: str | None = None) -> dict[str, str]:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    svix_id = event_id or f"msg_test_{uuid.uuid4().hex[:12]}"
    ts = str(int(time.time()))
    msg = f"{svix_id}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}"}


def resend_bounce(*, to: str, tenant_id: str, contact_id: str) -> dict[str, Any]:
    return {
        "type": "email.bounced",
        "data": {
            "to": [to],
            "tags": {"mtp_tenant": tenant_id, "mtp_contact": contact_id},
            "bounce": {"type": "hard_bounce", "reason": "550 5.1.1 mailbox does not exist (test)"},
        },
    }


def encode_event(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()
