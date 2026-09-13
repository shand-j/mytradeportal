"""Tests for the tenant-subscription billing endpoints."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.models import Subscription
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
def paddle_customer(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub Paddle customer binding; returns the mock for call assertions."""
    fake = AsyncMock(return_value="ctm_test_1")
    monkeypatch.setattr("app.routers.billing.get_or_create_customer", fake)
    return fake


async def test_checkout_returns_paddle_url(
    admin_client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    paddle_customer: AsyncMock,
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
    # The checkout is bound to the account's Paddle customer so the hosted
    # page prefills the email and keeps it non-editable.
    assert kwargs["customer_id"] == "ctm_test_1"
    assert paddle_customer.call_args.args[0] == "admin@test.local"


async def test_checkout_applies_beta_discount_when_configured(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, paddle_customer: AsyncMock
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
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, paddle_customer: AsyncMock
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
    admin_client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    paddle_customer: AsyncMock,
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


async def test_paywall_blocks_gated_endpoints_on_incomplete_subscription(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A tenant with a subscription row in a non-live state gets 402 on staff
    endpoints, while auth and billing escape hatches stay open."""
    tenant_id = admin_client.headers["X-Tenant-ID"]
    db.add(Subscription(tenant_id=tenant_id, plan_key="pro", status="incomplete"))
    await db.commit()

    blocked = await admin_client.get("/quotes")
    assert blocked.status_code == 402
    assert blocked.json()["detail"] == "subscription_required"

    # Escape hatches stay open: session bootstrap and billing endpoints.
    assert (await admin_client.get("/auth/me")).status_code == 200
    assert (await admin_client.get("/billing/subscription")).status_code == 200

    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    assert sub is not None
    sub.status = "trialing"
    await db.commit()

    assert (await admin_client.get("/quotes")).status_code == 200


async def test_paywall_allows_tenant_without_subscription_row(admin_client: AsyncClient) -> None:
    """Beta semantics: no subscription row (legacy/seed tenants) = allowed."""
    response = await admin_client.get("/quotes")
    assert response.status_code == 200


# --- W2-B plan mapping: per-interval env vars, legacy fallback, seats --------

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
    """Clear the new per-interval price env vars so each test controls them."""
    for name in _NEW_PRICE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


async def test_price_id_prefers_new_env_over_legacy(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    from app.routers.billing import _price_id_for_plan

    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_MONTH", "pri_new_pro_m")
    clean_price_env.setattr("app.routers.billing.settings.paddle_price_id_pro", "pri_legacy_pro")

    assert _price_id_for_plan("pro") == "pri_new_pro_m"


async def test_price_id_reads_annual_interval(clean_price_env: pytest.MonkeyPatch) -> None:
    from app.routers.billing import _price_id_for_plan

    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_MONTH", "pri_new_pro_m")
    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_YEAR", "pri_new_pro_y")

    assert _price_id_for_plan("pro", "month") == "pri_new_pro_m"
    assert _price_id_for_plan("pro", "year") == "pri_new_pro_y"


async def test_price_id_resolves_legacy_plan_keys_to_new_env(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    from app.routers.billing import _price_id_for_plan

    clean_price_env.setenv("PADDLE_PRICE_ID_SOLE_TRADER_MONTH", "pri_new_st_m")
    clean_price_env.setenv("PADDLE_PRICE_ID_TEAM_MONTH", "pri_new_team_m")

    assert _price_id_for_plan("starter") == "pri_new_st_m"
    assert _price_id_for_plan("business") == "pri_new_team_m"


async def test_price_id_falls_back_to_legacy_vars(clean_price_env: pytest.MonkeyPatch) -> None:
    from app.routers.billing import _price_id_for_plan

    clean_price_env.setattr(
        "app.routers.billing.settings.paddle_price_id_starter", "pri_legacy_starter"
    )
    clean_price_env.setattr("app.routers.billing.settings.paddle_price_id_pro", "pri_legacy_pro")
    clean_price_env.setattr(
        "app.routers.billing.settings.paddle_price_id_business", "pri_legacy_business"
    )

    assert _price_id_for_plan("starter") == "pri_legacy_starter"
    assert _price_id_for_plan("sole_trader") == "pri_legacy_starter"
    assert _price_id_for_plan("pro") == "pri_legacy_pro"
    assert _price_id_for_plan("team") == "pri_legacy_business"
    # Annual interval with only legacy (monthly) prices configured still falls
    # back so beta checkouts keep working until the new catalog is wired.
    assert _price_id_for_plan("pro", "year") == "pri_legacy_pro"


async def test_price_id_rejects_unconfigured_plan(clean_price_env: pytest.MonkeyPatch) -> None:
    from app.routers.billing import _price_id_for_plan
    from fastapi import HTTPException

    clean_price_env.setattr("app.routers.billing.settings.paddle_price_id_pro", "")

    with pytest.raises(HTTPException) as excinfo:
        _price_id_for_plan("pro")
    assert excinfo.value.status_code == 400


async def test_price_id_rejects_unknown_plan(clean_price_env: pytest.MonkeyPatch) -> None:
    from app.routers.billing import _price_id_for_plan
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        _price_id_for_plan("enterprise")
    assert excinfo.value.status_code == 400


async def test_checkout_quantity_enforces_team_seat_minimum(
    clean_price_env: pytest.MonkeyPatch,
) -> None:
    from app.routers.billing import _checkout_quantity
    from fastapi import HTTPException

    assert _checkout_quantity("team", None) == 3
    assert _checkout_quantity("team", 5) == 5
    with pytest.raises(HTTPException) as excinfo:
        _checkout_quantity("team", 2)
    assert excinfo.value.status_code == 400
    # Legacy "business" resolves to team and inherits its seat rules.
    assert _checkout_quantity("business", None) == 3
    # Fixed-seat plans default to one.
    assert _checkout_quantity("sole_trader", None) == 1


async def test_checkout_team_sends_seat_quantity_and_new_price(
    admin_client: AsyncClient,
    clean_price_env: pytest.MonkeyPatch,
    paddle_customer: AsyncMock,
) -> None:
    """POST /billing/checkout for team maps env price + seat count to Paddle."""
    clean_price_env.setenv("PADDLE_PRICE_ID_TEAM_MONTH", "pri_new_team_m")
    clean_price_env.setattr("app.routers.billing.settings.paddle_beta_discount_id", "")

    fake = AsyncMock(
        return_value={"transaction_id": "txn_team", "checkout_url": "https://pay.paddle.com/t"}
    )
    with patch("app.routers.billing.create_subscription_transaction", new=fake):
        response = await admin_client.post(
            "/billing/checkout", json={"plan_key": "team", "seats": 5}
        )

    assert response.status_code == 200, response.text
    _, kwargs = fake.call_args
    assert kwargs["price_id"] == "pri_new_team_m"
    assert kwargs["quantity"] == 5


async def test_checkout_team_below_min_seats_rejected(
    admin_client: AsyncClient,
    clean_price_env: pytest.MonkeyPatch,
    paddle_customer: AsyncMock,
) -> None:
    clean_price_env.setenv("PADDLE_PRICE_ID_TEAM_MONTH", "pri_new_team_m")

    response = await admin_client.post("/billing/checkout", json={"plan_key": "team", "seats": 1})

    assert response.status_code == 400


async def test_checkout_annual_interval_uses_year_price(
    admin_client: AsyncClient,
    clean_price_env: pytest.MonkeyPatch,
    paddle_customer: AsyncMock,
) -> None:
    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_MONTH", "pri_new_pro_m")
    clean_price_env.setenv("PADDLE_PRICE_ID_PRO_YEAR", "pri_new_pro_y")
    clean_price_env.setattr("app.routers.billing.settings.paddle_beta_discount_id", "")

    fake = AsyncMock(
        return_value={"transaction_id": "txn_year", "checkout_url": "https://pay.paddle.com/y"}
    )
    with patch("app.routers.billing.create_subscription_transaction", new=fake):
        response = await admin_client.post(
            "/billing/checkout", json={"plan_key": "pro", "interval": "year"}
        )

    assert response.status_code == 200, response.text
    _, kwargs = fake.call_args
    assert kwargs["price_id"] == "pri_new_pro_y"
    assert kwargs["quantity"] == 1


async def test_portal_session_returns_paddle_portal_url(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """POST /billing/portal-session mints a customer-portal URL for a
    subscription that has a Paddle customer linked."""
    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    db.add(
        Subscription(
            tenant_id=tenant_id,
            plan_key="pro",
            status="active",
            paddle_subscription_id="sub_test_1",
            paddle_customer_id="ctm_test_1",
        )
    )
    await db.commit()

    fake = AsyncMock(return_value="https://customer-portal.paddle.com/session_test_1")
    with patch("app.routers.billing.create_customer_portal_session", new=fake):
        response = await admin_client.post("/billing/portal-session")

    assert response.status_code == 200, response.text
    assert response.json() == {"portal_url": "https://customer-portal.paddle.com/session_test_1"}
    fake.assert_awaited_once_with("ctm_test_1")


async def test_portal_session_404_without_paddle_customer(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Signup-trial subscriptions have no Paddle customer yet → 404."""
    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    db.add(Subscription(tenant_id=tenant_id, plan_key="pro", status="trialing"))
    await db.commit()

    response = await admin_client.post("/billing/portal-session")
    assert response.status_code == 404


async def test_portal_session_404_without_subscription(admin_client: AsyncClient) -> None:
    response = await admin_client.post("/billing/portal-session")
    assert response.status_code == 404


async def test_portal_session_bubbles_paddle_failure_as_502(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    from uuid import UUID

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    db.add(
        Subscription(
            tenant_id=tenant_id,
            plan_key="pro",
            status="active",
            paddle_customer_id="ctm_test_1",
        )
    )
    await db.commit()

    fake = AsyncMock(side_effect=RuntimeError("paddle 500"))
    with patch("app.routers.billing.create_customer_portal_session", new=fake):
        response = await admin_client.post("/billing/portal-session")
    assert response.status_code == 502
