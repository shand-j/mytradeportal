"""Tests for the tenant-subscription billing endpoints."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.models import Subscription
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_checkout_returns_paddle_url(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /billing/checkout hands back a Paddle-hosted URL for the plan."""
    monkeypatch.setattr("app.routers.billing.settings.paddle_price_id_pro", "pri_test_pro")
    monkeypatch.setattr("app.routers.billing.settings.paddle_beta_discount_id", "")

    fake = AsyncMock(
        return_value={"transaction_id": "txn_test_1", "checkout_url": "https://pay.paddle.com/x"}
    )

    with patch("app.routers.billing.create_subscription_transaction", new=fake):
        response = await admin_client.post("/billing/checkout", json={"plan_key": "pro"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transaction_id"] == "txn_test_1"
    assert body["checkout_url"].startswith("https://")

    # An incomplete subscription row must be pre-created so the webhook can
    # find and hydrate it.
    tenant_id = admin_client.headers["X-Tenant-ID"]
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    assert sub is not None
    assert sub.plan_key == "pro"
    assert sub.status == "incomplete"
    assert sub.paddle_transaction_id == "txn_test_1"
    assert sub.paddle_price_id == "pri_test_pro"

    # The Paddle client was called with the tenant_id in custom_data so the
    # webhook can key back on it. No discount when unset.
    _, kwargs = fake.call_args
    assert kwargs["plan_key"] == "pro"
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["price_id"] == "pri_test_pro"
    assert kwargs["discount_id"] is None


async def test_checkout_applies_beta_discount_when_configured(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When PADDLE_BETA_DISCOUNT_ID is set, every checkout auto-applies it."""
    monkeypatch.setattr("app.routers.billing.settings.paddle_price_id_pro", "pri_test_pro")
    monkeypatch.setattr("app.routers.billing.settings.paddle_beta_discount_id", "dsc_test_beta")

    fake = AsyncMock(
        return_value={"transaction_id": "txn_test_beta", "checkout_url": "https://pay.paddle.com/x"}
    )
    with patch("app.routers.billing.create_subscription_transaction", new=fake):
        response = await admin_client.post("/billing/checkout", json={"plan_key": "pro"})

    assert response.status_code == 200
    _, kwargs = fake.call_args
    assert kwargs["discount_id"] == "dsc_test_beta"


async def test_checkout_rejects_unknown_plan(admin_client: AsyncClient) -> None:
    """Unknown plan keys 400 before any Paddle round-trip."""
    response = await admin_client.post("/billing/checkout", json={"plan_key": "enterprise"})
    assert response.status_code == 400
    assert "Unknown" in response.json()["detail"] or "unconfigured" in response.json()["detail"]


async def test_checkout_rejects_unconfigured_plan(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A known plan with no price id in settings 400s."""
    monkeypatch.setattr("app.routers.billing.settings.paddle_price_id_starter", "")
    response = await admin_client.post("/billing/checkout", json={"plan_key": "starter"})
    assert response.status_code == 400


async def test_checkout_bubbles_paddle_failure_as_502(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paddle client raising surfaces as 502 (Bad Gateway)."""
    monkeypatch.setattr("app.routers.billing.settings.paddle_price_id_pro", "pri_test_pro")

    fake = AsyncMock(side_effect=RuntimeError("paddle 500"))
    with patch("app.routers.billing.create_subscription_transaction", new=fake):
        response = await admin_client.post("/billing/checkout", json={"plan_key": "pro"})

    assert response.status_code == 502


async def test_get_subscription_returns_none_when_missing(admin_client: AsyncClient) -> None:
    """New tenants with no sub row see ``null`` — a legitimate state."""
    response = await admin_client.get("/billing/subscription")
    assert response.status_code == 200
    assert response.json() is None


async def test_get_subscription_returns_state_when_present(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """After a checkout + webhook has hydrated the row, GET returns it."""
    tenant_id = admin_client.headers["X-Tenant-ID"]
    from datetime import datetime, timedelta
    from uuid import UUID

    from app.rls import set_tenant_in_session

    await set_tenant_in_session(db, UUID(tenant_id))
    sub = Subscription(
        tenant_id=UUID(tenant_id),
        plan_key="pro",
        status="trialing",
        paddle_subscription_id="sub_test_1",
        paddle_customer_id="ctm_test_1",
        trial_ends_at=datetime.utcnow() + timedelta(days=14),
    )
    db.add(sub)
    await db.commit()

    response = await admin_client.get("/billing/subscription")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["plan_key"] == "pro"
    assert body["status"] == "trialing"
    assert body["paddle_subscription_id"] == "sub_test_1"


async def test_repeat_checkout_reuses_subscription_row(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second /billing/checkout call updates the same row (no duplicates)."""
    monkeypatch.setattr("app.routers.billing.settings.paddle_price_id_starter", "pri_test_starter")
    monkeypatch.setattr("app.routers.billing.settings.paddle_price_id_pro", "pri_test_pro")

    fake = AsyncMock(
        return_value={"transaction_id": "txn_1", "checkout_url": "https://pay.paddle.com/a"}
    )
    with patch("app.routers.billing.create_subscription_transaction", new=fake):
        await admin_client.post("/billing/checkout", json={"plan_key": "starter"})
        await admin_client.post("/billing/checkout", json={"plan_key": "pro"})

    tenant_id = admin_client.headers["X-Tenant-ID"]
    rows = (
        (await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].plan_key == "pro"
