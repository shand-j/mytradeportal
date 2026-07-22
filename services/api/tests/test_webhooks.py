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
