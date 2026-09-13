"""Evidence-capture API instance: the real FastAPI app with Stripe stubbed.

Runs the UNMODIFIED application code (``app.main:app``) against the local
docker-compose Postgres, with two seams mocked so no external service is
touched:

* ``app.stripe_client`` network functions (PaymentIntent create/retrieve,
  refund, account retrieve) are replaced with in-memory stubs. The public
  invoice endpoint only checks ``stripe_client.is_configured()`` (an env var)
  and then calls these functions, so the real destination-charge code path in
  ``app.routers.public_docs`` executes end to end and issues a genuine
  ``/pay/{token}?pi=...&cs=...`` URL — with a stub PaymentIntent id.
* Webhook signature verification is NOT stubbed: ``STRIPE_WEBHOOK_SECRET`` is
  set to a test value and ``scripts/replay_stripe_webhook.py`` computes a real
  Stripe HMAC-SHA256 signature, so ``stripe.Webhook.construct_event`` runs its
  genuine verification path.

Email is NOT stubbed either: RESEND_API_KEY is blanked so ``app.email`` falls
back to SMTP against the local Mailpit container (http://localhost:8025).
Supabase is blanked so auth uses the local bcrypt path. The LLM is never
called — quotes are seeded via the API by ``lifecycle.sh``.

Required env is exported by ``start-stack.sh`` (see README.md). Run from
``services/api`` with the repo venv:

    ../../.venv/bin/python ../../docs/evidence/wave-a/scripts/stubbed_api.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `app` importable regardless of the caller's cwd (the script lives in
# docs/evidence/wave-a/scripts/, the app in services/api/).
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "services" / "api"))

for var in ("DATABASE_URL", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
    if not os.environ.get(var):
        sys.exit(f"{var} must be set — launch via scripts/start-stack.sh")

# Patch BEFORE app.main is imported: routers bind stripe_client attributes at
# import time (``from app.stripe_client import ...`` / ``from app import
# stripe_client``), and every patched attribute here is looked up on the
# module at call time, so module-attribute patching covers all call sites.
from app import stripe_client  # noqa: E402

STUB_PAYMENT_INTENT_ID = "pi_evidence_stub_0001"
STUB_REFUND_ID = "re_evidence_stub_0001"


async def _fake_create_payment_intent(
    *,
    amount_pence: int,
    currency: str,
    connected_account_id: str,
    invoice_id: str,
    tenant_id: str,
) -> dict[str, str]:
    """Stand-in for stripe.PaymentIntent.create (destination charge)."""
    return {
        "id": STUB_PAYMENT_INTENT_ID,
        "client_secret": f"{STUB_PAYMENT_INTENT_ID}_secret_evidencestub",
    }


async def _fake_retrieve_payment_intent(payment_intent_id: str) -> dict[str, object]:
    """Stand-in for stripe.PaymentIntent.retrieve.

    Reports a non-open status so the public-docs endpoint always (re)mints
    the stub intent above instead of reusing a stale one.
    """
    return {
        "id": payment_intent_id,
        "client_secret": f"{payment_intent_id}_secret_evidencestub",
        "status": "canceled",
        "amount": 0,
    }


async def _fake_create_refund(payment_intent_id: str) -> dict[str, str]:
    """Stand-in for stripe.Refund.create (full refund of the stub intent)."""
    return {"id": STUB_REFUND_ID, "status": "succeeded"}


async def _fake_retrieve_account(account_id: str) -> dict[str, object]:
    """Stand-in for stripe.Account.retrieve (capability mirror)."""
    return {
        "id": account_id,
        "details_submitted": True,
        "charges_enabled": True,
        "payouts_enabled": True,
    }


stripe_client.create_payment_intent = _fake_create_payment_intent  # type: ignore[assignment]
stripe_client.retrieve_payment_intent = _fake_retrieve_payment_intent  # type: ignore[assignment]
stripe_client.create_refund = _fake_create_refund  # type: ignore[assignment]
stripe_client.retrieve_account = _fake_retrieve_account  # type: ignore[assignment]


def _construct_event_compat(body: bytes, signature_header: str) -> dict:
    """App-bug shim: ``app.stripe_client.construct_event`` ends with
    ``dict(event)``, which raises ``TypeError`` on stripe-python >= 15
    (``StripeObject`` no longer subclasses ``dict``). Verification itself is
    left entirely to the real ``stripe.Webhook.construct_event`` — this
    wrapper only adapts the return shape with ``.to_dict()``.
    """
    import stripe

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    stripe.api_version = stripe_client.STRIPE_API_VERSION
    event = stripe.Webhook.construct_event(
        body, signature_header, os.environ["STRIPE_WEBHOOK_SECRET"]
    )
    return dict(event.to_dict())


stripe_client.construct_event = _construct_event_compat  # type: ignore[assignment]

import uvicorn  # noqa: E402
from app.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="warning")
