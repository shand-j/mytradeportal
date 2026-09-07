"""Tests for Paddle webhook signature verification and endpoint handling."""

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from app.main import app
from app.paddle_client import parse_webhook_event, verify_webhook_signature
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


def _make_signature_payload(secret: str, body: bytes, timestamp: str = "1234567890") -> str:
    signature = hmac.new(
        secret.encode(), f"{timestamp}:".encode() + body, hashlib.sha256
    ).hexdigest()
    return f"ts={timestamp};h1={signature}"


async def test_verify_webhook_signature_valid() -> None:
    secret = "whsec_test_secret"
    body = b'{"event_type":"transaction.completed"}'
    header = _make_signature_payload(secret, body)

    assert verify_webhook_signature(body, header, secret) is True


async def test_verify_webhook_signature_invalid() -> None:
    secret = "whsec_test_secret"
    body = b'{"event_type":"transaction.completed"}'
    header = "ts=1234567890;h1=0000000000000000000000000000000000000000000000000000000000000000"

    assert verify_webhook_signature(body, header, secret) is False


async def test_parse_webhook_event() -> None:
    payload = {"event_type": "transaction.completed", "data": {"id": "txn_123"}}
    body = json.dumps(payload).encode()

    event = parse_webhook_event(body)

    assert event["event_type"] == "transaction.completed"
    assert event["data"]["id"] == "txn_123"


async def test_paddle_webhook_endpoint_accepts_valid_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "whsec_endpoint_secret"
    invoice_id = str(uuid4())
    payload = {
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_123",
            "currency_code": "GBP",
            "details": {"totals": {"total": "198000"}},
            "custom_data": {"invoice_id": invoice_id},
            "checkout": {"id": "chk_123"},
        },
    }
    body = json.dumps(payload).encode()
    signature = _make_signature_payload(secret, body)

    recorded: dict[str, Any] = {}

    async def fake_record_payment(inv_id: str, event_data: dict[str, Any]) -> None:
        recorded["invoice_id"] = inv_id
        recorded["amount"] = Decimal(event_data["details"]["totals"]["total"]) / 100

    monkeypatch.setattr("app.routers.webhooks._record_payment", fake_record_payment)
    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/paddle",
            content=body,
            headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert recorded["invoice_id"] == invoice_id
    assert recorded["amount"] == Decimal("1980.00")


async def test_paddle_webhook_endpoint_rejects_bad_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"event_type":"transaction.completed","data":{}}'

    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", "secret")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/paddle",
            content=body,
            headers={"Paddle-Signature": "ts=1;h1=bad", "Content-Type": "application/json"},
        )

    assert response.status_code == 401


async def test_paddle_webhook_dedupes_repeated_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeat delivery of the same ``event_id`` returns 200 with status=duplicate."""
    secret = "whsec_dedupe_secret"
    payload = {
        "event_id": f"evt_{uuid4().hex}",
        "event_type": "subscription.created",
        "data": {"id": "sub_dupe_1", "custom_data": {"tenant_id": str(uuid4())}},
    }
    body = json.dumps(payload).encode()
    signature = _make_signature_payload(secret, body)

    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    upsert_calls: list[Any] = []

    async def fake_upsert(event_type: str, event_data: dict[str, Any]) -> None:
        upsert_calls.append((event_type, event_data))

    monkeypatch.setattr("app.routers.webhooks._upsert_subscription", fake_upsert)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/webhooks/paddle",
            content=body,
            headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
        )
        second = await client.post(
            "/webhooks/paddle",
            content=body,
            headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
        )

    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    # Handler ran exactly once.
    assert len(upsert_calls) == 1


async def test_paddle_webhook_routes_subscription_created_to_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """subscription.created events go to the subscription upsert path, not the invoice one."""
    secret = "whsec_sub_secret"
    payload = {
        "event_id": f"evt_{uuid4().hex}",
        "event_type": "subscription.created",
        "data": {
            "id": "sub_test_created",
            "status": "trialing",
            "customer_id": "ctm_test",
            "custom_data": {"tenant_id": str(uuid4()), "plan_key": "pro"},
            "items": [
                {
                    "price": {"id": "pri_test", "product_id": "pro_test"},
                    "trial_dates": {"ends_at": "2027-01-01T00:00:00Z"},
                }
            ],
            "current_billing_period": {
                "starts_at": "2026-09-07T00:00:00Z",
                "ends_at": "2026-10-07T00:00:00Z",
            },
        },
    }
    body = json.dumps(payload).encode()
    signature = _make_signature_payload(secret, body)

    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    seen: dict[str, Any] = {}

    async def fake_upsert(event_type: str, event_data: dict[str, Any]) -> None:
        seen["event_type"] = event_type
        seen["event_data"] = event_data

    async def fake_record_payment(inv_id: str, event_data: dict[str, Any]) -> None:
        raise AssertionError("record_payment should not be called for subscription events")

    monkeypatch.setattr("app.routers.webhooks._upsert_subscription", fake_upsert)
    monkeypatch.setattr("app.routers.webhooks._record_payment", fake_record_payment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/paddle",
            content=body,
            headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert seen["event_type"] == "subscription.created"
    assert seen["event_data"]["id"] == "sub_test_created"
