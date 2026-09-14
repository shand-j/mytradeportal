"""Tests for customer-email failure alerts (send-time + Resend bounce webhook).

Covers the founder rule "if a customer email bounces or fails, the
electrician is notified and directed to phone instead":

* send-time transport failures (Resend AND SMTP) page tenant staff once per
  (tenant, contact, day) with the purpose, error class and phone directive;
* ``POST /webhooks/resend`` verifies the Svix signature (503 unconfigured,
  401 bad signature), matches ``mtp_*`` tags back to a contact and raises
  the same deduped alert; untagged/unknown events are acked as no-ops;
* customer-facing sends carry the ``mtp_tenant``/``mtp_contact`` Resend tags;
* staff-facing sends (plain ``send_event_email``) never raise alerts, so a
  failing staff alert email cannot loop into another alert.

Sessions follow the stripe-webhook test pattern: handlers work on their own
engine sessions, so fixtures are seeded (and cleaned up) with committed
sessions rather than the per-test rollback client.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from app.database import engine
from app.email import send_customer_email, send_event_email
from app.main import app
from app.models import Contact, EmailFailureAlert, Notification, Tenant, User
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.security import get_password_hash
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_SECRET = "whsec_" + base64.b64encode(b"resend-webhook-test-secret").decode()
_CUSTOMER_EMAIL = "harriet@example.com"
_STAFF_EMAIL = "sam@alertelectrical.co.uk"
_PHONE = "07123 456789"


# ---------------------------------------------------------------------------
# Transport fakes
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)  # type: ignore[arg-type]


class _FakeResendClient:
    """Responds 422 for recipients in ``fail_recipients``, 200 otherwise."""

    def __init__(self, fail_recipients: set[str]) -> None:
        self._fail = fail_recipients
        self.posts: list[dict[str, Any]] = []

    async def __aenter__(self) -> "_FakeResendClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _FakeResponse:
        self.posts.append(json)
        recipient = (json.get("to") or [""])[0]
        if recipient in self._fail:
            return _FakeResponse(422, {"statusCode": 422, "message": "mailbox unavailable"})
        return _FakeResponse(200, {"id": "re_test_msg"})


def _patch_resend(monkeypatch: pytest.MonkeyPatch, fail_recipients: set[str]) -> _FakeResendClient:
    from app import email as email_module

    monkeypatch.setattr(email_module.settings, "resend_api_key", "re_test_key")
    fake = _FakeResendClient(fail_recipients)
    monkeypatch.setattr(email_module.httpx, "AsyncClient", lambda **_: fake)
    return fake


def _patch_failing_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import email as email_module

    monkeypatch.setattr(email_module.settings, "resend_api_key", "")

    async def failing_send(message: Any, **_: Any) -> None:
        raise email_module.aiosmtplib.SMTPException("mailbox unavailable")

    monkeypatch.setattr(email_module.aiosmtplib, "send", failing_send)


# ---------------------------------------------------------------------------
# DB helpers (committed sessions, same pattern as the stripe webhook tests)
# ---------------------------------------------------------------------------


async def _seed(*, phone: str | None = _PHONE, with_staff: bool = False) -> dict[str, Any]:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        tenant = Tenant(slug=f"efa-{uuid4().hex[:8]}", name="Alert Electrical")
        session.add(tenant)
        await session.flush()
        await set_tenant_in_session(session, tenant.id)
        contact = Contact(
            tenant_id=tenant.id,
            name="Harriet Homeowner",
            email=_CUSTOMER_EMAIL,
            phone=phone,
        )
        session.add(contact)
        if with_staff:
            session.add(
                User(
                    tenant_id=tenant.id,
                    email=_STAFF_EMAIL,
                    full_name="Sam Spark",
                    role="admin",
                    password_hash=get_password_hash("staff-password"),
                    is_active=True,
                )
            )
        # Flush so the Python-side id defaults are assigned before capture.
        await session.flush()
        ids = {"tenant_id": tenant.id, "contact_id": contact.id}
        await session.commit()
        return ids


async def _cleanup(tenant_id: UUID) -> None:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        await session.execute(
            delete(EmailFailureAlert).where(EmailFailureAlert.tenant_id == tenant_id)
        )
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await session.commit()


async def _failure_notifications(tenant_id: UUID) -> list[Notification]:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        rows = (
            (
                await session.execute(
                    select(Notification).where(
                        Notification.tenant_id == tenant_id,
                        Notification.type == "email_failed",
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            session.expunge(row)
        return list(rows)


async def _alert_row_count(tenant_id: UUID) -> int:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        return int(
            await session.scalar(
                select(func.count())
                .select_from(EmailFailureAlert)
                .where(EmailFailureAlert.tenant_id == tenant_id)
            )
            or 0
        )


async def _send_quote_email(tenant_id: UUID, contact_id: UUID) -> bool:
    async with AsyncSession(engine) as session:
        delivered = await send_customer_email(
            session,
            tenant_id=tenant_id,
            contact_id=contact_id,
            purpose="quote",
            to_email=_CUSTOMER_EMAIL,
            subject="Your quote is ready",
            html_body="<p>Your quote</p>",
            text_body="Your quote",
            event="quote_sent",
            template="quote_ready",
            from_name="Alert Electrical",
        )
        await session.commit()
        return delivered


# ---------------------------------------------------------------------------
# Send-time failure alerts
# ---------------------------------------------------------------------------


async def test_resend_failure_alerts_staff_once_with_phone_directive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed(with_staff=True)
    fake = _patch_resend(monkeypatch, fail_recipients={_CUSTOMER_EMAIL})
    try:
        delivered = await _send_quote_email(ids["tenant_id"], ids["contact_id"])
        assert delivered is False

        notifications = await _failure_notifications(ids["tenant_id"])
        assert len(notifications) == 1
        alert = notifications[0]
        assert alert.title == "Email to Harriet Homeowner wasn't delivered"
        # Purpose, error class (not the raw payload) and the phone directive.
        assert "quote email" in alert.body
        assert "HTTPStatusError" in alert.body
        assert f"Contact them by phone instead: {_PHONE}" in alert.body
        assert alert.link == f"/customers/{ids['contact_id']}"
        assert await _alert_row_count(ids["tenant_id"]) == 1

        # The same content went out as a staff email (platform no-reply).
        staff_posts = [p for p in fake.posts if p["to"] == [_STAFF_EMAIL]]
        assert len(staff_posts) == 1
        assert staff_posts[0]["subject"] == alert.title
        assert _PHONE in staff_posts[0]["html"]

        # A repeat failure the same day is deduped: no second notification,
        # no second staff email.
        delivered = await _send_quote_email(ids["tenant_id"], ids["contact_id"])
        assert delivered is False
        assert len(await _failure_notifications(ids["tenant_id"])) == 1
        assert await _alert_row_count(ids["tenant_id"]) == 1
        assert len([p for p in fake.posts if p["to"] == [_STAFF_EMAIL]]) == 1
    finally:
        await _cleanup(ids["tenant_id"])


async def test_smtp_failure_alerts_staff(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = await _seed()
    _patch_failing_smtp(monkeypatch)
    try:
        delivered = await _send_quote_email(ids["tenant_id"], ids["contact_id"])
        assert delivered is False
        notifications = await _failure_notifications(ids["tenant_id"])
        assert len(notifications) == 1
        assert "SMTPException" in notifications[0].body
        assert f"Contact them by phone instead: {_PHONE}" in notifications[0].body
        assert await _alert_row_count(ids["tenant_id"]) == 1
    finally:
        await _cleanup(ids["tenant_id"])


async def test_contact_without_phone_gets_reach_another_way_directive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed(phone=None)
    _patch_resend(monkeypatch, fail_recipients={_CUSTOMER_EMAIL})
    try:
        delivered = await _send_quote_email(ids["tenant_id"], ids["contact_id"])
        assert delivered is False
        notifications = await _failure_notifications(ids["tenant_id"])
        assert len(notifications) == 1
        assert "Reach them another way — their email isn't working." in notifications[0].body
        assert "phone" not in notifications[0].body.split("failed")[1]
    finally:
        await _cleanup(ids["tenant_id"])


async def test_customer_send_carries_mtp_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = await _seed()
    fake = _patch_resend(monkeypatch, fail_recipients=set())
    try:
        delivered = await _send_quote_email(ids["tenant_id"], ids["contact_id"])
        assert delivered is True
        tags = {tag["name"]: tag["value"] for tag in fake.posts[0]["tags"]}
        assert tags["mtp_tenant"] == str(ids["tenant_id"])
        assert tags["mtp_contact"] == str(ids["contact_id"])
        # A successful send raises no alert.
        assert await _failure_notifications(ids["tenant_id"]) == []
        assert await _alert_row_count(ids["tenant_id"]) == 0
    finally:
        await _cleanup(ids["tenant_id"])


async def test_staff_facing_send_failure_does_not_raise_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plain ``send_event_email`` has no failure hook: staff-facing mail that
    fails must not create alert rows (no alert loops)."""
    ids = await _seed()
    _patch_resend(monkeypatch, fail_recipients={_STAFF_EMAIL})
    try:
        delivered = await send_event_email(
            to_email=_STAFF_EMAIL,
            subject="Ops alert",
            html_body="<p>ops</p>",
            event="ai_ops_alert",
            template="ai_ops_alert",
            context={"tenant_id": str(ids["tenant_id"])},
        )
        assert delivered is False
        assert await _failure_notifications(ids["tenant_id"]) == []
        assert await _alert_row_count(ids["tenant_id"]) == 0
    finally:
        await _cleanup(ids["tenant_id"])


# ---------------------------------------------------------------------------
# Resend bounce webhook
# ---------------------------------------------------------------------------


def _svix_headers(body: bytes, secret: str, msg_id: str = "msg_test_1") -> dict[str, str]:
    """Sign the body exactly the way Svix does: HMAC-SHA256 (base64) of
    ``"{svix-id}.{svix-timestamp}.{body}"`` keyed by the whsec_ secret."""
    timestamp = str(int(time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{msg_id}.{timestamp}.".encode() + body
    signature = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
    }


def _bounce_event(*, tenant_id: UUID, contact_id: UUID, event_type: str = "email.bounced") -> bytes:
    return json.dumps(
        {
            "type": event_type,
            "created_at": "2026-09-14T10:00:00.000Z",
            "data": {
                "email_id": f"em_{uuid4().hex[:12]}",
                "from": "quotes@mytradeportal.co.uk",
                "to": [_CUSTOMER_EMAIL],
                "subject": "Your quote is ready",
                "tags": {"mtp_tenant": str(tenant_id), "mtp_contact": str(contact_id)},
            },
        }
    ).encode()


async def _post_resend(body: bytes, headers: dict[str, str]) -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/resend",
            content=body,
            headers={**headers, "Content-Type": "application/json"},
        )


async def test_webhook_bounce_with_valid_signature_alerts_staff_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed()
    monkeypatch.setattr("app.config.RESEND_WEBHOOK_SECRET", _SECRET)
    body = _bounce_event(tenant_id=ids["tenant_id"], contact_id=ids["contact_id"])
    try:
        response = await _post_resend(body, _svix_headers(body, _SECRET))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        notifications = await _failure_notifications(ids["tenant_id"])
        assert len(notifications) == 1
        assert notifications[0].title == "Email to Harriet Homeowner wasn't delivered"
        assert "bounce" in notifications[0].body
        assert f"Contact them by phone instead: {_PHONE}" in notifications[0].body
        assert await _alert_row_count(ids["tenant_id"]) == 1

        # A replayed bounce the same day is deduped.
        replay = _bounce_event(tenant_id=ids["tenant_id"], contact_id=ids["contact_id"])
        response = await _post_resend(replay, _svix_headers(replay, _SECRET, "msg_test_2"))
        assert response.status_code == 200
        assert len(await _failure_notifications(ids["tenant_id"])) == 1
        assert await _alert_row_count(ids["tenant_id"]) == 1
    finally:
        await _cleanup(ids["tenant_id"])


async def test_webhook_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.RESEND_WEBHOOK_SECRET", _SECRET)
    body = b'{"type":"email.bounced","data":{"to":["x@example.com"],"tags":{}}}'
    response = await _post_resend(
        body,
        {
            "svix-id": "msg_forged",
            "svix-timestamp": str(int(time.time())),
            "svix-signature": "v1,AAAA",
        },
    )
    assert response.status_code == 401


async def test_webhook_503_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.RESEND_WEBHOOK_SECRET", "")
    body = b'{"type":"email.bounced","data":{}}'
    response = await _post_resend(body, _svix_headers(body, _SECRET))
    assert response.status_code == 503
    assert response.json()["detail"] == "resend_webhook_not_configured"


async def test_webhook_untagged_and_unknown_events_are_acked_noops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed()
    monkeypatch.setattr("app.config.RESEND_WEBHOOK_SECRET", _SECRET)
    try:
        # email.failed without mtp_ tags (platform mail / pre-tagging sends).
        untagged = json.dumps(
            {
                "type": "email.failed",
                "created_at": "2026-09-14T10:00:00.000Z",
                "data": {"email_id": "em_untagged", "to": ["someone@example.com"]},
            }
        ).encode()
        response = await _post_resend(untagged, _svix_headers(untagged, _SECRET, "msg_untagged"))
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

        # An event type we do not handle at all.
        delivered = json.dumps(
            {
                "type": "email.delivered",
                "created_at": "2026-09-14T10:00:00.000Z",
                "data": {"email_id": "em_ok", "to": [_CUSTOMER_EMAIL]},
            }
        ).encode()
        response = await _post_resend(delivered, _svix_headers(delivered, _SECRET, "msg_delivered"))
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

        assert await _failure_notifications(ids["tenant_id"]) == []
        assert await _alert_row_count(ids["tenant_id"]) == 0
    finally:
        await _cleanup(ids["tenant_id"])
