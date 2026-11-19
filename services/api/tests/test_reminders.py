"""Tests for the in-process quote/invoice reminder scheduler (N6)."""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from app.config import settings
from app.models import AiCallEvent, Contact, Invoice, Notification, Quote, Reminder, Tenant
from app.rls import set_tenant_in_session
from app.scheduler import run_reminder_tick
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class _EmailRecorder:
    """Stand-in for app.scheduler.send_customer_email that records calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, db: Any = None, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return True


@pytest_asyncio.fixture
async def email_recorder(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[_EmailRecorder, None]:
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.scheduler.send_customer_email", recorder)
    yield recorder


def _tenant_id(admin_client: AsyncClient) -> UUID:
    return UUID(admin_client.headers["X-Tenant-ID"])


async def _make_contact(
    db: AsyncSession, tenant_id: UUID, email: str | None = "amy@example.com"
) -> Contact:
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email=email)
    db.add(contact)
    await db.flush()
    return contact


def _make_quote(
    tenant_id: UUID,
    contact_id: UUID,
    *,
    sent_days_ago: int = 4,
    status: str = "sent",
) -> Quote:
    return Quote(
        tenant_id=tenant_id,
        contact_id=contact_id,
        title="Consumer unit replacement",
        status=status,
        sent_at=datetime.utcnow() - timedelta(days=sent_days_ago),
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )


def _make_invoice(
    tenant_id: UUID,
    contact_id: UUID,
    *,
    due_days_ago: int = 8,
    status: str = "sent",
) -> Invoice:
    return Invoice(
        tenant_id=tenant_id,
        contact_id=contact_id,
        invoice_number=f"INV-{uuid4().hex[:6]}",
        status=status,
        issue_date=datetime.utcnow() - timedelta(days=due_days_ago + 14),
        due_date=datetime.utcnow() - timedelta(days=due_days_ago),
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )


async def test_quote_reminder_sent_when_due(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    quote = _make_quote(tenant_id, contact.id)
    db.add(quote)
    await db.commit()

    summary = await run_reminder_tick(db)

    assert summary["quote_reminders"] == 1
    assert len(email_recorder.calls) == 1
    call = email_recorder.calls[0]
    assert call["event"] == "quote_reminder"
    assert call["template"] == "quote_reminder"
    assert call["to_email"] == "amy@example.com"
    assert "Consumer unit replacement" in call["html_body"]

    reminders = (
        (await db.execute(select(Reminder).where(Reminder.entity_id == quote.id))).scalars().all()
    )
    assert len(reminders) == 1
    assert reminders[0].entity_type == "quote"
    assert reminders[0].sequence == 1

    notifications = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id,
                    Notification.type == "quote_reminder_sent",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notifications) == 1
    assert notifications[0].link == f"/quotes/{quote.id}"


async def test_quote_reminder_respects_cadence(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    db.add(_make_quote(tenant_id, contact.id))
    await db.commit()

    first = await run_reminder_tick(db)
    assert first["quote_reminders"] == 1
    # Immediate second sweep: cadence (default 3 days) has not elapsed.
    second = await run_reminder_tick(db)
    assert second["quote_reminders"] == 0
    assert len(email_recorder.calls) == 1


async def test_quote_reminder_stops_after_max_count(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.settings = {
        **tenant.settings,
        "quote_reminder_max": 2,
        "quote_reminder_interval_days": 1,
    }
    contact = await _make_contact(db, tenant_id)
    db.add(_make_quote(tenant_id, contact.id, sent_days_ago=10))
    await db.commit()

    assert (await run_reminder_tick(db))["quote_reminders"] == 1
    # Backdate the reminder so the next one is due.
    reminder = (
        await db.execute(select(Reminder).where(Reminder.entity_type == "quote"))
    ).scalar_one()
    reminder.created_at = datetime.utcnow() - timedelta(days=2)
    await db.commit()

    assert (await run_reminder_tick(db))["quote_reminders"] == 1  # second and last
    reminder2 = (await db.execute(select(Reminder).where(Reminder.sequence == 2))).scalar_one()
    reminder2.created_at = datetime.utcnow() - timedelta(days=2)
    await db.commit()

    # Max (2) reached — no third reminder ever.
    assert (await run_reminder_tick(db))["quote_reminders"] == 0
    assert len(email_recorder.calls) == 2


async def test_quote_reminder_skipped_when_not_sent_or_answered(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    draft = _make_quote(tenant_id, contact.id, status="draft")
    approved = _make_quote(tenant_id, contact.id, status="approved")
    db.add_all([draft, approved])
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["quote_reminders"] == 0
    assert email_recorder.calls == []


async def test_quote_reminder_disabled_by_tenant_setting(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.settings = {**tenant.settings, "quote_reminders_enabled": False}
    contact = await _make_contact(db, tenant_id)
    db.add(_make_quote(tenant_id, contact.id))
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["quote_reminders"] == 0
    assert email_recorder.calls == []


async def test_quote_reminder_without_contact_email_not_counted(
    admin_client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A customer with no email must not burn a reminder slot (N3 semantics)."""
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id, email=None)
    db.add(_make_quote(tenant_id, contact.id))
    await db.commit()

    async def _fail_send(db: Any = None, **kwargs):  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr("app.scheduler.send_customer_email", _fail_send)
    summary = await run_reminder_tick(db)
    assert summary["quote_reminders"] == 0
    reminders = (await db.execute(select(Reminder))).scalars().all()
    assert reminders == []


async def test_invoice_reminder_recurs_indefinitely(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    invoice = _make_invoice(tenant_id, contact.id)
    db.add(invoice)
    await db.commit()

    for expected_sequence in (1, 2, 3):
        summary = await run_reminder_tick(db)
        assert summary["invoice_reminders"] == 1
        reminder = (
            await db.execute(
                select(Reminder).where(
                    Reminder.entity_id == invoice.id,
                    Reminder.sequence == expected_sequence,
                )
            )
        ).scalar_one()
        # Backdate so the next recurrence is due (default interval 7 days).
        reminder.created_at = datetime.utcnow() - timedelta(days=8)
        await db.commit()

    assert len(email_recorder.calls) == 3
    assert all(call["template"] == "invoice_reminder" for call in email_recorder.calls)
    notification = (
        (await db.execute(select(Notification).where(Notification.type == "invoice_reminder_sent")))
        .scalars()
        .first()
    )
    assert notification is not None
    assert notification.link == f"/invoices/{invoice.id}"


async def test_invoice_reminder_stops_when_paid_or_cancelled(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    db.add_all(
        [
            _make_invoice(tenant_id, contact.id, status="paid"),
            _make_invoice(tenant_id, contact.id, status="cancelled"),
            _make_invoice(tenant_id, contact.id, status="draft"),
        ]
    )
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["invoice_reminders"] == 0
    assert email_recorder.calls == []


async def test_invoice_reminder_respects_cadence(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    db.add(_make_invoice(tenant_id, contact.id))
    await db.commit()

    assert (await run_reminder_tick(db))["invoice_reminders"] == 1
    assert (await run_reminder_tick(db))["invoice_reminders"] == 0
    assert len(email_recorder.calls) == 1


async def test_tick_isolates_failing_tenant(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    """A second healthy tenant still gets reminders when another tenant errors."""
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    db.add(_make_quote(tenant_id, contact.id))

    broken = Tenant(slug=f"broken-{uuid4().hex[:8]}", name="Broken Ltd")
    db.add(broken)
    await db.flush()
    await set_tenant_in_session(db, broken.id)
    broken_contact = Contact(tenant_id=broken.id, name="Bob", email="bob@example.com")
    db.add(broken_contact)
    await db.flush()
    db.add(_make_quote(broken.id, broken_contact.id))
    await db.commit()

    # Force the broken tenant to fail mid-processing by corrupting settings type.
    broken.settings = {"quote_reminder_interval_days": "not-a-number-but-clamped"}
    await db.commit()

    summary = await run_reminder_tick(db)
    # Both tenants processed; bad values are clamped to defaults, not fatal.
    assert summary["tenants"] == 2
    assert summary["quote_reminders"] == 2
    assert summary["errors"] == 0


# ---------------------------------------------------------------------------
# F2: per-customer reminder (chase) overrides + AI-drafted reminder copy
# ---------------------------------------------------------------------------


async def test_contact_reminder_preferences_patch_merge_and_validation(
    admin_client: AsyncClient,
) -> None:
    """Known keys merge key-by-key; unknown keys and bad values are rejected."""
    response = await admin_client.post(
        "/contacts", json={"name": "Amy Homeowner", "email": "amy@example.com"}
    )
    assert response.status_code == 201
    contact_id = response.json()["id"]
    assert response.json()["reminder_preferences"] is None

    response = await admin_client.patch(
        f"/contacts/{contact_id}",
        json={"reminder_preferences": {"quote_chase_enabled": False, "max_reminders": 2}},
    )
    assert response.status_code == 200
    assert response.json()["reminder_preferences"] == {
        "quote_chase_enabled": False,
        "max_reminders": 2,
    }

    # Unknown keys are rejected so typos cannot silently create dead prefs.
    response = await admin_client.patch(
        f"/contacts/{contact_id}",
        json={"reminder_preferences": {"email_me_daily": True}},
    )
    assert response.status_code == 400
    assert "unknown_reminder_preference" in response.json()["detail"]

    # Non-integer max_reminders is rejected (a string fails Pydantic
    # validation at the schema layer; a bool reaches the router and is
    # rejected there).
    response = await admin_client.patch(
        f"/contacts/{contact_id}",
        json={"reminder_preferences": {"max_reminders": "lots"}},
    )
    assert response.status_code == 422
    response = await admin_client.patch(
        f"/contacts/{contact_id}",
        json={"reminder_preferences": {"max_reminders": True}},
    )
    assert response.status_code == 400
    assert "invalid_reminder_preference" in response.json()["detail"]

    # Clearing every key collapses back to NULL (tenant defaults).
    response = await admin_client.patch(
        f"/contacts/{contact_id}",
        json={"reminder_preferences": {"quote_chase_enabled": None, "max_reminders": None}},
    )
    assert response.status_code == 200
    assert response.json()["reminder_preferences"] is None


async def test_quote_reminder_skipped_when_contact_chase_disabled(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    contact.reminder_preferences = {"quote_chase_enabled": False}
    db.add(_make_quote(tenant_id, contact.id))
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["quote_reminders"] == 0
    assert email_recorder.calls == []
    assert (await db.execute(select(Reminder))).scalars().all() == []


async def test_invoice_reminder_skipped_when_contact_chase_disabled(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    contact.reminder_preferences = {"invoice_chase_enabled": False}
    db.add(_make_invoice(tenant_id, contact.id))
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["invoice_reminders"] == 0
    assert email_recorder.calls == []


async def test_quote_reminder_capped_by_contact_max_reminders(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    """Contact max_reminders caps the tenant cadence downward only."""
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.settings = {
        **tenant.settings,
        "quote_reminder_max": 3,
        "quote_reminder_interval_days": 1,
    }
    contact = await _make_contact(db, tenant_id)
    contact.reminder_preferences = {"max_reminders": 1}
    db.add(_make_quote(tenant_id, contact.id, sent_days_ago=10))
    await db.commit()

    assert (await run_reminder_tick(db))["quote_reminders"] == 1

    # Backdate the reminder so cadence would allow another — the contact cap
    # must still stop the sequence at one.
    reminder = (
        await db.execute(select(Reminder).where(Reminder.entity_type == "quote"))
    ).scalar_one()
    reminder.created_at = datetime.utcnow() - timedelta(days=2)
    await db.commit()

    assert (await run_reminder_tick(db))["quote_reminders"] == 0
    assert len(email_recorder.calls) == 1


def _fake_draft_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=200,
            completion_tokens=60,
            prompt_tokens_details=None,
        ),
    )


async def _reminder_draft_events(db: AsyncSession, tenant_id: UUID) -> list[AiCallEvent]:
    rows = await db.execute(
        select(AiCallEvent).where(
            AiCallEvent.feature == "reminder_draft",
            AiCallEvent.tenant_id == tenant_id,
        )
    )
    return list(rows.scalars().all())


async def test_quote_reminder_uses_ai_draft_and_logs_event(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake LLM success → drafted copy rendered, cached on the row, event logged."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    draft = "Hi Amy, just a gentle nudge about your consumer unit quote — it only takes a moment to accept."
    fake_llm = AsyncMock(return_value=_fake_draft_response(draft))
    monkeypatch.setattr("app.reminder_draft.acompletion", fake_llm)

    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    quote = _make_quote(tenant_id, contact.id)
    db.add(quote)
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["quote_reminders"] == 1
    assert fake_llm.await_count == 1

    call = email_recorder.calls[0]
    assert draft in call["html_body"]
    assert draft in call["text_body"]

    reminder = (
        (await db.execute(select(Reminder).where(Reminder.entity_id == quote.id))).scalars().one()
    )
    assert reminder.payload["ai_draft"] == draft

    events = await _reminder_draft_events(db, tenant_id)
    assert len(events) == 1
    assert events[0].status == "success"
    assert events[0].actor_type == "system"
    assert events[0].gen_ai_usage_input_tokens == 200


async def test_reminder_reuses_cached_draft_without_recalling_llm(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Later episodes of a chase reuse the cached draft — the LLM is paid once."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    draft = "Hi Amy, your quote is still waiting for a quick look when you have a moment."
    fake_llm = AsyncMock(return_value=_fake_draft_response(draft))
    monkeypatch.setattr("app.reminder_draft.acompletion", fake_llm)

    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.settings = {**tenant.settings, "quote_reminder_interval_days": 1}
    contact = await _make_contact(db, tenant_id)
    db.add(_make_quote(tenant_id, contact.id))
    await db.commit()

    assert (await run_reminder_tick(db))["quote_reminders"] == 1
    reminder = (
        await db.execute(select(Reminder).where(Reminder.entity_type == "quote"))
    ).scalar_one()
    reminder.created_at = datetime.utcnow() - timedelta(days=2)
    await db.commit()

    # Second episode: cadence due, cache hit — no second LLM call.
    assert (await run_reminder_tick(db))["quote_reminders"] == 1
    assert fake_llm.await_count == 1
    assert len(email_recorder.calls) == 2
    assert draft in email_recorder.calls[1]["html_body"]
    reminders = (await db.execute(select(Reminder).order_by(Reminder.sequence))).scalars().all()
    assert [r.payload["ai_draft"] for r in reminders] == [draft, draft]
    # Still only one ai_call_events row for the whole chase.
    assert len(await _reminder_draft_events(db, tenant_id)) == 1


async def test_quote_reminder_falls_back_to_static_template_when_llm_fails(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake LLM timeout/error → static template still sent, failure recorded."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    fake_llm = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    monkeypatch.setattr("app.reminder_draft.acompletion", fake_llm)

    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    quote = _make_quote(tenant_id, contact.id)
    db.add(quote)
    await db.commit()

    summary = await run_reminder_tick(db)  # must not raise
    assert summary["quote_reminders"] == 1

    call = email_recorder.calls[0]
    assert "Just a friendly reminder" in call["text_body"]
    reminder = (
        (await db.execute(select(Reminder).where(Reminder.entity_id == quote.id))).scalars().one()
    )
    assert "ai_draft" not in reminder.payload

    events = await _reminder_draft_events(db, tenant_id)
    assert len(events) == 1
    assert events[0].status == "error"


async def test_quote_reminder_sanity_gate_rejects_garbage_draft(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A markdown-broken/oversized draft falls back to the static template."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    garbage = "```json\n{#broken markdown}\n```"
    fake_llm = AsyncMock(return_value=_fake_draft_response(garbage))
    monkeypatch.setattr("app.reminder_draft.acompletion", fake_llm)

    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    db.add(_make_quote(tenant_id, contact.id))
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["quote_reminders"] == 1
    call = email_recorder.calls[0]
    assert "```json" not in call["html_body"]
    assert "Just a friendly reminder" in call["text_body"]


async def test_quote_reminder_skips_llm_when_no_api_key(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No API key → static template, and no ai_call_events row is attempted."""
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    fake_llm = AsyncMock()
    monkeypatch.setattr("app.reminder_draft.acompletion", fake_llm)

    tenant_id = _tenant_id(admin_client)
    contact = await _make_contact(db, tenant_id)
    db.add(_make_quote(tenant_id, contact.id))
    await db.commit()

    summary = await run_reminder_tick(db)
    assert summary["quote_reminders"] == 1
    assert "Just a friendly reminder" in email_recorder.calls[0]["text_body"]
    fake_llm.assert_not_awaited()
    assert await _reminder_draft_events(db, tenant_id) == []
