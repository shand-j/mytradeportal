"""Tests for customer-facing email triggers (beta-backlog N3/N4).

Covers: every trigger dispatches through ``send_event_email``, Resend errors
are logged at error level (never raised), and customers without a contact
email produce a warning log instead of a silent drop.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app import email as email_module
from app.email import send_event_email
from app.models import Contact, Customer, Quote, QuoteRequest, Tenant
from app.quote_automation import email_triage_question, start_ai_triage
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.security import create_access_token, get_password_hash
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class _RecordingLogger:
    """Stand-in for the structlog logger that records every call."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def _record(self, level: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.events.append((level, str(args[0]) if args else "", kwargs))

    def info(self, *args: Any, **kwargs: Any) -> None:
        self._record("info", args, kwargs)

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self._record("warning", args, kwargs)

    def error(self, *args: Any, **kwargs: Any) -> None:
        self._record("error", args, kwargs)

    def find(self, level: str, event: str) -> list[dict[str, Any]]:
        return [kw for lvl, ev, kw in self.events if lvl == level and ev == event]


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


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.posts: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _FakeResponse:
        self.posts.append((url, json, headers))
        return self._response


def _enable_resend(monkeypatch: MonkeyPatch, response: _FakeResponse) -> _FakeAsyncClient:
    monkeypatch.setattr(email_module.settings, "resend_api_key", "re_dev_test")
    monkeypatch.setattr(email_module.settings, "resend_from_email", "quotes@test.local")
    fake_client = _FakeAsyncClient(response)
    monkeypatch.setattr(email_module.httpx, "AsyncClient", lambda **_: fake_client)
    return fake_client


async def _create_tenant(db: AsyncSession, slug: str, email: str = "") -> Tenant:
    await bypass_rls_in_session(db)
    tenant = Tenant(
        slug=slug, name=f"{slug} Electrical", settings={"email": email} if email else {}
    )
    db.add(tenant)
    await db.flush()
    return tenant


async def _create_lead(
    db: AsyncSession, tenant: Tenant, contact_email: str | None
) -> tuple[Contact, QuoteRequest]:
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Lead Owner", email=contact_email)
    db.add(contact)
    await db.flush()
    lead = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        source="web_form",
        raw_text="Fuse board keeps tripping",
        structured_data={"category": "consumer_unit", "title": "Fuse board replacement"},
    )
    db.add(lead)
    await db.flush()
    return contact, lead


# ---------------------------------------------------------------------------
# send_event_email wrapper
# ---------------------------------------------------------------------------


async def test_send_event_email_dispatches_via_resend(monkeypatch: MonkeyPatch) -> None:
    """Happy path: the Resend HTTP call fires and the dispatch is logged."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(email_module, "logger", recorder)
    fake_client = _enable_resend(monkeypatch, _FakeResponse(200, {"id": "msg-1"}))

    sent = await send_event_email(
        to_email="homeowner@example.com",
        subject="Your quote",
        html_body="<p>hi</p>",
        text_body="hi",
        event="quote_sent",
        template="quote_ready",
        context={"quote_id": "q-1"},
    )

    assert sent is True
    assert len(fake_client.posts) == 1
    _, payload, _ = fake_client.posts[0]
    assert payload["to"] == ["homeowner@example.com"]
    logged = recorder.find("info", "email_dispatched")
    assert len(logged) == 1
    assert logged[0]["email_event"] == "quote_sent"
    assert logged[0]["template"] == "quote_ready"
    assert logged[0]["quote_id"] == "q-1"


async def test_send_event_email_without_recipient_logs_warning_not_raise(
    monkeypatch: MonkeyPatch,
) -> None:
    """No contact email → warning logged, no HTTP call, no exception (N3)."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(email_module, "logger", recorder)
    fake_client = _enable_resend(monkeypatch, _FakeResponse(200, {"id": "msg-1"}))

    sent = await send_event_email(
        to_email=None,
        subject="Your quote",
        html_body="<p>hi</p>",
        event="quote_sent",
        template="quote_ready",
        context={"quote_id": "q-2", "customer_id": "c-2"},
    )

    assert sent is False
    assert fake_client.posts == []
    warnings = recorder.find("warning", "email_skipped_no_contact_email")
    assert len(warnings) == 1
    assert warnings[0]["customer_id"] == "c-2"
    assert warnings[0]["email_event"] == "quote_sent"


async def test_send_event_email_blank_recipient_also_skipped(monkeypatch: MonkeyPatch) -> None:
    """Whitespace-only addresses count as missing."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(email_module, "logger", recorder)
    fake_client = _enable_resend(monkeypatch, _FakeResponse(200, {"id": "msg-1"}))

    sent = await send_event_email(
        to_email="   ",
        subject="s",
        html_body="<p>x</p>",
        event="account_created",
        template="account_created",
    )

    assert sent is False
    assert fake_client.posts == []
    assert len(recorder.find("warning", "email_skipped_no_contact_email")) == 1


async def test_send_event_email_resend_error_logged_at_error_level(
    monkeypatch: MonkeyPatch,
) -> None:
    """A Resend API failure is logged with recipient/template/event, not raised."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(email_module, "logger", recorder)
    _enable_resend(monkeypatch, _FakeResponse(422, {"error": "invalid recipient"}))

    sent = await send_event_email(
        to_email="bad@example.com",
        subject="Reset",
        html_body="<p>reset</p>",
        event="password_reset",
        template="password_reset",
    )

    assert sent is False
    errors = recorder.find("error", "email_send_failed")
    assert len(errors) == 1
    assert errors[0]["recipient"] == "bad@example.com"
    assert errors[0]["template"] == "password_reset"
    assert errors[0]["email_event"] == "password_reset"
    # The transport also logs the Resend status + body at error level.
    transport_errors = recorder.find("error", "resend_send_failed")
    assert len(transport_errors) == 1
    assert transport_errors[0]["status"] == 422


async def test_send_event_email_transport_exception_logged_not_raised(
    monkeypatch: MonkeyPatch,
) -> None:
    """A raised transport error (SMTP down, network) is logged, never raised."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(email_module, "logger", recorder)

    async def _boom(**_: Any) -> None:
        raise ConnectionError("smtp down")

    monkeypatch.setattr(email_module, "send_email", _boom)

    sent = await send_event_email(
        to_email="user@example.com",
        subject="s",
        html_body="<p>x</p>",
        event="quote_accepted",
        template="quote_accepted",
    )

    assert sent is False
    errors = recorder.find("error", "email_send_failed")
    assert len(errors) == 1
    assert errors[0]["error_type"] == "ConnectionError"


# ---------------------------------------------------------------------------
# Trigger: quote sent to customer (POST /quotes/{id}/send)
# ---------------------------------------------------------------------------


async def _create_quote_via_api(
    client: AsyncClient, tenant_id: str, contact_id: str
) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Fuse board replacement",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def test_quote_send_dispatches_quote_ready_email(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """POST /quotes/{id}/send emails the contact a review link."""
    tenant = await _create_tenant(db, f"qsend-{uuid4().hex[:8]}", email="sparks@example.com")
    contact, _ = await _create_lead(db, tenant, "homeowner@example.com")
    quote = await _create_quote_via_api(client, str(tenant.id), str(contact.id))

    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.quotes.send_customer_email", send_mock)

    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": str(tenant.id)}
    )

    assert response.status_code == 200, response.text
    send_mock.assert_awaited_once()
    assert send_mock.await_args is not None
    kwargs = send_mock.await_args.kwargs
    assert kwargs["to_email"] == "homeowner@example.com"
    assert kwargs["event"] == "quote_sent"
    assert kwargs["template"] == "quote_ready"
    # Tenant-branded customer comm: display name + Reply-To to the tenant.
    assert kwargs["from_name"] == tenant.name
    assert kwargs["reply_to"] == "sparks@example.com"


async def test_quote_send_without_contact_email_logs_warning(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Contact without email: send succeeds, skip is warning-logged (N3)."""
    tenant = await _create_tenant(db, f"qsend-{uuid4().hex[:8]}")
    contact, _ = await _create_lead(db, tenant, None)
    quote = await _create_quote_via_api(client, str(tenant.id), str(contact.id))

    recorder = _RecordingLogger()
    monkeypatch.setattr(email_module, "logger", recorder)
    transport = AsyncMock()
    monkeypatch.setattr(email_module, "send_email", transport)

    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": str(tenant.id)}
    )

    assert response.status_code == 200, response.text
    transport.assert_not_called()
    warnings = recorder.find("warning", "email_skipped_no_contact_email")
    assert len(warnings) == 1
    assert warnings[0]["email_event"] == "quote_sent"
    assert warnings[0]["quote_id"] == quote["id"]


# ---------------------------------------------------------------------------
# Trigger: customer account created (POST /customer/register)
# ---------------------------------------------------------------------------


async def test_customer_register_dispatches_account_created_email(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Registering a homeowner sends a no-reply welcome email."""
    slug = f"cust-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)

    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.customer_portal.send_customer_email", send_mock)

    response = await client.post(
        "/customer/register",
        json={
            "slug": slug,
            "full_name": "Homeowner Jane",
            "email": "jane@example.com",
            "password": "homeowner-pass-123",
        },
    )

    assert response.status_code == 201, response.text
    send_mock.assert_awaited_once()
    assert send_mock.await_args is not None
    kwargs = send_mock.await_args.kwargs
    assert kwargs["to_email"] == "jane@example.com"
    assert kwargs["event"] == "account_created"
    assert kwargs["template"] == "account_created"
    # Transactional account mail: no tenant display name → no-reply sender,
    # and no Reply-To.
    assert kwargs.get("from_name") is None
    assert kwargs.get("reply_to") is None


# ---------------------------------------------------------------------------
# Trigger: quote accepted (POST /customer/quotes/{id}/accept)
# ---------------------------------------------------------------------------


async def test_quote_accept_dispatches_confirmation_email(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Customer accepting a quote gets an email confirmation."""
    tenant = await _create_tenant(db, f"cust-{uuid4().hex[:8]}")
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Homeowner Jane", email="jane@example.com")
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email="jane@example.com",
        full_name="Homeowner Jane",
        password_hash=get_password_hash("homeowner-pass-123"),
        is_active=True,
    )
    db.add(customer)
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="Fuse board replacement",
        status="sent",
        subtotal=Decimal("480.00"),
        vat_amount=Decimal("96.00"),
        total=Decimal("576.00"),
    )
    db.add(quote)
    await db.flush()

    token = create_access_token(
        user_id=customer.id,
        tenant_id=tenant.id,
        role="customer",
        email=customer.email,
        subject_type="customer",
    )
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("app.quote_acceptance.send_customer_email", send_mock)

    response = await client.post(
        f"/customer/quotes/{quote.id}/accept",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    send_mock.assert_awaited_once()
    assert send_mock.await_args is not None
    kwargs = send_mock.await_args.kwargs
    assert kwargs["to_email"] == "jane@example.com"
    assert kwargs["event"] == "quote_accepted"
    assert kwargs["template"] == "quote_accepted"


# ---------------------------------------------------------------------------
# Trigger: AI follow-up needed (triage question)
# ---------------------------------------------------------------------------


async def test_email_triage_question_sends_to_contact_email(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """The triage helper emails the lead's contact, tenant-branded."""
    tenant = await _create_tenant(db, f"triage-{uuid4().hex[:8]}", email="sparks@example.com")
    _, lead = await _create_lead(db, tenant, "homeowner@example.com")

    transport = AsyncMock()
    monkeypatch.setattr(email_module, "send_email", transport)

    await email_triage_question(db, tenant, lead, "Where is the consumer unit?")

    transport.assert_awaited_once()
    assert transport.await_args is not None
    kwargs = transport.await_args.kwargs
    assert kwargs["to_email"] == "homeowner@example.com"
    assert kwargs["from_name"] == tenant.name
    assert kwargs["reply_to"] == "sparks@example.com"
    assert "Where is the consumer unit?" in kwargs["html_body"]


async def test_email_triage_question_without_contact_email_logs_warning(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Lead without contact email: warning logged, nothing raised (N3)."""
    tenant = await _create_tenant(db, f"triage-{uuid4().hex[:8]}")
    _, lead = await _create_lead(db, tenant, None)

    recorder = _RecordingLogger()
    monkeypatch.setattr(email_module, "logger", recorder)
    transport = AsyncMock()
    monkeypatch.setattr(email_module, "send_email", transport)

    await email_triage_question(db, tenant, lead, "Where is the consumer unit?")

    transport.assert_not_called()
    warnings = recorder.find("warning", "email_skipped_no_contact_email")
    assert len(warnings) == 1
    assert warnings[0]["email_event"] == "ai_followup_needed"
    assert warnings[0]["quote_request_id"] == str(lead.id)


async def test_start_ai_triage_dispatches_email(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Auto-triage opening (low-confidence draft) emails the question."""
    tenant = await _create_tenant(db, f"triage-{uuid4().hex[:8]}")
    _, lead = await _create_lead(db, tenant, "homeowner@example.com")

    followup_payload = {
        "confidence": 40,
        "complete": False,
        "message": "Where is the consumer unit located?",
        "options": [],
    }
    monkeypatch.setattr("app.rag.generate_followup", AsyncMock(return_value=followup_payload))
    email_mock = AsyncMock()
    monkeypatch.setattr("app.quote_automation.email_triage_question", email_mock)

    await start_ai_triage(db, tenant, lead.id, 0.5)

    email_mock.assert_awaited_once()
    assert email_mock.await_args is not None
    args = email_mock.await_args.args
    assert args[1].id == tenant.id
    assert args[2].id == lead.id
    assert args[3] == "Where is the consumer unit located?"


async def test_ai_followup_endpoint_dispatches_email(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """A new (non-closure) AI question from the endpoint is emailed too."""
    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    _, lead = await _create_lead(db, tenant, "lead.owner@example.com")

    followup_payload = {
        "confidence": 40,
        "complete": False,
        "message": "Where is the consumer unit located?",
        "extracted": {},
    }
    monkeypatch.setattr(
        "app.routers.communications.generate_followup",
        AsyncMock(return_value=followup_payload),
    )
    email_mock = AsyncMock()
    monkeypatch.setattr("app.routers.communications.email_triage_question", email_mock)

    response = await admin_client.post(f"/communications/{lead.id}/ai-followup")

    assert response.status_code == 200, response.text
    email_mock.assert_awaited_once()
    assert email_mock.await_args is not None
    args = email_mock.await_args.args
    assert args[2].id == lead.id
    assert args[3] == "Where is the consumer unit located?"


async def test_ai_followup_closure_does_not_email(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """A closure message is not a follow-up question — no email."""
    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    _, lead = await _create_lead(db, tenant, "lead.owner@example.com")

    followup_payload = {
        "confidence": 95,
        "complete": True,
        "message": "Thanks, that's everything.",
        "extracted": {},
    }
    monkeypatch.setattr(
        "app.routers.communications.generate_followup",
        AsyncMock(return_value=followup_payload),
    )
    email_mock = AsyncMock()
    monkeypatch.setattr("app.routers.communications.email_triage_question", email_mock)

    response = await admin_client.post(f"/communications/{lead.id}/ai-followup")

    assert response.status_code == 200, response.text
    email_mock.assert_not_called()
