#!/usr/bin/env python3
"""Replay a Stripe webhook against the local evidence API with a REAL signature.

Nothing here is mocked except Stripe itself: the event body is hand-built,
but the ``Stripe-Signature`` header is a genuine HMAC-SHA256 computed exactly
the way Stripe computes it (``t=<ts>,v1=<hmac(secret, "<ts>.<body>")``), so
the API's ``stripe.Webhook.construct_event`` verification runs for real
against the test ``STRIPE_WEBHOOK_SECRET`` the stubbed API was started with.

Usage:
    replay_stripe_webhook.py succeeded --pi <payment_intent_id> \
        --amount <pence> --invoice <invoice_uuid> --tenant <tenant_uuid>
    replay_stripe_webhook.py refunded --pi <payment_intent_id>

Env: API (default http://localhost:8100), STRIPE_WEBHOOK_SECRET (required).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
import uuid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["succeeded", "refunded"])
    parser.add_argument("--pi", required=True, help="payment intent id")
    parser.add_argument("--amount", type=int, default=0, help="amount in pence")
    parser.add_argument("--invoice", default="", help="invoice uuid")
    parser.add_argument("--tenant", default="", help="tenant uuid")
    args = parser.parse_args()

    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        sys.exit("STRIPE_WEBHOOK_SECRET must be set (same value the API was started with)")
    api = os.environ.get("API", "http://localhost:8100")

    if args.kind == "succeeded":
        event_type = "payment_intent.succeeded"
        obj = {
            "id": args.pi,
            "object": "payment_intent",
            "amount": args.amount,
            "amount_received": args.amount,
            "currency": "gbp",
            "status": "succeeded",
            "metadata": {"invoice_id": args.invoice, "tenant_id": args.tenant},
        }
    else:
        event_type = "charge.refunded"
        obj = {
            "id": f"ch_evidence_{uuid.uuid4().hex[:12]}",
            "object": "charge",
            "amount": args.amount,
            "amount_refunded": args.amount,
            "currency": "gbp",
            "payment_intent": args.pi,
            "status": "succeeded",
        }

    event = {
        "id": f"evt_evidence_{uuid.uuid4().hex[:16]}",
        "object": "event",
        "api_version": "2025-08-27.basil",
        "created": int(time.time()),
        "type": event_type,
        "livemode": False,
        "data": {"object": obj},
    }
    body = json.dumps(event, separators=(",", ":")).encode()

    timestamp = str(int(time.time()))
    signed = f"{timestamp}.".encode() + body
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()

    request = urllib.request.Request(
        f"{api}/webhooks/stripe",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": f"t={timestamp},v1={signature}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print(f"HTTP {response.status} {response.read().decode()}")
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code} {exc.read().decode()}")


if __name__ == "__main__":
    main()
