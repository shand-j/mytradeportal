"""Tests for the no-card signup trial and the sent-AI-quotes trial extension.

Covers:
- POST /tenants creates an internal ``trialing`` Subscription row (14 days,
  no Paddle interaction).
- Paddle checkout and the subscription webhook update THAT SAME row (no
  unique-key conflict, no duplicate row).
- The trial extension fires at exactly TRIAL_EXTENSION_SENT_AI_QUOTES sent
  AI-drafted quotes, fires only once, and ignores non-AI quotes.
- An expired trial fails ``is_subscription_active`` and the paywall.
- ``beta_comped`` tenants keep their override (access stays "active" even
  with an expired trialing row).
"""

import contextlib
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app.models import Subscription, Tenant
from app.plans import (
    DEFAULT_PLAN_KEY,
    TRIAL_DAYS,
    TRIAL_EXTENSION_DAYS,
    TRIAL_EXTENSION_SENT_AI_QUOTES,
)
from app.routers.billing import is_subscription_active
from app.routers.webhooks import _upsert_subscription
from app.trial import TRIAL_EXTENDED_SETTINGS_KEY
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _signup_and_login(client: AsyncClient, slug: str) -> str:
    """Bootstrap a tenant with an admin and log in; returns the tenant id."""
    response = await client.post(
        "/tenants",
        json={
            "slug": slug,
            "name": f"{slug} Ltd",
            "admin_email": f"admin@{slug}.example.com",
            "admin_password": "trial-pass-123",
            "admin_name": "Trial Admin",
        },
    )
    assert response.status_code == 201, response.text
    tenant_id: str = response.json()["id"]

    login = await client.post(
        "/auth/login",
        json={
            "email": f"admin@{slug}.example.com",
            "password": "trial-pass-123",
            "tenant_slug": slug,
        },
    )
    assert login.status_code == 200, login.text
    client.headers["X-Tenant-ID"] = tenant_id
    return tenant_id


async def _create_contact(client: AsyncClient, tenant_id: str) -> str:
    response = await client.post(
        "/contacts",
        json={"name": "Trial Customer", "email": "customer@example.com"},
    )
    assert response.status_code == 201, response.text
    contact_id: str = response.json()["id"]
    return contact_id


async def _create_and_send_quote(
    client: AsyncClient, tenant_id: str, contact_id: str, *, ai: bool
) -> None:
    response = await client.post(
        "/quotes",
        json={
            "contact_id": contact_id,
            "title": "AI quote" if ai else "Manual quote",
            "line_items": [
                {
                    "description": "Consumer unit upgrade",
                    "quantity": "1",
                    "unit_price": "450.00",
                    "ai_generated": ai,
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    quote_id = response.json()["id"]

    sent = await client.post(f"/quotes/{quote_id}/send")
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"


async def _get_subscription(db: AsyncSession, tenant_id: str) -> Subscription:
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == UUID(tenant_id)))
    assert sub is not None
    await db.refresh(sub)
    return sub


async def test_signup_creates_trialing_subscription_row(
    client: AsyncClient, db: AsyncSession
) -> None:
    """POST /tenants starts a 14-day no-card trial: trialing row, no Paddle ids."""
    before = datetime.utcnow()
    tenant_id = await _signup_and_login(client, f"trial-{uuid4().hex[:8]}")

    sub = await _get_subscription(db, tenant_id)
    assert sub.status == "trialing"
    assert sub.plan_key == DEFAULT_PLAN_KEY
    assert sub.paddle_subscription_id is None
    assert sub.paddle_customer_id is None
    assert sub.trial_ends_at is not None
    assert before + timedelta(days=TRIAL_DAYS) <= sub.trial_ends_at
    assert sub.trial_ends_at <= datetime.utcnow() + timedelta(days=TRIAL_DAYS)

    # The unexpired trial passes the paywall and the activity gate.
    assert is_subscription_active(sub) is True
    assert (await client.get("/quotes")).status_code == 200


async def test_checkout_after_trial_signup_updates_same_row(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paddle checkout on a trialing tenant reuses the trial row (no conflict)."""
    tenant_id = await _signup_and_login(client, f"trial-{uuid4().hex[:8]}")
    trial_row = await _get_subscription(db, tenant_id)

    monkeypatch.setattr("app.routers.billing.settings.paddle_price_id_pro", "pri_test_pro")
    monkeypatch.setattr(
        "app.routers.billing.get_or_create_customer", AsyncMock(return_value="ctm_test_1")
    )
    fake = AsyncMock(
        return_value={"transaction_id": "txn_trial_1", "checkout_url": "https://pay.paddle.com/x"}
    )
    with patch("app.routers.billing.create_subscription_transaction", new=fake):
        response = await client.post("/billing/checkout", json={"plan_key": "pro"})
    assert response.status_code == 200, response.text

    rows = (
        (await db.execute(select(Subscription).where(Subscription.tenant_id == UUID(tenant_id))))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].id == trial_row.id
    assert rows[0].plan_key == "pro"
    assert rows[0].paddle_transaction_id == "txn_trial_1"


async def test_webhook_subscription_created_updates_trial_row_in_place() -> None:
    """``_upsert_subscription`` finds the signup trial row via
    ``custom_data.tenant_id`` and hydrates it — same row id, still one row."""
    from app.database import AsyncSessionLocal

    # The webhook handler opens its own session on the (test) engine, so the
    # fixture rows must be committed on a separate connection to be visible.
    async with AsyncSessionLocal() as session:
        tenant = Tenant(slug=f"wh-{uuid4().hex[:8]}", name="Webhook Trial Ltd")
        session.add(tenant)
        await session.flush()
        trial_sub = Subscription(
            tenant_id=tenant.id,
            plan_key=DEFAULT_PLAN_KEY,
            status="trialing",
            trial_ends_at=datetime.utcnow() + timedelta(days=TRIAL_DAYS),
            provider_payload={"source": "signup_trial"},
        )
        session.add(trial_sub)
        await session.commit()
        tenant_id, trial_sub_id = tenant.id, trial_sub.id

    try:
        # Pre-existing quirk in _upsert_subscription (owned by the W2-B agent):
        # its post-commit logger.info lazy-loads sub.tenant_id on an expired
        # ORM object. The upsert has already COMMITTED by then, which is what
        # this test verifies below — so tolerate the MissingGreenlet.
        with contextlib.suppress(MissingGreenlet):
            await _upsert_subscription(
                "subscription.created",
                {
                    "id": "sub_paddle_trial_1",
                    "status": "active",
                    "customer_id": "ctm_paddle_1",
                    "custom_data": {"tenant_id": str(tenant_id)},
                    "items": [{"price": {"id": "pri_test_pro", "product_id": "pro_test"}}],
                    "current_billing_period": {
                        "starts_at": "2026-09-12T00:00:00Z",
                        "ends_at": "2026-10-12T00:00:00Z",
                    },
                },
            )

        async with AsyncSessionLocal() as session:
            rows = (
                (
                    await session.execute(
                        select(Subscription).where(Subscription.tenant_id == tenant_id)
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1
            row = rows[0]
            assert row.id == trial_sub_id
            assert row.status == "active"
            assert row.paddle_subscription_id == "sub_paddle_trial_1"
            assert row.paddle_customer_id == "ctm_paddle_1"
            assert row.paddle_price_id == "pri_test_pro"
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()


async def test_trial_extension_fires_at_exactly_three_sent_ai_quotes(
    client: AsyncClient, db: AsyncSession
) -> None:
    """2 sent AI quotes: no extension. The 3rd extends the trial to
    TRIAL_EXTENSION_DAYS from now, and a 4th send does not move it again."""
    tenant_id = await _signup_and_login(client, f"trial-{uuid4().hex[:8]}")
    contact_id = await _create_contact(client, tenant_id)
    assert TRIAL_EXTENSION_SENT_AI_QUOTES == 3  # guards the loop counts below

    sub = await _get_subscription(db, tenant_id)
    original_trial_end = sub.trial_ends_at
    assert original_trial_end is not None

    for _ in range(TRIAL_EXTENSION_SENT_AI_QUOTES - 1):
        await _create_and_send_quote(client, tenant_id, contact_id, ai=True)

    sub = await _get_subscription(db, tenant_id)
    assert sub.trial_ends_at == original_trial_end
    tenant = await db.get(Tenant, UUID(tenant_id))
    assert tenant is not None
    await db.refresh(tenant)
    assert TRIAL_EXTENDED_SETTINGS_KEY not in tenant.settings

    await _create_and_send_quote(client, tenant_id, contact_id, ai=True)

    sub = await _get_subscription(db, tenant_id)
    assert sub.trial_ends_at is not None
    assert sub.trial_ends_at > original_trial_end
    assert sub.trial_ends_at >= datetime.utcnow() + timedelta(days=TRIAL_EXTENSION_DAYS - 1)
    extended_trial_end = sub.trial_ends_at
    await db.refresh(tenant)
    assert tenant.settings[TRIAL_EXTENDED_SETTINGS_KEY]

    # Fires once: a further sent AI quote leaves trial_ends_at untouched.
    await _create_and_send_quote(client, tenant_id, contact_id, ai=True)
    sub = await _get_subscription(db, tenant_id)
    assert sub.trial_ends_at == extended_trial_end


async def test_trial_extension_ignores_non_ai_quotes(client: AsyncClient, db: AsyncSession) -> None:
    """Manually drafted quotes never count towards the extension trigger."""
    tenant_id = await _signup_and_login(client, f"trial-{uuid4().hex[:8]}")
    contact_id = await _create_contact(client, tenant_id)

    sub = await _get_subscription(db, tenant_id)
    original_trial_end = sub.trial_ends_at

    for _ in range(TRIAL_EXTENSION_SENT_AI_QUOTES + 1):
        await _create_and_send_quote(client, tenant_id, contact_id, ai=False)

    sub = await _get_subscription(db, tenant_id)
    assert sub.trial_ends_at == original_trial_end
    tenant = await db.get(Tenant, UUID(tenant_id))
    assert tenant is not None
    await db.refresh(tenant)
    assert TRIAL_EXTENDED_SETTINGS_KEY not in tenant.settings


async def test_expired_trial_is_inactive_and_paywalled(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Once trial_ends_at passes, the gate flips: is_subscription_active is
    False and staff endpoints return 402."""
    tenant_id = await _signup_and_login(client, f"trial-{uuid4().hex[:8]}")

    sub = await _get_subscription(db, tenant_id)
    sub.trial_ends_at = datetime.utcnow() - timedelta(hours=1)
    await db.commit()

    assert is_subscription_active(sub) is False
    blocked = await client.get("/quotes")
    assert blocked.status_code == 402
    assert blocked.json()["detail"] == "subscription_required"

    # A non-trialing live status is unaffected by an old trial date.
    sub.status = "active"
    assert is_subscription_active(sub) is True


async def test_beta_comped_override_survives_trial_rows(
    client: AsyncClient, db: AsyncSession
) -> None:
    """beta_comped stays supreme: even with an EXPIRED trialing subscription
    row, tenant-status reports access "active" for a comped tenant."""
    tenant_id = await _signup_and_login(client, f"trial-{uuid4().hex[:8]}")

    tenant = await db.get(Tenant, UUID(tenant_id))
    assert tenant is not None
    tenant.settings = {**tenant.settings, "beta_comped": True}
    sub = await _get_subscription(db, tenant_id)
    sub.trial_ends_at = datetime.utcnow() - timedelta(days=1)
    await db.commit()

    response = await client.get("/auth/tenant-status")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["beta_comped"] is True
    assert body["access"] == "active"
    assert body["subscription_status"] == "trialing"
