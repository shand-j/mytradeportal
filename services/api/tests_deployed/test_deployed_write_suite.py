"""Deployed write suite: stateful end-to-end coverage of the CI safety net.

Where the read-only smoke suite (``test_deployed_api.py``) asserts that public
surfaces fail closed, these tests exercise full journeys against a live
deployment under throwaway tenants created with ``TEST_SETUP_TOKEN``:

- subscription paywall (Paddle webhook -> tenant-status -> 402 middleware)
- Stripe Connect onboarding mirror + forged card-payment webhook chain
  (public invoice -> PaymentIntent -> paid -> refunded) with Mailpit email
  assertions (payment received + review CTA)
- no-card trial + extension after 3 sent AI-drafted quotes
- Resend bounce webhook -> staff alert (in-app + email)
- customer magic-link exchange + account claim
- staff data-export shape

Never runs against production: every test owns a fresh tenant created via the
setup token on staging / PR environments, and skips without the token.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import pytest

from . import webhook_signing as sign
from .conftest import (
    PADDLE_PRICE_ID_PRO,
    PADDLE_WEBHOOK_SECRET,
    RESEND_WEBHOOK_SECRET,
    STRIPE_WEBHOOK_SECRET,
    SeededTenant,
    requires_base_url,
    requires_paddle_secret,
    requires_resend_secret,
    requires_setup_token,
    requires_stripe_secret,
)
from .mailpit_client import mailpit_configured, wait_for_email

if TYPE_CHECKING:
    import httpx

pytestmark = [
    pytest.mark.deployed,
    pytest.mark.deployed_write,
    requires_base_url,
    requires_setup_token,
]

requires_mailpit = pytest.mark.skipif(not mailpit_configured(), reason="Mailpit is not configured")


def _staff(
    api: httpx.Client, tenant: SeededTenant, method: str, path: str, **kwargs: Any
) -> httpx.Response:
    return api.request(method, path, headers=tenant.headers, **kwargs)


def _create_contact(api: httpx.Client, tenant: SeededTenant, email: str) -> dict[str, Any]:
    resp = _staff(
        api,
        tenant,
        "POST",
        "/contacts",
        json={
            "name": f"WS Contact {uuid.uuid4().hex[:6]}",
            "email": email,
            "phone": "07700 900000",
            "postcode": "M20 1AA",
            "address": "1 WriteSuite Road, Manchester",
        },
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _create_quote(
    api: httpx.Client, tenant: SeededTenant, contact_id: str, title: str
) -> dict[str, Any]:
    resp = _staff(
        api,
        tenant,
        "POST",
        "/quotes",
        json={
            "contact_id": contact_id,
            "title": title,
            "line_items": [
                {"description": "Consumer unit replacement", "quantity": 1, "unit_price": "400.00"},
                {
                    "description": "Circuit testing (AI drafted)",
                    "quantity": 2,
                    "unit_price": "75.00",
                    "ai_generated": True,
                },
            ],
            "vat_rate": "0.20",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    body: dict[str, Any] = resp.json()
    return body


def _tenant_status(api: httpx.Client, tenant: SeededTenant) -> dict[str, Any]:
    resp = _staff(api, tenant, "GET", "/auth/tenant-status")
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


# ---------------------------------------------------------------------------
# Tenant bootstrap + trial
# ---------------------------------------------------------------------------


class TestTenantBootstrap:
    def test_new_tenant_is_trialing_with_active_access(
        self, api: httpx.Client, make_tenant: Any
    ) -> None:
        tenant: SeededTenant = make_tenant("mtp-boot")
        status = _tenant_status(api, tenant)
        assert status["access"] == "active"
        assert status["subscription_status"] == "trialing"
        assert status["trial_ends_at"] is not None
        trial_end = datetime.fromisoformat(status["trial_ends_at"].replace("Z", "+00:00"))
        days = (trial_end - datetime.now(tz=trial_end.tzinfo)).days
        assert 12 <= days <= 15, f"expected a 14-day trial, got {days} days"


# ---------------------------------------------------------------------------
# Paddle subscription webhooks -> paywall
# ---------------------------------------------------------------------------


def _post_paddle(api: httpx.Client, payload: dict[str, Any]) -> httpx.Response:
    body = sign.encode_event(payload)
    return api.post(
        "/webhooks/paddle",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sign.paddle_signature(body, PADDLE_WEBHOOK_SECRET),
        },
    )


@requires_paddle_secret
class TestPaddleWebhooks:
    def test_bad_signature_is_rejected(self, api: httpx.Client) -> None:
        resp = api.post(
            "/webhooks/paddle",
            json={"event_id": "evt_bad", "event_type": "subscription.updated", "data": {}},
            headers={"Paddle-Signature": "ts=1;h1=bad"},
        )
        assert resp.status_code == 401

    def test_cancel_blocks_access_and_middleware_then_reactivate(
        self, api: httpx.Client, make_tenant: Any
    ) -> None:
        tenant: SeededTenant = make_tenant("mtp-paddle")

        cancel = _post_paddle(
            api,
            sign.paddle_subscription_event(
                event_type="subscription.canceled", tenant_id=tenant.id, status="canceled"
            ),
        )
        assert cancel.status_code == 200, cancel.text
        assert _tenant_status(api, tenant)["access"] == "payment_required"
        # The paywall middleware blocks staff surfaces but leaves the status
        # endpoint (and other exempt paths) reachable so the app can render
        # the paywall itself.
        assert _staff(api, tenant, "GET", "/quotes").status_code == 402
        assert _staff(api, tenant, "GET", "/invoices").status_code == 402

        activate = _post_paddle(
            api,
            sign.paddle_subscription_event(
                event_type="subscription.activated",
                tenant_id=tenant.id,
                status="active",
                price_id=PADDLE_PRICE_ID_PRO or None,
            ),
        )
        assert activate.status_code == 200, activate.text
        assert _tenant_status(api, tenant)["access"] == "active"
        assert _staff(api, tenant, "GET", "/quotes").status_code == 200
        if PADDLE_PRICE_ID_PRO:
            sub = _staff(api, tenant, "GET", "/billing/subscription")
            assert sub.status_code == 200, sub.text
            assert sub.json()["plan_key"] == "pro"

    def test_duplicate_event_id_replays_as_duplicate(
        self, api: httpx.Client, make_tenant: Any
    ) -> None:
        tenant: SeededTenant = make_tenant("mtp-paddle-dup")
        payload = sign.paddle_subscription_event(
            event_type="subscription.activated",
            tenant_id=tenant.id,
            status="active",
            event_id=f"evt_dup_{uuid.uuid4().hex[:12]}",
        )
        first = _post_paddle(api, payload)
        assert first.status_code == 200 and first.json() == {"status": "ok"}
        second = _post_paddle(api, payload)
        assert second.status_code == 200 and second.json() == {"status": "duplicate"}


# ---------------------------------------------------------------------------
# Stripe Connect + card payment webhook chain
# ---------------------------------------------------------------------------


def _post_stripe(api: httpx.Client, payload: dict[str, Any]) -> httpx.Response:
    body = sign.encode_event(payload)
    return api.post(
        "/webhooks/stripe",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": sign.stripe_signature(body, STRIPE_WEBHOOK_SECRET),
        },
    )


@requires_stripe_secret
@requires_mailpit
class TestStripeConnectAndCardPayment:
    def test_connect_onboard_pay_refund_chain(self, api: httpx.Client, make_tenant: Any) -> None:
        tenant: SeededTenant = make_tenant("mtp-pay")
        customer_email = f"pay-{uuid.uuid4().hex[:8]}@example.com"

        # 1. Connect onboarding URL mints a linked (not yet chargeable) account.
        connect = _staff(api, tenant, "POST", "/payments/connect", json={})
        assert connect.status_code == 200, connect.text
        assert connect.json()["onboarding_url"].startswith("https://connect.stripe.")
        status = _staff(api, tenant, "GET", "/payments/status").json()
        assert status["connected"] is True
        assert status["charges_enabled"] is False
        account_id = status["stripe_account_id"]
        assert account_id

        # 2. Stripe mirrors capability flags via account.updated.
        mirror = _post_stripe(
            api,
            sign.stripe_account_updated(
                account_id=account_id,
                details_submitted=True,
                charges_enabled=True,
                payouts_enabled=True,
            ),
        )
        assert mirror.status_code == 200, mirror.text
        status = _staff(api, tenant, "GET", "/payments/status").json()
        assert status["charges_enabled"] is True
        assert status["onboarding_complete"] is True

        # 3. Review URL gates the post-payment review CTA.
        patch = _staff(
            api,
            tenant,
            "PATCH",
            "/tenants/me",
            json={"review_url": "https://maps.google.com/ws-review"},
        )
        assert patch.status_code == 200, patch.text

        # 4. Quote -> invoice -> send -> emailed public doc link.
        contact = _create_contact(api, tenant, customer_email)
        quote = _create_quote(api, tenant, contact["id"], "WS card-pay quote")
        invoice_resp = _staff(
            api,
            tenant,
            "POST",
            "/invoices",
            json={"contact_id": contact["id"], "quote_id": quote["id"]},
        )
        assert invoice_resp.status_code in (200, 201), invoice_resp.text
        invoice = invoice_resp.json()
        expected_total_pence = int(float(invoice["total"]) * 100)

        send = _staff(api, tenant, "POST", f"/invoices/{invoice['id']}/send")
        assert send.status_code == 200, send.text
        sent_mail = wait_for_email(customer_email, subject_includes="Invoice")
        match = re.search(r"/invoice/([A-Za-z0-9_\-]+)", sent_mail.html + sent_mail.text)
        assert match, "no public invoice link in the sent email"
        doc_token = match.group(1)

        # 5. The public doc creates (or reuses) a real PaymentIntent because the
        #    Connect account is chargeable.
        public = api.get(f"/public/invoice/{doc_token}")
        assert public.status_code == 200, public.text
        public_body = public.json()
        assert public_body["status"] == "sent"
        payment_url = public_body.get("payment_url")
        assert payment_url, "expected a Stripe payment_url for a chargeable invoice"
        intent_id = parse_qs(urlparse(payment_url).query)["pi"][0]
        assert intent_id

        # 6. Forged payment_intent.succeed marks the invoice paid end-to-end.
        paid_event = sign.stripe_payment_intent_succeeded(
            invoice_id=invoice["id"],
            tenant_id=tenant.id,
            amount_pence=expected_total_pence,
        )
        webhook = _post_stripe(api, paid_event)
        assert webhook.status_code == 200, webhook.text
        fetched = _staff(api, tenant, "GET", f"/invoices/{invoice['id']}").json()
        assert fetched["status"] == "paid"
        assert fetched["paid_via"] == "stripe"
        assert fetched["stripe_payment_intent_id"] == intent_id

        # Staff get an in-app notification linking back to the invoice.
        notifications = _staff(api, tenant, "GET", "/notifications").json()
        paid_notice = next((n for n in notifications if n.get("type") == "invoice_paid"), None)
        assert paid_notice is not None
        assert str(invoice["id"]) in (paid_notice.get("link") or "")

        # The customer gets a payment-received email carrying the review CTA.
        payment_mail = wait_for_email(customer_email, subject_includes="Payment received")
        assert "ws-review" in (payment_mail.html + payment_mail.text)

        # 7. Replays are deduped by event id.
        replay = _post_stripe(api, paid_event)
        assert replay.status_code == 200 and replay.json() == {"status": "duplicate"}

        # 8. A refund webhook moves the invoice to refunded.
        refund = _post_stripe(api, sign.stripe_charge_refunded(payment_intent_id=intent_id))
        assert refund.status_code == 200, refund.text
        assert (
            _staff(api, tenant, "GET", f"/invoices/{invoice['id']}").json()["status"] == "refunded"
        )


# ---------------------------------------------------------------------------
# Trial extension after 3 sent AI-drafted quotes
# ---------------------------------------------------------------------------


class TestTrialExtension:
    def test_three_sent_ai_quotes_extend_trial_once(
        self, api: httpx.Client, make_tenant: Any
    ) -> None:
        tenant: SeededTenant = make_tenant("mtp-trial")
        initial_end = datetime.fromisoformat(
            _tenant_status(api, tenant)["trial_ends_at"].replace("Z", "+00:00")
        )
        contact = _create_contact(api, tenant, f"trial-{uuid.uuid4().hex[:8]}@example.com")

        for i in range(3):
            quote = _create_quote(api, tenant, contact["id"], f"WS trial quote {i}")
            assert any(line["ai_generated"] for line in quote["line_items"])
            send = _staff(api, tenant, "POST", f"/quotes/{quote['id']}/send")
            assert send.status_code == 200, send.text

        # Contract (app/trial.py): the trial is extended TO now + 30 days at
        # the moment the 3rd AI-drafted quote is sent — not +30d on top of the
        # original 14-day end.
        sub = _staff(api, tenant, "GET", "/billing/subscription")
        assert sub.status_code == 200, sub.text
        extended_end = datetime.fromisoformat(sub.json()["trial_ends_at"].replace("Z", "+00:00"))
        assert extended_end > initial_end
        days_from_now = (extended_end - datetime.now(tz=extended_end.tzinfo)).days
        assert 28 <= days_from_now <= 31, (
            f"expected trial to end ~30d from now, got {days_from_now}d"
        )

        # The extension fires exactly once: a 4th sent AI quote must not move
        # trial_ends_at again.
        extra = _create_quote(api, tenant, contact["id"], "WS trial quote 4")
        assert _staff(api, tenant, "POST", f"/quotes/{extra['id']}/send").status_code == 200
        after = datetime.fromisoformat(
            _staff(api, tenant, "GET", "/billing/subscription")
            .json()["trial_ends_at"]
            .replace("Z", "+00:00")
        )
        assert after == extended_end


# ---------------------------------------------------------------------------
# Resend bounce -> staff alert
# ---------------------------------------------------------------------------


def _post_resend(api: httpx.Client, payload: dict[str, Any]) -> httpx.Response:
    body = sign.encode_event(payload)
    return api.post(
        "/webhooks/resend",
        content=body,
        headers={
            "Content-Type": "application/json",
            **sign.resend_svix_headers(body, RESEND_WEBHOOK_SECRET),
        },
    )


@requires_resend_secret
@requires_mailpit
class TestResendBounce:
    def test_bounce_alerts_staff_in_app_and_by_email(
        self, api: httpx.Client, make_tenant: Any
    ) -> None:
        tenant: SeededTenant = make_tenant("mtp-bounce")
        contact = _create_contact(api, tenant, f"bounce-{uuid.uuid4().hex[:8]}@example.com")

        resp = _post_resend(
            api,
            sign.resend_bounce(to=contact["email"], tenant_id=tenant.id, contact_id=contact["id"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"status": "ok"}

        notifications = _staff(api, tenant, "GET", "/notifications").json()
        alert = next((n for n in notifications if n.get("type") == "email_failed"), None)
        assert alert is not None
        assert contact["email"] in (alert.get("body") or "") or contact["email"] in (
            alert.get("title") or ""
        )

        staff_mail = wait_for_email(tenant.admin_email, subject_includes="wasn't delivered")
        assert contact["email"] in (staff_mail.text + staff_mail.html)

    def test_untagged_event_is_ignored(self, api: httpx.Client) -> None:
        resp = _post_resend(api, {"type": "email.bounced", "data": {"to": ["x@example.com"]}})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}


# ---------------------------------------------------------------------------
# Customer magic link + account claim
# ---------------------------------------------------------------------------


@requires_mailpit
class TestCustomerMagicLinks:
    def test_magic_request_exchange_and_claim(self, api: httpx.Client, make_tenant: Any) -> None:
        tenant: SeededTenant = make_tenant("mtp-magic")
        customer_email = f"magic-{uuid.uuid4().hex[:8]}@example.com"
        register = api.post(
            "/customer/register",
            json={
                "slug": tenant.slug,
                "email": customer_email,
                "password": "initial-pass-123",
                "full_name": "WS Magic Customer",
            },
        )
        assert register.status_code in (200, 201), register.text

        # The portal endpoints resolve the tenant from the Host subdomain, which
        # only works when served from a tenant subdomain — the api's bare public
        # domain falls back to the default tenant and silently emails nothing
        # (anti-enumeration). The X-Tenant-Slug header pins the tenant instead
        # (same mechanism the web portal uses when served from the marketing
        # origin).
        portal_headers = {"X-Tenant-Slug": tenant.slug}
        request = api.post(
            "/customer/auth/magic/request", json={"email": customer_email}, headers=portal_headers
        )
        assert request.status_code == 202, request.text

        mail = wait_for_email(customer_email, subject_includes="sign-in link")
        match = re.search(r"[?&]token=([A-Za-z0-9_\-]+)", mail.html + mail.text)
        assert match, "no magic token in the emailed link"
        token = match.group(1)

        exchange = api.post("/customer/auth/magic", json={"token": token})
        assert exchange.status_code == 200, exchange.text
        assert exchange.json()["customer"]["email"] == customer_email
        assert exchange.json()["access_token"]

        # Claiming with the same token sets a new password (single-use).
        new_password = "claimed-pass-456"
        claim = api.post("/customer/auth/claim", json={"token": token, "password": new_password})
        assert claim.status_code == 200, claim.text
        assert claim.json()["access_token"]

        login = api.post(
            "/customer/login",
            json={"slug": tenant.slug, "email": customer_email, "password": new_password},
        )
        assert login.status_code == 200, login.text

        reuse = api.post("/customer/auth/magic", json={"token": token})
        assert reuse.status_code == 401


# ---------------------------------------------------------------------------
# Staff data export
# ---------------------------------------------------------------------------


class TestDataExport:
    def test_export_my_data_returns_full_json_snapshot(
        self, api: httpx.Client, make_tenant: Any
    ) -> None:
        tenant: SeededTenant = make_tenant("mtp-export")
        contact = _create_contact(api, tenant, f"export-{uuid.uuid4().hex[:8]}@example.com")
        _create_quote(api, tenant, contact["id"], "WS export quote")

        resp = _staff(api, tenant, "GET", "/export/my-data")
        assert resp.status_code == 200, resp.text
        assert "attachment" in resp.headers.get("content-disposition", "")
        payload = json.loads(resp.text)
        assert payload["tenant"]["slug"] == tenant.slug
        assert len(payload["quotes"]) == 1
        assert payload["quotes"][0]["title"] == "WS export quote"
