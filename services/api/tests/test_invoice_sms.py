"""Tests for sending invoices by SMS (POST /invoices/{id}/send-sms).

Covers the Telnyx send path (link minting, one-segment tenant-branded body,
fair-use Reminder row), the eligibility 4xx cases (Telnyx unconfigured, no
normalisable phone, STOP opt-out), provider-failure handling, and the
``sms_available`` affordance flag on InvoiceRead.
"""

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.config import settings
from app.models import AuditLog, Contact, DocumentAccessToken, Invoice, Reminder
from app.rls import set_tenant_in_session
from app.routers.invoices import _invoice_sms_text
from app.sms import sms_segment_limit
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def sms_sender(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Fake Telnyx dispatch: every send succeeds with a message id."""
    sender = AsyncMock(return_value="msg_test_1")
    monkeypatch.setattr("app.routers.invoices.send_sms", sender)
    return sender


@pytest.fixture
def telnyx_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telnyx_api_key", "KEYTEST")
    monkeypatch.setattr(settings, "telnyx_from_number", "+447700900000")
    monkeypatch.setattr(settings, "telnyx_messaging_profile_id", "")


@pytest.fixture
def telnyx_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telnyx_api_key", "")
    monkeypatch.setattr(settings, "telnyx_from_number", "")
    monkeypatch.setattr(settings, "telnyx_messaging_profile_id", "")


def _tenant_id(admin_client: AsyncClient) -> UUID:
    return UUID(admin_client.headers["X-Tenant-ID"])


async def _make_invoice(
    admin_client: AsyncClient,
    db: AsyncSession,
    *,
    phone: str | None = "07700900123",
    opted_out: bool = False,
) -> tuple[Contact, dict[str, Any]]:
    """A contact (created directly so reminder_preferences are settable) plus a
    scratch invoice created through the API."""
    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(
        tenant_id=tenant_id,
        name="Amy Homeowner",
        email="amy@example.com",
        phone=phone,
        reminder_preferences={"sms_opt_out": True} if opted_out else None,
    )
    db.add(contact)
    await db.flush()
    response = await admin_client.post(
        "/invoices",
        json={
            "contact_id": str(contact.id),
            "invoice_number": f"INV-{uuid4().hex[:6]}",
            "line_items": [
                {"description": "Fuse board works", "quantity": "1", "unit_price": "600.00"},
            ],
        },
    )
    assert response.status_code == 201
    return contact, response.json()


async def _invoice_reminders(db: AsyncSession, tenant_id: UUID, invoice_id: str) -> list[Reminder]:
    await set_tenant_in_session(db, tenant_id)
    return list(
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.entity_type == "invoice",
                    Reminder.entity_id == UUID(invoice_id),
                )
                .order_by(Reminder.sequence)
            )
        )
        .scalars()
        .all()
    )


# --- SMS body builder ---------------------------------------------------------


def test_invoice_sms_text_fits_one_segment_and_keeps_the_link_whole() -> None:
    url = "https://www.mytradeportal.co.uk/invoice/" + "a" * 43
    text = _invoice_sms_text(
        tenant_name="A Very Long Electrical Company Name Ltd",
        invoice_number="INV-123",
        total="1,234.56",
        url=url,
        include_stop=True,
    )
    assert text is not None
    assert len(text) <= sms_segment_limit(text)
    assert url in text  # the link is never truncated or split
    assert "Reply STOP to opt out." in text


def test_invoice_sms_text_drops_the_stop_line_for_alphanumeric_senders() -> None:
    url = "https://www.mytradeportal.co.uk/invoice/" + "a" * 43
    text = _invoice_sms_text(
        tenant_name="Test Electrical",
        invoice_number="INV-001",
        total="600.00",
        url=url,
        include_stop=False,
    )
    assert text is not None
    assert "STOP" not in text
    assert text.startswith("Test Electrical: Invoice INV-001 for £600.00.")


def test_invoice_sms_text_returns_none_when_the_link_alone_is_too_long() -> None:
    url = "https://example.com/invoice/" + "x" * 200
    assert (
        _invoice_sms_text(
            tenant_name="Test Electrical",
            invoice_number="INV-001",
            total="600.00",
            url=url,
            include_stop=False,
        )
        is None
    )


# --- Happy path -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_sms_mints_link_sends_and_records(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    contact, invoice = await _make_invoice(admin_client, db)

    response = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["sms_available"] is True

    sms_sender.assert_awaited_once()
    call = sms_sender.call_args
    assert call.kwargs["to_phone"] == contact.phone
    assert call.kwargs["tenant_name"] == "Test Electrical"
    text = call.kwargs["text"]
    assert sms_segment_limit(text) == 160
    assert len(text) <= 160
    assert "/invoice/" in text
    assert invoice["invoice_number"] in text
    assert "£600.00" in text

    tenant_id = _tenant_id(admin_client)
    await set_tenant_in_session(db, tenant_id)
    tokens = (
        (
            await db.execute(
                select(DocumentAccessToken).where(
                    DocumentAccessToken.document_id == UUID(invoice["id"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(tokens) == 1

    reminders = await _invoice_reminders(db, tenant_id, invoice["id"])
    assert [(r.channel, r.sequence) for r in reminders] == [("sms", 1)]
    assert reminders[0].payload["to"] == "+447700900123"
    assert reminders[0].payload["telnyx_message_id"] == "msg_test_1"

    audit_rows = (
        (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "invoice",
                    AuditLog.entity_id == UUID(invoice["id"]),
                    AuditLog.action == "invoice.sent",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1
    assert audit_rows[0].payload["channel"] == "sms"


@pytest.mark.asyncio
async def test_send_sms_resend_counts_toward_fair_use_each_time(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    """Every dispatched SMS appends a channel='sms' Reminder row — the rows the
    monthly fair-use guardrail counts."""
    _, invoice = await _make_invoice(admin_client, db)

    first = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")
    second = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")

    assert first.status_code == 200
    assert second.status_code == 200
    assert sms_sender.await_count == 2
    reminders = await _invoice_reminders(db, _tenant_id(admin_client), invoice["id"])
    assert [(r.channel, r.sequence) for r in reminders] == [("sms", 1), ("sms", 2)]


# --- Eligibility 4xx --------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_sms_unconfigured_returns_400(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_unconfigured: None,
) -> None:
    _, invoice = await _make_invoice(admin_client, db)

    response = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")

    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]
    sms_sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_sms_without_phone_returns_400(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    _, invoice = await _make_invoice(admin_client, db, phone=None)

    response = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")

    assert response.status_code == 400
    assert "phone" in response.json()["detail"]
    sms_sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_sms_unnormalisable_phone_returns_400(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    _, invoice = await _make_invoice(admin_client, db, phone="not-a-number")

    response = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")

    assert response.status_code == 400
    sms_sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_sms_respects_stop_opt_out(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    _, invoice = await _make_invoice(admin_client, db, opted_out=True)

    response = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")

    assert response.status_code == 409
    assert "opted out" in response.json()["detail"]
    sms_sender.assert_not_awaited()
    assert await _invoice_reminders(db, _tenant_id(admin_client), invoice["id"]) == []
    # The invoice is untouched — still a draft.
    row = await db.get(Invoice, UUID(invoice["id"]))
    assert row is not None
    assert row.status == "draft"


@pytest.mark.asyncio
async def test_send_sms_provider_failure_returns_502_without_recording(
    admin_client: AsyncClient,
    db: AsyncSession,
    sms_sender: AsyncMock,
    telnyx_configured: None,
) -> None:
    sms_sender.return_value = None  # Telnyx rejected the send
    _, invoice = await _make_invoice(admin_client, db)

    response = await admin_client.post(f"/invoices/{invoice['id']}/send-sms")

    assert response.status_code == 502
    assert await _invoice_reminders(db, _tenant_id(admin_client), invoice["id"]) == []
    row = await db.get(Invoice, UUID(invoice["id"]))
    assert row is not None
    assert row.status == "draft"


# --- sms_available affordance flag -------------------------------------------------


@pytest.mark.asyncio
async def test_sms_available_flag_on_detail_and_list(
    admin_client: AsyncClient,
    db: AsyncSession,
    telnyx_configured: None,
) -> None:
    _, eligible = await _make_invoice(admin_client, db)
    _, opted_out = await _make_invoice(admin_client, db, opted_out=True)

    detail = await admin_client.get(f"/invoices/{eligible['id']}")
    assert detail.status_code == 200
    assert detail.json()["sms_available"] is True

    opted_out_detail = await admin_client.get(f"/invoices/{opted_out['id']}")
    assert opted_out_detail.json()["sms_available"] is False

    listed = await admin_client.get("/invoices")
    by_id = {i["id"]: i for i in listed.json()}
    assert by_id[eligible["id"]]["sms_available"] is True
    assert by_id[opted_out["id"]]["sms_available"] is False


@pytest.mark.asyncio
async def test_sms_available_false_when_unconfigured(
    admin_client: AsyncClient,
    db: AsyncSession,
    telnyx_unconfigured: None,
) -> None:
    _, invoice = await _make_invoice(admin_client, db)

    detail = await admin_client.get(f"/invoices/{invoice['id']}")

    assert detail.status_code == 200
    assert detail.json()["sms_available"] is False
