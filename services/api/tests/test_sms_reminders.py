"""Tests for SMS appointment reminders (Telnyx) and their fair-use guardrail.

Covers :mod:`app.sms` phone normalisation and the scheduler pass in
:mod:`app.appointment_reminders`: window firing (24h/2h), per-window
dedupe, customer+staff recipients, email fallback when SMS is unavailable,
the tenant kill-switch, and the monthly fair-use degrade-to-email behaviour
(mirroring the AI-token fair-use pattern).
"""

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from app.config import settings
from app.models import AiAlertState, Appointment, Contact, Reminder, Tenant, User
from app.plans import current_period
from app.scheduler import run_reminder_tick
from app.sms import normalize_phone, normalize_sender, send_sms, sms_segment_limit
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class _EmailRecorder:
    """Stand-in for app.appointment_reminders.send_customer_email."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, db: Any = None, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return True


@pytest_asyncio.fixture
async def email_recorder(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[_EmailRecorder, None]:
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.appointment_reminders.send_customer_email", recorder)
    yield recorder


@pytest.fixture
def sms_sender(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Fake Telnyx dispatch: every send succeeds with a message id."""
    sender = AsyncMock(return_value="msg_test_1")
    monkeypatch.setattr("app.appointment_reminders.send_sms", sender)
    return sender


@pytest.fixture
def telnyx_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telnyx_api_key", "KEYTEST")
    monkeypatch.setattr(settings, "telnyx_from_number", "+447700900000")
    monkeypatch.setattr(settings, "telnyx_messaging_profile_id", "")


@pytest.fixture
def recorded_alerts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    alerts: list[tuple[str, str]] = []

    async def fake_send_alert(subject: str, text: str) -> dict[str, bool]:
        alerts.append((subject, text))
        return {"email": True}

    monkeypatch.setattr("app.appointment_reminders.send_alert", fake_send_alert)
    return alerts


def _tenant_id(admin_client: AsyncClient) -> UUID:
    return UUID(admin_client.headers["X-Tenant-ID"])


async def _make_contact(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    email: str | None = "amy@example.com",
    phone: str | None = "07700900123",
) -> Contact:
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email=email, phone=phone)
    db.add(contact)
    await db.flush()
    return contact


async def _make_staff(db: AsyncSession, tenant_id: UUID, *, phone: str | None) -> User:
    user = User(
        tenant_id=tenant_id,
        email=f"sparky-{uuid4().hex[:6]}@test.local",
        full_name="Sam Sparky",
        role="engineer",
        phone=phone,
    )
    db.add(user)
    await db.flush()
    return user


def _make_appointment(
    tenant_id: UUID,
    contact_id: UUID,
    *,
    start_at: datetime,
    status: str = "confirmed",
    assigned_user_id: UUID | None = None,
    title: str = "Consumer unit replacement",
    address: str | None = "12 Acacia Avenue",
) -> Appointment:
    return Appointment(
        tenant_id=tenant_id,
        contact_id=contact_id,
        title=title,
        start_at=start_at,
        end_at=start_at + timedelta(hours=2),
        status=status,
        assigned_user_id=assigned_user_id,
        address=address,
    )


async def _appointment_reminders(db: AsyncSession, appointment_id: UUID) -> list[Reminder]:
    return list(
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.entity_type == "appointment",
                    Reminder.entity_id == appointment_id,
                )
                .order_by(Reminder.sequence)
            )
        )
        .scalars()
        .all()
    )


# --- Phone normalisation ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+447700900123", "+447700900123"),
        ("07700900123", "+447700900123"),
        ("44 7700 900123", "+447700900123"),
        ("00447700900123", "+447700900123"),
        ("(07700) 900-123", "+447700900123"),
        ("+44 7700 900123", "+447700900123"),
        ("12345", None),
        ("abc", None),
        ("", None),
        (None, None),
        ("+44abc", None),
        ("07000900123199", None),  # 14 digits, not a UK shape
    ],
)
def test_normalize_phone(raw: str | None, expected: str | None) -> None:
    assert normalize_phone(raw) == expected


# --- Sender identity + single-segment budget ------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Sparks & Sons", "SPARKSSONS"),
        ("abc electrical", "ABCELECTRIC"),  # 13 letters → truncated to 11
        ("Joe's Electrical Services!", "JOESELECTRI"),
        ("12345", None),  # all digits would be read as a phone number
        ("07700 900111", None),  # digit-shaped even after stripping
        ("!!!", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_sender(name: str | None, expected: str | None) -> None:
    assert normalize_sender(name) == expected


@pytest.mark.parametrize(
    ("text", "limit"),
    [
        ("Plain ASCII reminder.", 160),
        ("£50 fixed fee", 160),  # £ is in the GSM-7 extension table
        ("Price — today", 70),  # em dash is not GSM-7
        ("Hello 👋", 70),  # emoji forces UCS-2
    ],
)
def test_sms_segment_limit(text: str, limit: int) -> None:
    assert sms_segment_limit(text) == limit


def _mock_telnyx_transport(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture send_sms HTTP requests with a 200 MockTransport; return payloads."""
    payloads: list[dict[str, Any]] = []
    real_async_client = httpx.AsyncClient  # patched module attr would recurse

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {"id": "msg_mock_1"}})

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.sms.httpx.AsyncClient", client_factory)
    return payloads


@pytest.mark.asyncio
async def test_send_sms_prefers_alphanumeric_tenant_sender(
    monkeypatch: pytest.MonkeyPatch, telnyx_configured: None
) -> None:
    payloads = _mock_telnyx_transport(monkeypatch)

    message_id = await send_sms(to_phone="07700900123", text="Hi", tenant_name="Sparks & Sons")

    assert message_id == "msg_mock_1"
    assert payloads[0]["from"] == "SPARKSSONS"
    assert payloads[0]["to"] == "+447700900123"


@pytest.mark.asyncio
async def test_send_sms_falls_back_to_number_for_digit_tenant_name(
    monkeypatch: pytest.MonkeyPatch, telnyx_configured: None
) -> None:
    payloads = _mock_telnyx_transport(monkeypatch)

    await send_sms(to_phone="07700900123", text="Hi", tenant_name="12345")

    assert payloads[0]["from"] == "+447700900000"  # TELNYX_FROM_NUMBER


# --- Window firing + dedupe ---------------------------------------------------


@pytest.mark.asyncio
async def test_24h_window_sends_customer_and_staff_sms(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    staff = await _make_staff(db, tenant_id, phone="07700900999")
    appointment = _make_appointment(
        tenant_id,
        contact.id,
        start_at=datetime.utcnow() + timedelta(hours=24),
        assigned_user_id=staff.id,
    )
    db.add(appointment)
    await db.commit()

    now = datetime.utcnow()
    summary = await run_reminder_tick(db, now)

    assert summary["appointment_customer_sms"] == 1
    assert summary["appointment_staff_sms"] == 1
    assert summary["appointment_email_fallbacks"] == 0

    reminders = await _appointment_reminders(db, appointment.id)
    assert {(r.channel, r.payload["window_hours"], r.payload["role"]) for r in reminders} == {
        ("sms", "24", "customer"),
        ("sms", "24", "staff"),
    }
    assert all(
        r.payload["to"] == "+447700900999" for r in reminders if r.payload["role"] == "staff"
    )
    customer_send = next(
        c for c in sms_sender.call_args_list if c.kwargs["to_phone"] == "07700900123"
    )
    assert "Consumer unit replacement" in customer_send.kwargs["text"]
    # "Test Electrical" normalises to the TESTELECTR alphanumeric sender ID,
    # which cannot receive replies — the STOP line must be omitted.
    assert customer_send.kwargs["tenant_name"] == "Test Electrical"
    assert "Reply STOP to opt out." not in customer_send.kwargs["text"]

    # Second sweep 30 minutes later: same window still open, nothing re-fires.
    summary2 = await run_reminder_tick(db, now + timedelta(minutes=30))
    assert summary2["appointment_customer_sms"] == 0
    assert summary2["appointment_staff_sms"] == 0
    assert len(await _appointment_reminders(db, appointment.id)) == 2


@pytest.mark.asyncio
async def test_2h_window_fires_its_own_rows(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    appointment = _make_appointment(
        tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(appointment)
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    # Only the 2h window is due (24h is still 22h out, beyond the pad).
    assert summary["appointment_customer_sms"] == 1
    reminders = await _appointment_reminders(db, appointment.id)
    assert [(r.payload["window_hours"], r.payload["role"]) for r in reminders] == [
        ("2", "customer")
    ]


@pytest.mark.asyncio
async def test_far_future_and_cancelled_appointments_fire_nothing(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    far = _make_appointment(tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(days=5))
    cancelled = _make_appointment(
        tenant_id,
        contact.id,
        start_at=datetime.utcnow() + timedelta(hours=2),
        status="cancelled",
    )
    db.add_all([far, cancelled])
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 0
    assert summary["appointment_staff_sms"] == 0
    assert summary["appointment_email_fallbacks"] == 0
    sms_sender.assert_not_awaited()
    assert (await db.execute(select(Reminder))).scalars().all() == []


@pytest.mark.asyncio
async def test_disabled_by_tenant_setting(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.settings = {**tenant.settings, "appointment_reminders_enabled": False}
    contact = await _make_contact(db, tenant_id)
    db.add(
        _make_appointment(tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(hours=2))
    )
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 0
    sms_sender.assert_not_awaited()


# --- Fallbacks ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_usable_phone_falls_back_to_one_email_per_window(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id, phone="not-a-number")
    appointment = _make_appointment(
        tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(appointment)
    await db.commit()

    now = datetime.utcnow()
    summary = await run_reminder_tick(db, now)

    assert summary["appointment_customer_sms"] == 0
    assert summary["appointment_email_fallbacks"] == 1
    sms_sender.assert_not_awaited()  # un-normalisable number never hits Telnyx
    assert len(email_recorder.calls) == 1
    call = email_recorder.calls[0]
    assert call["event"] == "appointment_reminder"
    assert call["to_email"] == "amy@example.com"
    assert "Consumer unit replacement" in call["html_body"]

    reminders = await _appointment_reminders(db, appointment.id)
    assert [(r.channel, r.payload["role"]) for r in reminders] == [("email", "customer")]

    # Repeated ticks inside the window do not re-send the fallback email.
    summary2 = await run_reminder_tick(db, now + timedelta(minutes=30))
    assert summary2["appointment_email_fallbacks"] == 0
    assert len(email_recorder.calls) == 1
    assert len(await _appointment_reminders(db, appointment.id)) == 1


@pytest.mark.asyncio
async def test_unconfigured_sms_degrades_to_email(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Telnyx credentials → the customer still gets the email reminder."""
    monkeypatch.setattr(settings, "telnyx_api_key", "")
    monkeypatch.setattr(settings, "telnyx_from_number", "")
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    appointment = _make_appointment(
        tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(hours=24)
    )
    db.add(appointment)
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 0
    assert summary["appointment_email_fallbacks"] == 1
    reminders = await _appointment_reminders(db, appointment.id)
    assert [(r.channel, r.payload["window_hours"], r.payload["role"]) for r in reminders] == [
        ("email", "24", "customer")
    ]


@pytest.mark.asyncio
async def test_staff_without_phone_gets_push_only(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    staff = await _make_staff(db, tenant_id, phone=None)
    appointment = _make_appointment(
        tenant_id,
        contact.id,
        start_at=datetime.utcnow() + timedelta(hours=2),
        assigned_user_id=staff.id,
    )
    db.add(appointment)
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 1
    assert summary["appointment_staff_sms"] == 0
    reminders = await _appointment_reminders(db, appointment.id)
    assert {(r.channel, r.payload["role"]) for r in reminders} == {
        ("sms", "customer"),
        ("push", "staff"),
    }
    # Exactly one SMS attempt (the customer) — staff push is free, not SMS.
    assert len(sms_sender.call_args_list) == 1

    notifications = (
        (
            await db.execute(
                select(Reminder).where(
                    Reminder.entity_type == "appointment",
                    Reminder.entity_id == appointment.id,
                    Reminder.channel == "push",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notifications) == 1


# --- STOP opt-out + one-segment bodies --------------------------------------------


@pytest.mark.asyncio
async def test_stop_line_present_when_sender_is_a_number(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    """A digit-only business name falls back to the numeric sender, where
    replies (and STOP) work — the opt-out line must be included."""
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.name = "12345678901"  # normalises to None → numeric sender
    contact = await _make_contact(db, tenant_id)
    db.add(
        _make_appointment(tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(hours=2))
    )
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 1
    text = sms_sender.call_args_list[0].kwargs["text"]
    assert "Reply STOP to opt out." in text


@pytest.mark.asyncio
async def test_long_title_and_address_still_fit_one_segment(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    """An over-long combination drops the address/greeting and never exceeds
    the 160-char GSM-7 single-segment budget."""
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    appointment = _make_appointment(
        tenant_id,
        contact.id,
        start_at=datetime.utcnow() + timedelta(hours=2),
        title=(
            "Full consumer unit replacement with surge protection, EV charger "
            "isolator and garden lighting circuit upgrade works"
        ),
        address="123 Very Long Road Name, Some Village, Near A Town, AB12 3CD",
    )
    db.add(appointment)
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 1
    text = sms_sender.call_args_list[0].kwargs["text"]
    assert len(text) <= 160
    assert sms_segment_limit(text) == 160  # still GSM-7, one segment


@pytest.mark.asyncio
async def test_non_gsm7_character_drops_limit_to_70(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    """A non-GSM-7 character (em dash) anywhere in the text caps the whole
    message at the 70-char UCS-2 single-segment budget."""
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    appointment = _make_appointment(
        tenant_id,
        contact.id,
        start_at=datetime.utcnow() + timedelta(hours=2),
        title="Consumer unit replacement — fuse board upgrade",
    )
    db.add(appointment)
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 1
    text = sms_sender.call_args_list[0].kwargs["text"]
    assert sms_segment_limit(text) == 70
    assert len(text) <= 70


# --- Fair use --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fair_use_pause_degrades_to_email_and_alerts_once(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    sms_sender: AsyncMock,
    telnyx_configured: None,
    recorded_alerts: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = _tenant_id(admin_client)
    monkeypatch.setattr("app.appointment_reminders.SMS_FAIR_USE_MONTHLY_THRESHOLD", 3)
    # Seed 3 SMS reminders already sent this month → threshold crossed.
    for i in range(3):
        db.add(
            Reminder(
                tenant_id=tenant_id,
                entity_type="appointment",
                entity_id=uuid4(),
                channel="sms",
                sequence=i + 1,
                payload={"window_hours": "24", "role": "customer"},
            )
        )
    contact = await _make_contact(db, tenant_id)
    appointment = _make_appointment(
        tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(appointment)
    await db.commit()

    now = datetime.utcnow()
    summary = await run_reminder_tick(db, now)

    # SMS paused: customer falls back to email; no SMS dispatched.
    assert summary["appointment_customer_sms"] == 0
    assert summary["appointment_email_fallbacks"] == 1
    sms_sender.assert_not_awaited()
    assert len(email_recorder.calls) == 1

    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    assert tenant.settings["sms_reminders_paused"] is True
    assert tenant.settings["sms_fair_use_period"] == current_period()

    assert len(recorded_alerts) == 1
    subject, text = recorded_alerts[0]
    assert tenant.slug in subject
    assert "degrade" in text or "email/push" in text

    # Second sweep: still paused, no second alert, no second email.
    summary2 = await run_reminder_tick(db, now + timedelta(minutes=30))
    assert summary2["appointment_email_fallbacks"] == 0
    assert len(recorded_alerts) == 1
    assert len(email_recorder.calls) == 1
    dedupe_rows = (
        (
            await db.execute(
                select(AiAlertState).where(AiAlertState.threshold == f"sms_fair_use:{tenant_id}")
            )
        )
        .scalars()
        .all()
    )
    assert len(dedupe_rows) == 1


@pytest.mark.asyncio
async def test_fair_use_pause_clears_next_month(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
    recorded_alerts: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stored pause from a past period is cleared and SMS flows again."""
    tenant_id = _tenant_id(admin_client)
    monkeypatch.setattr("app.appointment_reminders.SMS_FAIR_USE_MONTHLY_THRESHOLD", 500)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.settings = {
        **tenant.settings,
        "sms_reminders_paused": True,
        "sms_fair_use_period": "2000-01",
    }
    contact = await _make_contact(db, tenant_id)
    appointment = _make_appointment(
        tenant_id, contact.id, start_at=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(appointment)
    await db.commit()

    summary = await run_reminder_tick(db, datetime.utcnow())

    assert summary["appointment_customer_sms"] == 1
    tenant_after = await db.get(Tenant, tenant_id)
    assert tenant_after is not None
    assert "sms_reminders_paused" not in (tenant_after.settings or {})
    assert recorded_alerts == []
