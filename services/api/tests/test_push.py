"""Tests for the Expo push send path and notification-trigger push coverage.

The Expo push HTTP call is stubbed (a fake ``httpx.AsyncClient``) so payload
shape, ticket-error handling, invalid-token cleanup and per-event trigger
coverage are verified without network access.
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import Customer, Notification, PushToken, QuoteRequest
from app.push import notify_customer, notify_staff, send_expo_push
from app.quote_automation import _notify_quote_failed, _notify_quote_ready
from app.rls import set_tenant_in_session
from app.schemas import QuoteRead
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class _FakeExpoResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"data": []}
        self.text = json.dumps(self._payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeExpoClient:
    """Stand-in for httpx.AsyncClient that records POSTs to the Expo API."""

    def __init__(self, calls: list[dict[str, Any]], response: _FakeExpoResponse):
        self._calls = calls
        self._response = response

    async def __aenter__(self) -> "_FakeExpoClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: object = None) -> _FakeExpoResponse:
        self._calls.append({"url": url, "json": json})
        return self._response


def _stub_expo(
    monkeypatch: pytest.MonkeyPatch, response: _FakeExpoResponse
) -> list[dict[str, Any]]:
    """Patch the httpx client used by app.push; returns the recorded calls."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.push.httpx.AsyncClient",
        lambda **kwargs: _FakeExpoClient(calls, response),
    )
    return calls


async def _seed_push_token(
    db: AsyncSession,
    tenant_id: UUID,
    owner_type: str,
    owner_id: UUID,
    token: str,
) -> PushToken:
    await set_tenant_in_session(db, tenant_id)
    row = PushToken(
        tenant_id=tenant_id,
        owner_type=owner_type,
        owner_id=owner_id,
        token=token,
        platform="ios",
    )
    db.add(row)
    await db.flush()
    return row


async def _seed_customer(db: AsyncSession, tenant_id: UUID) -> Customer:
    """Seed a customer account directly (independent of the register endpoint)."""
    await set_tenant_in_session(db, tenant_id)
    customer = Customer(
        tenant_id=tenant_id,
        email=f"jane-{uuid4().hex[:6]}@example.com",
        full_name="Homeowner Jane",
    )
    db.add(customer)
    await db.flush()
    return customer


def _quote_read(tenant_id: UUID, quote_request_id: UUID | None = None) -> QuoteRead:
    now = datetime.utcnow()
    contact_id = uuid4()
    return QuoteRead.model_validate(
        {
            "id": uuid4(),
            "tenant_id": tenant_id,
            "contact_id": contact_id,
            "title": "Full rewire",
            "description": None,
            "status": "draft",
            "subtotal": Decimal("100.00"),
            "vat_rate": Decimal("20.00"),
            "vat_amount": Decimal("20.00"),
            "total": Decimal("120.00"),
            "valid_until": None,
            "approved_at": None,
            "sent_at": None,
            "line_items": [],
            "bill_of_quantities": None,
            "quote_request_id": quote_request_id,
            "created_at": now,
            "updated_at": now,
            "contact": {
                "id": contact_id,
                "tenant_id": tenant_id,
                "name": "Homeowner Jane",
                "email": None,
                "phone": None,
                "address": None,
                "postcode": None,
                "notes": None,
                "created_at": now,
                "updated_at": now,
            },
        }
    )


async def test_send_expo_push_posts_alert_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Messages include sound/priority so iOS shows a banner with sound."""
    calls = _stub_expo(monkeypatch, _FakeExpoResponse(payload={"data": [{"status": "ok"}]}))

    await send_expo_push(
        ["ExponentPushToken[device1]"],
        "Quote ready for review",
        "AI draft quote is ready.",
        data={"type": "quote_ready", "id": "abc", "link": "/quotes/abc"},
    )

    assert len(calls) == 1
    assert calls[0]["url"] == "https://exp.host/--/api/v2/push/send"
    message = calls[0]["json"][0]
    assert message["to"] == "ExponentPushToken[device1]"
    assert message["title"] == "Quote ready for review"
    assert message["sound"] == "default"
    assert message["priority"] == "high"
    assert message["data"] == {"type": "quote_ready", "id": "abc", "link": "/quotes/abc"}
    # No badge unless the caller supplies one.
    assert "badge" not in message


async def test_send_expo_push_includes_badge_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unread count rides in the payload so iOS badges the app icon."""
    calls = _stub_expo(monkeypatch, _FakeExpoResponse(payload={"data": [{"status": "ok"}]}))

    await send_expo_push(["ExponentPushToken[device1]"], "T", "B", badge=4)

    assert calls[0]["json"][0]["badge"] == 4


async def test_send_expo_push_http_error_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-200 from Expo is logged and swallowed, never raised."""
    calls = _stub_expo(monkeypatch, _FakeExpoResponse(status_code=500, payload={"errors": []}))

    await send_expo_push(["ExponentPushToken[device1]"], "T", "B")

    assert len(calls) == 1  # the attempt happened; failure was contained


async def test_send_expo_push_removes_device_not_registered_tokens(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expo DeviceNotRegistered tickets delete the dead token, keep the live one."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_push_token(db, tenant_id, "staff", uuid4(), "ExponentPushToken[live]")
    await _seed_push_token(db, tenant_id, "staff", uuid4(), "ExponentPushToken[dead]")
    response = _FakeExpoResponse(
        payload={
            "data": [
                {"status": "ok", "id": "ticket-1"},
                {
                    "status": "error",
                    "id": "ticket-2",
                    "message": "The device cannot receive push notifications anymore",
                    "details": {"error": "DeviceNotRegistered"},
                },
            ]
        }
    )
    _stub_expo(monkeypatch, response)

    await send_expo_push(["ExponentPushToken[live]", "ExponentPushToken[dead]"], "T", "B", db=db)
    await db.flush()

    await set_tenant_in_session(db, tenant_id)
    remaining = (
        (await db.execute(select(PushToken.token).where(PushToken.tenant_id == tenant_id)))
        .scalars()
        .all()
    )
    assert list(remaining) == ["ExponentPushToken[live]"]


async def test_notify_staff_push_data_includes_type_and_id(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_push_token(db, tenant_id, "staff", uuid4(), "ExponentPushToken[staff1]")
    # Another tenant's staff token must not be targeted.
    created = await admin_client.post(
        "/tenants", json={"slug": f"other-{uuid4().hex[:8]}", "name": "Other Ltd"}
    )
    assert created.status_code == 201
    await _seed_push_token(
        db, UUID(created.json()["id"]), "staff", uuid4(), "ExponentPushToken[foreign]"
    )
    calls = _stub_expo(monkeypatch, _FakeExpoResponse(payload={"data": [{"status": "ok"}]}))

    quote_id = uuid4()
    await set_tenant_in_session(db, tenant_id)
    await notify_staff(
        db,
        tenant_id,
        kind="quote_ready",
        title="Quote ready for review",
        body="AI draft quote is ready.",
        link=f"/quotes/{quote_id}",
    )
    await db.flush()

    assert len(calls) == 1
    messages = calls[0]["json"]
    assert [m["to"] for m in messages] == ["ExponentPushToken[staff1]"]
    assert messages[0]["data"] == {
        "type": "quote_ready",
        "id": str(quote_id),
        "link": f"/quotes/{quote_id}",
    }

    rows = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id, Notification.type == "quote_ready"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].recipient_type == "staff"


async def test_notify_customer_targets_only_that_customer(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    customer = await _seed_customer(db, tenant_id)
    await _seed_push_token(db, tenant_id, "customer", customer.id, "ExponentPushToken[cust1]")
    await _seed_push_token(db, tenant_id, "customer", uuid4(), "ExponentPushToken[cust2]")
    await _seed_push_token(db, tenant_id, "staff", uuid4(), "ExponentPushToken[staff1]")
    calls = _stub_expo(monkeypatch, _FakeExpoResponse(payload={"data": [{"status": "ok"}]}))

    await set_tenant_in_session(db, tenant_id)
    await notify_customer(
        db,
        tenant_id,
        customer.id,
        kind="chat_reply",
        title="New message",
        body="Could you share more details?",
        link=f"/chat/{uuid4()}",
    )

    assert len(calls) == 1
    messages = calls[0]["json"]
    assert [m["to"] for m in messages] == ["ExponentPushToken[cust1]"]
    assert messages[0]["data"]["type"] == "chat_reply"


async def test_notify_quote_ready_pushes_staff_and_customer(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The async quote-ready path pushes BOTH staff and the linked customer."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    customer = await _seed_customer(db, tenant_id)
    await set_tenant_in_session(db, tenant_id)
    quote_request = QuoteRequest(
        tenant_id=tenant_id, customer_id=customer.id, raw_text="Rewire please"
    )
    db.add(quote_request)
    await db.flush()
    await _seed_push_token(db, tenant_id, "staff", uuid4(), "ExponentPushToken[staff1]")
    await _seed_push_token(db, tenant_id, "customer", customer.id, "ExponentPushToken[cust1]")
    calls = _stub_expo(monkeypatch, _FakeExpoResponse(payload={"data": [{"status": "ok"}]}))

    quote = _quote_read(tenant_id, quote_request_id=quote_request.id)
    await _notify_quote_ready(db, tenant_id, quote, quote_request.id)
    await db.flush()

    # Two batches: staff first, then the customer.
    assert len(calls) == 2
    assert [m["to"] for m in calls[0]["json"]] == ["ExponentPushToken[staff1]"]
    assert calls[0]["json"][0]["data"]["type"] == "quote_ready"
    assert calls[0]["json"][0]["data"]["id"] == str(quote.id)
    assert [m["to"] for m in calls[1]["json"]] == ["ExponentPushToken[cust1]"]
    assert calls[1]["json"][0]["title"] == "Your quote is ready"
    assert calls[1]["json"][0]["data"]["type"] == "quote_ready"

    # Both in-app notification rows were recorded too.
    rows = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id, Notification.type == "quote_ready"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {row.recipient_type for row in rows} == {"staff", "customer"}


async def test_notify_quote_failed_sends_push(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed generation now pushes staff, not just an in-app row."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_push_token(db, tenant_id, "staff", uuid4(), "ExponentPushToken[staff1]")
    calls = _stub_expo(monkeypatch, _FakeExpoResponse(payload={"data": [{"status": "ok"}]}))

    await _notify_quote_failed(db, tenant_id)
    await db.flush()

    assert len(calls) == 1
    message = calls[0]["json"][0]
    assert message["to"] == "ExponentPushToken[staff1]"
    assert message["title"] == "Quote generation failed"
    assert message["data"]["type"] == "quote_failed"
    assert message["data"]["id"] == ""
    assert message["sound"] == "default"

    row = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant_id, Notification.type == "quote_failed"
        )
    )
    assert row is not None
    assert row.link is None
