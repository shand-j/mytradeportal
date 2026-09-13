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


# --- Recorded-shape Paddle contract fixtures -----------------------------------
#
# Payloads below mirror what Paddle Billing actually delivers (envelope +
# entity bodies), per the Paddle webhook docs: ``event_id``/``event_type``/
# ``occurred_at``/``notification_id`` envelope, and entity ``data`` with
# ``pri_``/``pro_``/``ctm_``/``sub_``/``txn_``-prefixed ids. They are the
# contract the handler must keep accepting; no live Paddle calls are made.


def _envelope(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """A Paddle webhook envelope in the shape Paddle actually POSTs."""
    return {
        "event_id": f"evt_{uuid4().hex[:24]}",
        "event_type": event_type,
        "occurred_at": "2026-09-13T10:15:00.000000Z",
        "notification_id": f"ntf_{uuid4().hex[:24]}",
        "data": data,
    }


def _price_entity(price_id: str, product_id: str, *, interval: str = "month") -> dict[str, Any]:
    return {
        "id": price_id,
        "product_id": product_id,
        "name": "Pro Monthly",
        "type": "standard",
        "billing_cycle": {"interval": interval, "frequency": 1},
        "trial_period": {"interval": "day", "frequency": 14},
        "tax_mode": "account_setting",
        "unit_price": {"amount": "3900", "currency_code": "GBP"},
        "quantity": {"minimum": 1, "maximum": 1},
        "status": "active",
        "custom_data": None,
    }


def _subscription_data(
    *,
    status: str = "trialing",
    price_id: str = "pri_test_pro",
    product_id: str = "pro_test_pro",
    tenant_id: str | None = None,
    customer_id: str = "ctm_01jsubcust0000000000000",
    canceled_at: str | None = None,
    scheduled_change: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A ``data`` body in Paddle's recorded subscription shape."""
    return {
        "id": f"sub_{uuid4().hex[:24]}",
        "status": status,
        "customer_id": customer_id,
        "address_id": "add_01jaddr0000000000000000",
        "business_id": None,
        "currency_code": "GBP",
        "created_at": "2026-09-13T10:00:00.000000Z",
        "updated_at": "2026-09-13T10:15:00.000000Z",
        "started_at": "2026-09-13T10:00:00.000000Z",
        "first_billed_at": None,
        "next_billed_at": "2026-10-13T10:00:00.000000Z",
        "paused_at": None,
        "canceled_at": canceled_at,
        "collection_mode": "automatic",
        "billing_details": None,
        "current_billing_period": {
            "starts_at": "2026-09-13T10:00:00.000000Z",
            "ends_at": "2026-10-13T10:00:00.000000Z",
        },
        "billing_cycle": {"interval": "month", "frequency": 1},
        "scheduled_change": scheduled_change,
        "items": [
            {
                "status": status,
                "quantity": 1,
                "recurring": True,
                "created_at": "2026-09-13T10:00:00.000000Z",
                "updated_at": "2026-09-13T10:15:00.000000Z",
                "previously_billed_at": None,
                "next_billed_at": "2026-10-13T10:00:00.000000Z",
                "trial_dates": {
                    "starts_at": "2026-09-13T10:00:00.000000Z",
                    "ends_at": "2026-09-27T10:00:00.000000Z",
                },
                "price": _price_entity(price_id, product_id),
                "product": {"id": product_id, "name": "My Trade Portal"},
            }
        ],
        "custom_data": {"tenant_id": tenant_id} if tenant_id else None,
    }


def _transaction_data(
    *,
    status: str = "completed",
    invoice_id: str | None = None,
    subscription_id: str | None = None,
) -> dict[str, Any]:
    """A ``data`` body in Paddle's recorded transaction shape."""
    return {
        "id": f"txn_{uuid4().hex[:24]}",
        "status": status,
        "customer_id": "ctm_01jtxncust0000000000000",
        "address_id": "add_01jaddr0000000000000000",
        "business_id": None,
        "currency_code": "GBP",
        "origin": "subscription_recurring",
        "subscription_id": subscription_id,
        "invoice_id": f"inv_{uuid4().hex[:24]}",
        "invoice_number": "INV-1000-0001",
        "collection_mode": "automatic",
        "discount_id": None,
        "billing_details": {
            "enable_checkout": False,
            "purchase_order_number": None,
            "additional_information": None,
            "payment_terms": {"interval": "day", "frequency": 14},
        },
        "billing_period": {
            "starts_at": "2026-09-13T10:00:00.000000Z",
            "ends_at": "2026-10-13T10:00:00.000000Z",
        },
        "items": [
            {
                "price_id": "pri_test_pro",
                "quantity": 1,
                "proration": None,
            }
        ],
        "details": {
            "line_items": [
                {
                    "price_id": "pri_test_pro",
                    "quantity": 1,
                    "totals": {"subtotal": "3900", "discount": "0", "tax": "780", "total": "4680"},
                }
            ],
            "payout_totals": None,
            "tax_rates_used": [{"tax_rate": "0.20", "totals": {"subtotal": "3900", "tax": "780"}}],
            "totals": {
                "subtotal": "3900",
                "discount": "0",
                "tax": "780",
                "total": "4680",
                "grand_total": "4680",
                "fee": None,
                "earnings": None,
                "currency_code": "GBP",
            },
            "adjusted_totals": None,
        },
        "payments": [
            {
                "payment_attempt_id": f"payatt_{uuid4().hex[:20]}",
                "stored_payment_method_id": "paymtd_01jpm00000000000000000",
                "amount": "4680",
                "status": "captured",
            }
        ],
        "checkout": {"url": None},
        "created_at": "2026-09-13T10:00:00.000000Z",
        "updated_at": "2026-09-13T10:00:05.000000Z",
        "billed_at": "2026-09-13T10:00:00.000000Z",
        "revised_at": None,
        "custom_data": {"invoice_id": invoice_id} if invoice_id else None,
        "receipt_data": None,
    }


async def _post_paddle(client: AsyncClient, payload: dict[str, Any], secret: str) -> Any:
    """POST an envelope to the webhook endpoint with a valid signature."""
    body = json.dumps(payload).encode()
    signature = _make_signature_payload(secret, body)
    return await client.post(
        "/webhooks/paddle",
        content=body,
        headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
    )


async def _make_tenant_with_subscription(
    plan_key: str = "sole_trader",
    status: str = "incomplete",
    *,
    paddle_sub_id: str | None = None,
) -> str:
    """Committed tenant + subscription via the app engine; returns tenant id."""
    from app.database import engine
    from app.models import Subscription, Tenant
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as session:
        tenant = Tenant(slug=f"wh-{uuid4().hex[:8]}", name="Webhook Contract Co")
        session.add(tenant)
        await session.flush()
        session.add(
            Subscription(
                tenant_id=tenant.id,
                plan_key=plan_key,
                status=status,
                paddle_subscription_id=paddle_sub_id,
                provider_payload={"source": "contract_test"},
            )
        )
        tenant_id = str(tenant.id)  # capture before commit expires the ORM state
        await session.commit()
        return tenant_id


async def _fetch_subscription_by_tenant(tenant_id: str) -> dict[str, Any]:
    """Read a subscription row back as plain data (session closes on return)."""
    from uuid import UUID

    from app.database import engine
    from app.models import Subscription
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as session:
        row = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == UUID(tenant_id))
        )
        assert row is not None
        return {
            "plan_key": row.plan_key,
            "status": row.status,
            "paddle_subscription_id": row.paddle_subscription_id,
            "paddle_customer_id": row.paddle_customer_id,
            "paddle_price_id": row.paddle_price_id,
            "paddle_product_id": row.paddle_product_id,
            "trial_ends_at": row.trial_ends_at,
            "current_period_start": row.current_period_start,
            "current_period_end": row.current_period_end,
            "scheduled_change_action": row.scheduled_change_action,
            "scheduled_change_at": row.scheduled_change_at,
            "canceled_at": row.canceled_at,
            "provider_payload": row.provider_payload,
        }


async def test_all_six_new_price_ids_map_to_plans(clean_price_env: pytest.MonkeyPatch) -> None:
    """Every PADDLE_PRICE_ID_{SOLE_TRADER,PRO,TEAM}_{MONTH,YEAR} value maps
    onto its tier; legacy vars fill gaps but never override the new ids."""
    from app.routers.webhooks import _plan_key_for_price_id, _price_id_plan_map

    cases = {
        "PADDLE_PRICE_ID_SOLE_TRADER_MONTH": ("pri_c_st_m", "sole_trader"),
        "PADDLE_PRICE_ID_SOLE_TRADER_YEAR": ("pri_c_st_y", "sole_trader"),
        "PADDLE_PRICE_ID_PRO_MONTH": ("pri_c_pro_m", "pro"),
        "PADDLE_PRICE_ID_PRO_YEAR": ("pri_c_pro_y", "pro"),
        "PADDLE_PRICE_ID_TEAM_MONTH": ("pri_c_team_m", "team"),
        "PADDLE_PRICE_ID_TEAM_YEAR": ("pri_c_team_y", "team"),
    }
    for env_name, (price_id, _) in cases.items():
        clean_price_env.setenv(env_name, price_id)

    for price_id, tier in cases.values():
        assert _plan_key_for_price_id(price_id) == tier

    # A legacy var pointing at the same tier's old price still resolves, and
    # never clobbers a new-catalog id sharing the tier.
    clean_price_env.setattr("app.routers.webhooks.settings.paddle_price_id_pro", "pri_c_legacy_pro")
    mapping = _price_id_plan_map()
    assert mapping["pri_c_legacy_pro"] == "pro"
    assert mapping["pri_c_pro_m"] == "pro"


async def test_recorded_subscription_created_hydrates_checkout_row(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    """A recorded-shape subscription.created (keyed on custom_data.tenant_id)
    hydrates the incomplete checkout row: status, paddle ids, plan derived
    from the price id, trial + period dates."""
    secret = "whsec_contract_created"
    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_MONTH", "pri_contract_pro_m")
    clean_price_env.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    tenant_id = await _make_tenant_with_subscription(plan_key="sole_trader")
    data = _subscription_data(
        status="active",
        price_id="pri_contract_pro_m",
        product_id="pro_contract_pro",
        tenant_id=tenant_id,
    )
    payload = _envelope("subscription.created", data)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"

    row = await _fetch_subscription_by_tenant(tenant_id)
    assert row["status"] == "active"
    assert row["plan_key"] == "pro"  # re-derived from the price id
    assert row["paddle_subscription_id"] == data["id"]
    assert row["paddle_customer_id"] == data["customer_id"]
    assert row["paddle_price_id"] == "pri_contract_pro_m"
    assert row["paddle_product_id"] == "pro_contract_pro"
    assert row["trial_ends_at"] is not None
    assert row["trial_ends_at"].isoformat().startswith("2026-09-27")
    assert row["current_period_start"].isoformat().startswith("2026-09-13")
    assert row["current_period_end"].isoformat().startswith("2026-10-13")
    assert row["provider_payload"]["id"] == data["id"]


async def test_recorded_subscription_updated_applies_scheduled_change(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    """subscription.updated re-keys on paddle_subscription_id and records a
    scheduled downgrade/cancellation without mutating it prematurely."""
    secret = "whsec_contract_updated"
    clean_price_env.setenv("PADDLE_PRICE_ID_TEAM_MONTH", "pri_contract_team_m")
    clean_price_env.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    paddle_sub_id = f"sub_{uuid4().hex[:24]}"
    tenant_id = await _make_tenant_with_subscription(
        plan_key="team", status="active", paddle_sub_id=paddle_sub_id
    )
    data = _subscription_data(
        status="active",
        price_id="pri_contract_team_m",
        product_id="pro_contract_team",
        tenant_id=None,  # custom_data stripped: must re-key on sub id
        scheduled_change={
            "action": "cancel",
            "effective_at": "2026-10-13T10:00:00.000000Z",
            "resume_at": None,
        },
    )
    data["id"] = paddle_sub_id
    payload = _envelope("subscription.updated", data)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    row = await _fetch_subscription_by_tenant(tenant_id)
    assert row["status"] == "active"  # not canceled yet — only scheduled
    assert row["plan_key"] == "team"
    assert row["scheduled_change_action"] == "cancel"
    assert row["scheduled_change_at"].isoformat().startswith("2026-10-13")


async def test_recorded_subscription_canceled_sets_canceled_at(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    secret = "whsec_contract_canceled"
    clean_price_env.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    paddle_sub_id = f"sub_{uuid4().hex[:24]}"
    tenant_id = await _make_tenant_with_subscription(
        plan_key="pro", status="active", paddle_sub_id=paddle_sub_id
    )
    data = _subscription_data(
        status="canceled",
        canceled_at="2026-09-13T10:15:00.000000Z",
    )
    data["id"] = paddle_sub_id
    payload = _envelope("subscription.canceled", data)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    row = await _fetch_subscription_by_tenant(tenant_id)
    assert row["status"] == "canceled"
    assert row["canceled_at"].isoformat().startswith("2026-09-13T10:15")
    assert row["plan_key"] == "pro"  # unknown price id: stored plan survives


async def test_recorded_transaction_completed_routes_to_payment_recording(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    """A recorded-shape transaction.completed reaches _record_payment with
    the full entity body intact."""
    secret = "whsec_contract_txn"
    clean_price_env.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    invoice_id = str(uuid4())
    data = _transaction_data(invoice_id=invoice_id)
    payload = _envelope("transaction.completed", data)

    recorded: dict[str, Any] = {}

    async def fake_record_payment(inv_id: str, event_data: dict[str, Any]) -> None:
        recorded["invoice_id"] = inv_id
        recorded["event_data"] = event_data

    clean_price_env.setattr("app.routers.webhooks._record_payment", fake_record_payment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    assert recorded["invoice_id"] == invoice_id
    assert recorded["event_data"]["id"] == data["id"]
    assert recorded["event_data"]["details"]["totals"]["total"] == "4680"


async def test_recorded_transaction_billed_mutates_no_state(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    """Flat pricing has NO overage ledger: transaction.billed renewals are
    verified, deduped and acknowledged, and leave the subscription row
    (plan, status, price, payload) bit-for-bit untouched."""
    secret = "whsec_contract_billed"
    clean_price_env.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    paddle_sub_id = f"sub_{uuid4().hex[:24]}"
    tenant_id = await _make_tenant_with_subscription(
        plan_key="pro", status="active", paddle_sub_id=paddle_sub_id
    )
    before = await _fetch_subscription_by_tenant(tenant_id)

    data = _transaction_data(status="billed", subscription_id=paddle_sub_id)
    payload = _envelope("transaction.billed", data)

    async def fail_record_payment(inv_id: str, event_data: dict[str, Any]) -> None:
        raise AssertionError("billed events must never reach the payment recorder")

    async def fail_upsert(event_type: str, event_data: dict[str, Any]) -> None:
        raise AssertionError("billed events must never reach the subscription upsert")

    clean_price_env.setattr("app.routers.webhooks._record_payment", fail_record_payment)
    clean_price_env.setattr("app.routers.webhooks._upsert_subscription", fail_upsert)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"

    after = await _fetch_subscription_by_tenant(tenant_id)
    assert after == before


async def test_unknown_price_id_keeps_stored_plan_via_endpoint(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    """Safe fallback: a subscription.updated carrying an unmapped price id is
    accepted, status syncs, but the stored plan key is not clobbered."""
    secret = "whsec_contract_unknown"
    clean_price_env.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    paddle_sub_id = f"sub_{uuid4().hex[:24]}"
    tenant_id = await _make_tenant_with_subscription(
        plan_key="pro", status="trialing", paddle_sub_id=paddle_sub_id
    )
    data = _subscription_data(status="active", price_id="pri_unmapped_zzz")
    data["id"] = paddle_sub_id
    payload = _envelope("subscription.updated", data)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    row = await _fetch_subscription_by_tenant(tenant_id)
    assert row["status"] == "active"
    assert row["plan_key"] == "pro"
    assert row["paddle_price_id"] == "pri_unmapped_zzz"


async def test_tampered_payload_rejected_despite_valid_signature_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sign body A, deliver body B: the HMAC no longer matches and the
    endpoint must 401 — the only thing standing between us and forged
    subscription state."""
    secret = "whsec_tamper"
    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)

    original = _envelope("transaction.completed", _transaction_data(invoice_id=str(uuid4())))
    body = json.dumps(original).encode()
    signature = _make_signature_payload(secret, body)

    tampered = json.loads(body)
    tampered["data"]["details"]["totals"]["total"] = "1"  # attacker drops the amount
    tampered_body = json.dumps(tampered).encode()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/paddle",
            content=tampered_body,
            headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
        )

    assert response.status_code == 401
