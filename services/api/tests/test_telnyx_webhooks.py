"""Tests for the Telnyx webhook (delivery receipts + STOP opt-outs).

Covers ``POST /webhooks/telnyx``:

* Ed25519 signature verification — 503 when ``TELNYX_PUBLIC_KEY`` is
  unconfigured, 401 on a bad signature, a stale timestamp or missing
  headers, 200 when correctly signed;
* delivery receipts (``message.sent`` / ``message.finalized``) — matched to
  the appointment-reminder row via ``payload.telnyx_message_id``, status
  transitions recorded on the row (terminal outcomes never downgraded by a
  late interim receipt), and a permanent failure on a customer reminder
  paging staff once per (tenant, contact, day) — mirroring the email bounce
  alert;
* inbound CTIA keywords — STOP (case-insensitive) sets
  ``reminder_preferences.sms_opt_out`` on the contact we texted, the
  appointment-reminder sweep then skips SMS and falls back to email, and
  START clears the flag again;
* event-id idempotency via the ``processed_webhooks`` ledger — a replayed
  event is acked as a duplicate without re-running side effects.

Sessions follow the resend/stripe webhook test pattern: handlers work on
their own engine sessions, so fixtures are seeded (and cleaned up) with
committed sessions rather than the per-test rollback client.
"""

import base64
import json
import time
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.config import settings
from app.database import engine
from app.main import app
from app.models import (
    Appointment,
    Contact,
    EmailFailureAlert,
    Notification,
    ProcessedWebhook,
    Reminder,
    Tenant,
)
from app.rls import bypass_rls_in_session, set_tenant_in_session
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_PRIVATE_KEY = Ed25519PrivateKey.generate()
_PUBLIC_KEY_B64 = base64.b64encode(
    _PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode()

_CUSTOMER_PHONE = "07700900123"
_CUSTOMER_PHONE_E164 = "+447700900123"
_MESSAGE_ID = f"msg_{uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Signing + payload builders
# ---------------------------------------------------------------------------


def _telnyx_headers(body: bytes, *, timestamp: str | None = None) -> dict[str, str]:
    """Sign the body exactly the way Telnyx does: Ed25519 (base64) of
    ``"{timestamp}|{body}"`` verifiable against the account public key."""
    ts = timestamp or str(int(time.time()))
    signature = base64.b64encode(_PRIVATE_KEY.sign(f"{ts}|".encode() + body)).decode()
    return {"telnyx-timestamp": ts, "telnyx-signature-ed25519": signature}


def _receipt_event(
    *,
    message_id: str,
    to_status: str,
    event_type: str = "message.finalized",
    event_id: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> bytes:
    payload: dict[str, Any] = {
        "id": message_id,
        "direction": "outbound",
        "type": "SMS",
        "from": {"phone_number": "+447700900000"},
        "to": [{"phone_number": _CUSTOMER_PHONE_E164, "status": to_status}],
        "text": "Reminder: your appointment",
        "errors": errors or [],
    }
    return json.dumps(
        {
            "data": {
                "record_type": "event",
                "event_type": event_type,
                "id": event_id or str(uuid4()),
                "occurred_at": "2026-09-20T10:00:00.000+00:00",
                "payload": payload,
            },
            "meta": {"attempt": 1, "delivered_to": "https://api.example.com/webhooks/telnyx"},
        }
    ).encode()


def _inbound_event(*, from_number: str, text: str, event_id: str | None = None) -> bytes:
    return json.dumps(
        {
            "data": {
                "record_type": "event",
                "event_type": "message.received",
                "id": event_id or str(uuid4()),
                "occurred_at": "2026-09-20T10:00:00.000+00:00",
                "payload": {
                    "id": str(uuid4()),
                    "direction": "inbound",
                    "type": "SMS",
                    "from": {"phone_number": from_number},
                    "to": [{"phone_number": "+447700900000", "status": "webhook_delivered"}],
                    "text": text,
                },
            },
            "meta": {"attempt": 1, "delivered_to": "https://api.example.com/webhooks/telnyx"},
        }
    ).encode()


async def _post_telnyx(body: bytes, headers: dict[str, str]) -> Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/telnyx",
            content=body,
            headers={**headers, "Content-Type": "application/json"},
        )


@pytest.fixture
def telnyx_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telnyx_public_key", _PUBLIC_KEY_B64)


# ---------------------------------------------------------------------------
# DB helpers (committed sessions, same pattern as the resend webhook tests)
# ---------------------------------------------------------------------------


async def _seed(
    *,
    role: str = "customer",
    message_id: str = _MESSAGE_ID,
    window_hours: str = "24",
    phone: str | None = _CUSTOMER_PHONE,
    email: str | None = "harriet@example.com",
) -> dict[str, Any]:
    """Tenant + contact + appointment + one SMS appointment-reminder row."""
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        tenant = Tenant(slug=f"tw-{uuid4().hex[:8]}", name="Alert Electrical")
        session.add(tenant)
        await session.flush()
        await set_tenant_in_session(session, tenant.id)
        contact = Contact(
            tenant_id=tenant.id,
            name="Harriet Homeowner",
            email=email,
            phone=phone,
        )
        session.add(contact)
        await session.flush()
        start = datetime.utcnow() + timedelta(hours=24)
        appointment = Appointment(
            tenant_id=tenant.id,
            contact_id=contact.id,
            title="Consumer unit replacement",
            start_at=start,
            end_at=start + timedelta(hours=2),
            status="confirmed",
        )
        session.add(appointment)
        await session.flush()
        payload: dict[str, Any] = {
            "appointment_id": str(appointment.id),
            "window_hours": window_hours,
            "role": role,
            "to": _CUSTOMER_PHONE_E164,
        }
        if message_id:
            payload["telnyx_message_id"] = message_id
        session.add(
            Reminder(
                tenant_id=tenant.id,
                entity_type="appointment",
                entity_id=appointment.id,
                channel="sms",
                sequence=1,
                payload=payload,
            )
        )
        ids = {
            "tenant_id": tenant.id,
            "contact_id": contact.id,
            "appointment_id": appointment.id,
        }
        await session.commit()
        return ids


async def _cleanup(tenant_id: UUID) -> None:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        await session.execute(
            delete(EmailFailureAlert).where(EmailFailureAlert.tenant_id == tenant_id)
        )
        await session.execute(delete(Notification).where(Notification.tenant_id == tenant_id))
        await session.execute(delete(Reminder).where(Reminder.tenant_id == tenant_id))
        await session.execute(delete(ProcessedWebhook).where(ProcessedWebhook.provider == "telnyx"))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await session.commit()


async def _reminder_row(appointment_id: UUID) -> Reminder:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        row = await session.scalar(
            select(Reminder).where(
                Reminder.entity_type == "appointment",
                Reminder.entity_id == appointment_id,
            )
        )
        assert row is not None
        session.expunge(row)
        return row


async def _contact(contact_id: UUID) -> Contact:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        contact = await session.get(Contact, contact_id)
        assert contact is not None
        session.expunge(contact)
        return contact


async def _failure_notifications(tenant_id: UUID) -> list[Notification]:
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        rows = (
            (
                await session.execute(
                    select(Notification).where(
                        Notification.tenant_id == tenant_id,
                        Notification.type == "sms_failed",
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


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


async def test_webhook_503_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telnyx_public_key", "")
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    response = await _post_telnyx(body, _telnyx_headers(body))
    assert response.status_code == 503
    assert response.json()["detail"] == "telnyx_webhook_not_configured"


async def test_webhook_rejects_bad_signature(telnyx_public_key: None) -> None:
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    response = await _post_telnyx(
        body,
        {
            "telnyx-timestamp": str(int(time.time())),
            "telnyx-signature-ed25519": base64.b64encode(b"forged").decode(),
        },
    )
    assert response.status_code == 401


async def test_webhook_rejects_stale_timestamp(telnyx_public_key: None) -> None:
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    stale = str(int(time.time()) - 3600)
    response = await _post_telnyx(body, _telnyx_headers(body, timestamp=stale))
    assert response.status_code == 401


async def test_webhook_rejects_missing_signature_headers(telnyx_public_key: None) -> None:
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    response = await _post_telnyx(body, {})
    assert response.status_code == 401


async def test_webhook_unknown_event_type_is_acked_noop(telnyx_public_key: None) -> None:
    body = json.dumps(
        {
            "data": {
                "record_type": "event",
                "event_type": "message.replaced",
                "id": str(uuid4()),
                "payload": {},
            }
        }
    ).encode()
    response = await _post_telnyx(body, _telnyx_headers(body))
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Delivery receipts
# ---------------------------------------------------------------------------


async def test_delivered_receipt_records_status_transition(telnyx_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="delivered")
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        reminder = await _reminder_row(ids["appointment_id"])
        assert reminder.payload["delivery_status"] == "delivered"
        assert reminder.payload["delivery_events"] == [
            {
                "status": "delivered",
                "event_type": "message.finalized",
                "at": "2026-09-20T10:00:00.000+00:00",
            }
        ]
        # A successful delivery raises no staff alert.
        assert await _failure_notifications(ids["tenant_id"]) == []
        assert await _alert_row_count(ids["tenant_id"]) == 0
    finally:
        await _cleanup(ids["tenant_id"])


async def test_failed_receipt_pages_staff_once_with_error_detail(
    telnyx_public_key: None,
) -> None:
    ids = await _seed()
    errors = [{"code": "40300", "title": "Destination number unreachable"}]
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="delivery_failed", errors=errors)
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        reminder = await _reminder_row(ids["appointment_id"])
        assert reminder.payload["delivery_status"] == "delivery_failed"

        notifications = await _failure_notifications(ids["tenant_id"])
        assert len(notifications) == 1
        alert = notifications[0]
        assert alert.title == "SMS to Harriet Homeowner wasn't delivered"
        assert "appointment reminder" in alert.body
        assert "delivery failure" in alert.body
        assert "40300 Destination number unreachable" in alert.body
        assert "Reach them by email instead: harriet@example.com" in alert.body
        assert alert.link == f"/customers/{ids['contact_id']}"
        assert await _alert_row_count(ids["tenant_id"]) == 1

        # A second failure receipt for the same contact the same day (fresh
        # event id, same message — e.g. the failover URL also delivering) is
        # deduped: no second staff page.
        replay = _receipt_event(message_id=_MESSAGE_ID, to_status="delivery_failed", errors=errors)
        response = await _post_telnyx(replay, _telnyx_headers(replay))
        assert response.status_code == 200
        assert len(await _failure_notifications(ids["tenant_id"])) == 1
        assert await _alert_row_count(ids["tenant_id"]) == 1
    finally:
        await _cleanup(ids["tenant_id"])


async def test_failed_receipt_on_staff_role_records_without_alert(
    telnyx_public_key: None,
) -> None:
    ids = await _seed(role="staff")
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="sending_failed")
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        reminder = await _reminder_row(ids["appointment_id"])
        assert reminder.payload["delivery_status"] == "sending_failed"
        assert await _failure_notifications(ids["tenant_id"]) == []
        assert await _alert_row_count(ids["tenant_id"]) == 0
    finally:
        await _cleanup(ids["tenant_id"])


async def test_late_interim_receipt_does_not_downgrade_terminal_status(
    telnyx_public_key: None,
) -> None:
    ids = await _seed()
    try:
        delivered = _receipt_event(message_id=_MESSAGE_ID, to_status="delivered")
        response = await _post_telnyx(delivered, _telnyx_headers(delivered))
        assert response.status_code == 200

        # Out-of-order delivery: message.sent arrives after the final state.
        sent = _receipt_event(message_id=_MESSAGE_ID, to_status="sent", event_type="message.sent")
        response = await _post_telnyx(sent, _telnyx_headers(sent))
        assert response.status_code == 200

        reminder = await _reminder_row(ids["appointment_id"])
        assert reminder.payload["delivery_status"] == "delivered"
        assert [event["status"] for event in reminder.payload["delivery_events"]] == [
            "delivered",
            "sent",
        ]
    finally:
        await _cleanup(ids["tenant_id"])


async def test_receipt_for_unknown_message_is_acked_noop(telnyx_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _receipt_event(message_id=f"msg_{uuid4().hex[:12]}", to_status="delivered")
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        reminder = await _reminder_row(ids["appointment_id"])
        assert "delivery_status" not in reminder.payload
    finally:
        await _cleanup(ids["tenant_id"])


async def test_replayed_event_id_is_duplicate_without_side_effects(
    telnyx_public_key: None,
) -> None:
    ids = await _seed()
    event_id = str(uuid4())
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="delivered", event_id=event_id)
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "duplicate"

        reminder = await _reminder_row(ids["appointment_id"])
        assert len(reminder.payload["delivery_events"]) == 1
    finally:
        await _cleanup(ids["tenant_id"])


# ---------------------------------------------------------------------------
# STOP / START opt-out
# ---------------------------------------------------------------------------


async def test_stop_reply_opts_contact_out_case_insensitive(telnyx_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text=" stop ")
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        contact = await _contact(ids["contact_id"])
        assert (contact.reminder_preferences or {}).get("sms_opt_out") is True
    finally:
        await _cleanup(ids["tenant_id"])


async def test_start_reply_re_enables_sms(telnyx_public_key: None) -> None:
    ids = await _seed()
    try:
        stop = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
        response = await _post_telnyx(stop, _telnyx_headers(stop))
        assert response.status_code == 200
        contact = await _contact(ids["contact_id"])
        assert (contact.reminder_preferences or {}).get("sms_opt_out") is True

        start = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="START")
        response = await _post_telnyx(start, _telnyx_headers(start))
        assert response.status_code == 200
        contact = await _contact(ids["contact_id"])
        assert not (contact.reminder_preferences or {}).get("sms_opt_out")
    finally:
        await _cleanup(ids["tenant_id"])


async def test_non_keyword_inbound_is_acked_noop(telnyx_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="Thanks!")
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        contact = await _contact(ids["contact_id"])
        assert not (contact.reminder_preferences or {}).get("sms_opt_out")
    finally:
        await _cleanup(ids["tenant_id"])


async def test_stop_for_number_we_never_texted_is_noop(telnyx_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _inbound_event(from_number="+447700999999", text="STOP")
        response = await _post_telnyx(body, _telnyx_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        contact = await _contact(ids["contact_id"])
        assert not (contact.reminder_preferences or {}).get("sms_opt_out")
    finally:
        await _cleanup(ids["tenant_id"])


async def test_opted_out_contact_gets_email_fallback_not_sms(
    monkeypatch: pytest.MonkeyPatch, telnyx_public_key: None
) -> None:
    """STOP suppresses the future SMS and the sweep degrades to email."""
    from app.appointment_reminders import process_appointment_reminders

    # The prior SMS row uses the 2h window so the 24h customer reminder is
    # still unfired when the sweep runs (dedupe is window+role keyed).
    ids = await _seed(window_hours="2")
    sms_sender = AsyncMock(return_value=f"msg_{uuid4().hex[:12]}")
    monkeypatch.setattr("app.appointment_reminders.send_sms", sms_sender)
    monkeypatch.setattr(settings, "telnyx_api_key", "KEYTEST")
    monkeypatch.setattr(settings, "telnyx_from_number", "+447700900000")
    monkeypatch.setattr(settings, "telnyx_messaging_profile_id", "")
    emails: list[dict[str, Any]] = []

    async def fake_send_customer_email(db: Any, **kwargs: Any) -> bool:
        emails.append(kwargs)
        return True

    monkeypatch.setattr("app.appointment_reminders.send_customer_email", fake_send_customer_email)
    try:
        stop = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
        response = await _post_telnyx(stop, _telnyx_headers(stop))
        assert response.status_code == 200

        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            tenant = await session.get(Tenant, ids["tenant_id"])
            assert tenant is not None
            await set_tenant_in_session(session, tenant.id)
            counts = await process_appointment_reminders(session, tenant, datetime.utcnow())
            await session.commit()

        # No SMS attempted for the opted-out customer; the 24h reminder went
        # out by email instead.
        assert counts["customer_sms"] == 0
        assert counts["email_fallbacks"] == 1
        assert not [
            call
            for call in sms_sender.call_args_list
            if call.kwargs.get("to_phone") == _CUSTOMER_PHONE
        ]
        assert len(emails) == 1
        assert emails[0]["to_email"] == "harriet@example.com"

        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            channels = (
                (
                    await session.execute(
                        select(Reminder.channel).where(Reminder.entity_id == ids["appointment_id"])
                    )
                )
                .scalars()
                .all()
            )
        assert set(channels) == {"sms", "email"}
    finally:
        await _cleanup(ids["tenant_id"])
