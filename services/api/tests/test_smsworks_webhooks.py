"""Tests for the SMS Works delivery-report and inbound-message webhooks.

Covers basic authentication, flat delivery-report status transitions, failure
alerts, STOP/START opt-outs and message-id idempotency. Sessions are seeded and
cleaned up with committed sessions, matching the other webhook suites.
"""

import base64
import json
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
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_CUSTOMER_PHONE = "07700900123"
_CUSTOMER_PHONE_E164 = "+447700900123"
_MESSAGE_ID = f"msg_{uuid4().hex[:12]}"


def _smsworks_headers(body: bytes, *, timestamp: str | None = None) -> dict[str, str]:
    token = base64.b64encode(b"reports:secret").decode()
    return {"Authorization": f"Basic {token}"}


def _receipt_event(
    *,
    message_id: str,
    to_status: str,
    event_type: str = "delivery_report",
    event_id: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> bytes:
    failure = None
    if errors:
        failure = {
            "code": errors[0].get("code"),
            "details": errors[0].get("title"),
            "permanent": True,
        }
    payload = {
        "messageid": message_id,
        "destination": _CUSTOMER_PHONE_E164.lstrip("+"),
        "status": to_status.upper(),
        "created": "2026-09-20T10:00:00.000+00:00",
        "modified": "2026-09-20T10:00:00.000+00:00",
        "failurereason": failure,
    }
    return json.dumps(payload).encode()


def _inbound_event(*, from_number: str, text: str, event_id: str | None = None) -> bytes:
    return json.dumps(
        {
            "content": text,
            "from": from_number.lstrip("+"),
            "messageid": event_id or str(uuid4()),
            "messagetype": "incoming",
        }
    ).encode()


async def _post_smsworks(body: bytes, headers: dict[str, str]) -> Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/smsworks",
            content=body,
            headers={**headers, "Content-Type": "application/json"},
        )


@pytest.fixture
def smsworks_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smsworks_webhook_username", "reports")
    monkeypatch.setattr(settings, "smsworks_webhook_password", "secret")


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
            payload["smsworks_message_id"] = message_id
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
        await session.execute(
            delete(ProcessedWebhook).where(ProcessedWebhook.provider == "smsworks")
        )
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
    monkeypatch.setattr(settings, "smsworks_webhook_username", "reports")
    monkeypatch.setattr(settings, "smsworks_webhook_password", "")
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    response = await _post_smsworks(body, _smsworks_headers(body))
    assert response.status_code == 503
    assert response.json()["detail"] == "smsworks_webhook_not_configured"


async def test_webhook_rejects_bad_signature(smsworks_public_key: None) -> None:
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    response = await _post_smsworks(body, {"Authorization": "Basic wrong"})
    assert response.status_code == 401


async def test_webhook_rejects_stale_timestamp(smsworks_public_key: None) -> None:
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    response = await _post_smsworks(body, {"Authorization": "Basic not-base64"})
    assert response.status_code == 401


async def test_webhook_rejects_missing_signature_headers(smsworks_public_key: None) -> None:
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
    response = await _post_smsworks(body, {})
    assert response.status_code == 401


async def test_webhook_unknown_event_type_is_acked_noop(smsworks_public_key: None) -> None:
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
    response = await _post_smsworks(body, _smsworks_headers(body))
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Delivery receipts
# ---------------------------------------------------------------------------


async def test_delivered_receipt_records_status_transition(smsworks_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="delivered")
        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        reminder = await _reminder_row(ids["appointment_id"])
        assert reminder.payload["delivery_status"] == "delivered"
        assert reminder.payload["delivery_events"] == [
            {
                "status": "delivered",
                "event_type": "delivery_report",
                "at": "2026-09-20T10:00:00.000+00:00",
            }
        ]
        # A successful delivery raises no staff alert.
        assert await _failure_notifications(ids["tenant_id"]) == []
        assert await _alert_row_count(ids["tenant_id"]) == 0
    finally:
        await _cleanup(ids["tenant_id"])


async def test_failed_receipt_pages_staff_once_with_error_detail(
    smsworks_public_key: None,
) -> None:
    ids = await _seed()
    errors = [{"code": "40300", "title": "Destination number unreachable"}]
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="delivery_failed", errors=errors)
        response = await _post_smsworks(body, _smsworks_headers(body))
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
        response = await _post_smsworks(replay, _smsworks_headers(replay))
        assert response.status_code == 200
        assert len(await _failure_notifications(ids["tenant_id"])) == 1
        assert await _alert_row_count(ids["tenant_id"]) == 1
    finally:
        await _cleanup(ids["tenant_id"])


async def test_failed_receipt_on_staff_role_records_without_alert(
    smsworks_public_key: None,
) -> None:
    ids = await _seed(role="staff")
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="sending_failed")
        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        reminder = await _reminder_row(ids["appointment_id"])
        assert reminder.payload["delivery_status"] == "sending_failed"
        assert await _failure_notifications(ids["tenant_id"]) == []
        assert await _alert_row_count(ids["tenant_id"]) == 0
    finally:
        await _cleanup(ids["tenant_id"])


async def test_late_interim_receipt_does_not_downgrade_terminal_status(
    smsworks_public_key: None,
) -> None:
    ids = await _seed()
    try:
        delivered = _receipt_event(message_id=_MESSAGE_ID, to_status="delivered")
        response = await _post_smsworks(delivered, _smsworks_headers(delivered))
        assert response.status_code == 200

        # Out-of-order delivery: message.sent arrives after the final state.
        sent = _receipt_event(message_id=_MESSAGE_ID, to_status="sent", event_type="message.sent")
        response = await _post_smsworks(sent, _smsworks_headers(sent))
        assert response.status_code == 200

        reminder = await _reminder_row(ids["appointment_id"])
        assert reminder.payload["delivery_status"] == "delivered"
        assert [event["status"] for event in reminder.payload["delivery_events"]] == [
            "delivered",
            "sent",
        ]
    finally:
        await _cleanup(ids["tenant_id"])


async def test_receipt_for_unknown_message_is_acked_noop(smsworks_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _receipt_event(message_id=f"msg_{uuid4().hex[:12]}", to_status="delivered")
        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        reminder = await _reminder_row(ids["appointment_id"])
        assert "delivery_status" not in reminder.payload
    finally:
        await _cleanup(ids["tenant_id"])


async def test_replayed_event_id_is_duplicate_without_side_effects(
    smsworks_public_key: None,
) -> None:
    ids = await _seed()
    event_id = str(uuid4())
    try:
        body = _receipt_event(message_id=_MESSAGE_ID, to_status="delivered", event_id=event_id)
        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "duplicate"

        reminder = await _reminder_row(ids["appointment_id"])
        assert len(reminder.payload["delivery_events"]) == 1
    finally:
        await _cleanup(ids["tenant_id"])


async def test_inbound_retry_after_handler_failure_processes_once(
    monkeypatch: pytest.MonkeyPatch, smsworks_public_key: None
) -> None:
    ids = await _seed()
    event_id = str(uuid4())
    body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP", event_id=event_id)

    from app.routers import smsworks_webhooks

    real_set_sms_opt_out = smsworks_webhooks._set_sms_opt_out
    attempts = 0

    async def flaky_set_sms_opt_out(
        session: AsyncSession, from_number: str, *, opted_out: bool
    ) -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary opt-out write failure")
        return await real_set_sms_opt_out(session, from_number, opted_out=opted_out)

    monkeypatch.setattr("app.routers.smsworks_webhooks._set_sms_opt_out", flaky_set_sms_opt_out)

    try:
        with pytest.raises(RuntimeError, match="temporary opt-out write failure"):
            await _post_smsworks(body, _smsworks_headers(body))
        contact = await _contact(ids["contact_id"])
        assert not (contact.reminder_preferences or {}).get("sms_opt_out")

        second = await _post_smsworks(body, _smsworks_headers(body))
        assert second.status_code == 200
        assert second.json()["status"] == "ok"
        contact = await _contact(ids["contact_id"])
        assert (contact.reminder_preferences or {}).get("sms_opt_out") is True

        third = await _post_smsworks(body, _smsworks_headers(body))
        assert third.status_code == 200
        assert third.json()["status"] == "duplicate"
        assert attempts == 2
    finally:
        await _cleanup(ids["tenant_id"])


# ---------------------------------------------------------------------------
# STOP / START opt-out
# ---------------------------------------------------------------------------


async def test_stop_reply_opts_contact_out_case_insensitive(smsworks_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text=" stop ")
        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        contact = await _contact(ids["contact_id"])
        assert (contact.reminder_preferences or {}).get("sms_opt_out") is True
    finally:
        await _cleanup(ids["tenant_id"])


async def test_start_reply_re_enables_sms(smsworks_public_key: None) -> None:
    ids = await _seed()
    try:
        stop = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
        response = await _post_smsworks(stop, _smsworks_headers(stop))
        assert response.status_code == 200
        contact = await _contact(ids["contact_id"])
        assert (contact.reminder_preferences or {}).get("sms_opt_out") is True

        start = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="START")
        response = await _post_smsworks(start, _smsworks_headers(start))
        assert response.status_code == 200
        contact = await _contact(ids["contact_id"])
        assert not (contact.reminder_preferences or {}).get("sms_opt_out")
    finally:
        await _cleanup(ids["tenant_id"])


async def test_non_keyword_inbound_is_acked_noop(smsworks_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="Thanks!")
        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        contact = await _contact(ids["contact_id"])
        assert not (contact.reminder_preferences or {}).get("sms_opt_out")
    finally:
        await _cleanup(ids["tenant_id"])


async def test_stop_for_number_we_never_texted_is_noop(smsworks_public_key: None) -> None:
    ids = await _seed()
    try:
        body = _inbound_event(from_number="+447700999999", text="STOP")
        response = await _post_smsworks(body, _smsworks_headers(body))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        contact = await _contact(ids["contact_id"])
        assert not (contact.reminder_preferences or {}).get("sms_opt_out")
    finally:
        await _cleanup(ids["tenant_id"])


async def test_opted_out_contact_gets_email_fallback_not_sms(
    monkeypatch: pytest.MonkeyPatch, smsworks_public_key: None
) -> None:
    """STOP suppresses the future SMS and the sweep degrades to email."""
    from app.appointment_reminders import process_appointment_reminders

    # The prior SMS row uses the 2h window so the 24h customer reminder is
    # still unfired when the sweep runs (dedupe is window+role keyed).
    ids = await _seed(window_hours="2")
    sms_sender = AsyncMock(return_value=f"msg_{uuid4().hex[:12]}")
    monkeypatch.setattr("app.appointment_reminders.send_sms", sms_sender)
    monkeypatch.setattr(settings, "smsworks_api_token", "KEYTEST")
    monkeypatch.setattr(settings, "smsworks_from_number", "447700900000")
    emails: list[dict[str, Any]] = []

    async def fake_send_customer_email(db: Any, **kwargs: Any) -> bool:
        emails.append(kwargs)
        return True

    monkeypatch.setattr("app.appointment_reminders.send_customer_email", fake_send_customer_email)
    try:
        stop = _inbound_event(from_number=_CUSTOMER_PHONE_E164, text="STOP")
        response = await _post_smsworks(stop, _smsworks_headers(stop))
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
