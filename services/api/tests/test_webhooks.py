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


# --- Flat pricing: price→plan re-derivation (no overage billing) -------------

_NEW_PRICE_ENV_VARS = (
    "PADDLE_PRICE_ID_SOLE_TRADER_MONTH",
    "PADDLE_PRICE_ID_SOLE_TRADER_YEAR",
    "PADDLE_PRICE_ID_PRO_MONTH",
    "PADDLE_PRICE_ID_PRO_YEAR",
    "PADDLE_PRICE_ID_TEAM_MONTH",
    "PADDLE_PRICE_ID_TEAM_YEAR",
)


@pytest.fixture
def clean_price_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in _NEW_PRICE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


async def test_plan_key_for_price_id_new_catalog(clean_price_env: pytest.MonkeyPatch) -> None:
    from app.routers.webhooks import _plan_key_for_price_id

    clean_price_env.setenv("PADDLE_PRICE_ID_SOLE_TRADER_MONTH", "pri_w2b_st_m")
    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_YEAR", "pri_w2b_pro_y")
    clean_price_env.setenv("PADDLE_PRICE_ID_TEAM_MONTH", "pri_w2b_team_m")

    assert _plan_key_for_price_id("pri_w2b_st_m") == "sole_trader"
    assert _plan_key_for_price_id("pri_w2b_pro_y") == "pro"
    assert _plan_key_for_price_id("pri_w2b_team_m") == "team"


async def test_plan_key_for_price_id_legacy_vars(clean_price_env: pytest.MonkeyPatch) -> None:
    from app.routers.webhooks import _plan_key_for_price_id

    clean_price_env.setattr(
        "app.routers.webhooks.settings.paddle_price_id_starter", "pri_legacy_starter"
    )
    clean_price_env.setattr("app.routers.webhooks.settings.paddle_price_id_pro", "pri_legacy_pro")
    clean_price_env.setattr(
        "app.routers.webhooks.settings.paddle_price_id_business", "pri_legacy_business"
    )

    # Legacy price ids resolve onto the current catalog keys.
    assert _plan_key_for_price_id("pri_legacy_starter") == "sole_trader"
    assert _plan_key_for_price_id("pri_legacy_pro") == "pro"
    assert _plan_key_for_price_id("pri_legacy_business") == "team"


async def test_plan_key_for_price_id_unknown(clean_price_env: pytest.MonkeyPatch) -> None:
    from app.routers.webhooks import _plan_key_for_price_id

    assert _plan_key_for_price_id("pri_not_configured") is None
    assert _plan_key_for_price_id("") is None
    assert _plan_key_for_price_id(None) is None


async def _make_subscription(plan_key: str = "starter") -> str:
    """Create a tenant + subscription via the app engine; return the paddle sub id."""
    from app.database import engine
    from app.models import Subscription, Tenant
    from sqlalchemy.ext.asyncio import AsyncSession

    paddle_sub_id = f"sub_{uuid4().hex[:16]}"
    async with AsyncSession(engine) as session:
        tenant = Tenant(slug=f"wh-{uuid4().hex[:8]}", name="Webhook Co")
        session.add(tenant)
        await session.flush()
        session.add(
            Subscription(
                tenant_id=tenant.id,
                plan_key=plan_key,
                status="trialing",
                paddle_subscription_id=paddle_sub_id,
            )
        )
        await session.commit()
    return paddle_sub_id


async def _fetch_subscription(paddle_sub_id: str) -> dict[str, Any]:
    """Read a subscription row back as plain data (session closes on return)."""
    from app.database import engine
    from app.models import Subscription
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as session:
        row = await session.scalar(
            select(Subscription).where(Subscription.paddle_subscription_id == paddle_sub_id)
        )
        assert row is not None
        return {
            "plan_key": row.plan_key,
            "status": row.status,
            "paddle_price_id": row.paddle_price_id,
            "provider_payload": row.provider_payload,
        }


async def test_upsert_subscription_rederives_plan_key_from_new_price(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    """A subscription event carrying a new-catalog price rewrites plan_key."""
    from app.routers.webhooks import _upsert_subscription

    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_MONTH", "pri_w2b_pro_m")
    paddle_sub_id = await _make_subscription(plan_key="starter")

    await _upsert_subscription(
        "subscription.updated",
        {
            "id": paddle_sub_id,
            "status": "active",
            "items": [{"price": {"id": "pri_w2b_pro_m", "product_id": "pro_w2b_pro"}}],
        },
    )

    row = await _fetch_subscription(paddle_sub_id)
    assert row["plan_key"] == "pro"
    assert row["status"] == "active"
    assert row["paddle_price_id"] == "pri_w2b_pro_m"


async def test_upsert_subscription_rederives_plan_key_from_legacy_price(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    from app.routers.webhooks import _upsert_subscription

    clean_price_env.setattr(
        "app.routers.webhooks.settings.paddle_price_id_business", "pri_legacy_business"
    )
    paddle_sub_id = await _make_subscription(plan_key="pro")

    await _upsert_subscription(
        "subscription.updated",
        {
            "id": paddle_sub_id,
            "status": "active",
            "items": [{"price": {"id": "pri_legacy_business", "product_id": "pro_legacy"}}],
        },
    )

    row = await _fetch_subscription(paddle_sub_id)
    assert row["plan_key"] == "team"


async def test_upsert_subscription_keeps_plan_key_for_unknown_price(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    from app.routers.webhooks import _upsert_subscription

    paddle_sub_id = await _make_subscription(plan_key="pro")

    await _upsert_subscription(
        "subscription.updated",
        {
            "id": paddle_sub_id,
            "status": "active",
            "items": [{"price": {"id": "pri_unmapped", "product_id": "pro_x"}}],
        },
    )

    row = await _fetch_subscription(paddle_sub_id)
    assert row["plan_key"] == "pro"


async def test_paddle_webhook_accepts_transaction_billed_without_handler(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    """Flat pricing has no overage ledger: transaction.billed renewals are
    verified, deduped and acknowledged without touching subscription state."""
    secret = "whsec_billed_secret"
    payload = {
        "event_id": f"evt_{uuid4().hex}",
        "event_type": "transaction.billed",
        "data": {"id": "txn_billed_1", "subscription_id": "sub_x", "items": []},
    }
    body = json.dumps(payload).encode()
    signature = _make_signature_payload(secret, body)

    clean_price_env.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/paddle",
            content=body,
            headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
