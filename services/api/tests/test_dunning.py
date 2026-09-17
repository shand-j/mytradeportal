"""Tests for Paddle payment-failure dunning (#84).

Covers: webhook triggers (``subscription.past_due`` / ``transaction.payment_failed``)
opening a dunning episode with exactly one email, replay idempotency, the
follow-up cadence driven by the reminder scheduler sweep, recovery/cancellation
stopping the sequence, and the bounded past-due grace before the paywall
re-engages.
"""

import hashlib
import hmac
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from app.main import app
from app.models import Reminder, Subscription, Tenant
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


def _make_signature_payload(secret: str, body: bytes, timestamp: str = "1234567890") -> str:
    signature = hmac.new(
        secret.encode(), f"{timestamp}:".encode() + body, hashlib.sha256
    ).hexdigest()
    return f"ts={timestamp};h1={signature}"


class _EmailRecorder:
    """Stand-in for app.dunning.send_customer_email that records calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, db: Any = None, **kwargs: Any) -> bool:
        self.calls.append(kwargs)
        return True


@pytest_asyncio.fixture
async def email_recorder(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[_EmailRecorder, None]:
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.dunning.send_customer_email", recorder)
    yield recorder


@pytest_asyncio.fixture
async def portal_session_url(monkeypatch: pytest.MonkeyPatch) -> str:
    url = "https://customer-portal.paddle.com/session_dunning"

    async def _fake(customer_id: str) -> str:
        assert customer_id == "ctm_dunning_1"
        return url

    monkeypatch.setattr("app.dunning.create_customer_portal_session", _fake)
    return url


async def _post_paddle(client: AsyncClient, payload: dict[str, Any], secret: str) -> Any:
    body = json.dumps(payload).encode()
    signature = _make_signature_payload(secret, body)
    return await client.post(
        "/webhooks/paddle",
        content=body,
        headers={"Paddle-Signature": signature, "Content-Type": "application/json"},
    )


def _envelope(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": f"evt_{uuid4().hex[:24]}",
        "event_type": event_type,
        "occurred_at": "2026-09-13T10:15:00.000000Z",
        "notification_id": f"ntf_{uuid4().hex[:24]}",
        "data": data,
    }


# Tenant ids committed via the app engine during a test. The autouse cleanup
# fixture deletes them (cascading subscriptions/reminders) at test end so the
# engine-committed rows never leak into other suites sharing the test DB.
_committed_tenant_ids: list[str] = []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_committed_tenants() -> AsyncGenerator[None, None]:
    _committed_tenant_ids.clear()
    yield
    if _committed_tenant_ids:
        from uuid import UUID

        from app.database import engine
        from app.rls import bypass_rls_in_session
        from sqlalchemy import delete
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            ids = [UUID(value) for value in _committed_tenant_ids]
            await session.execute(delete(Tenant).where(Tenant.id.in_(ids)))
            await session.commit()
    _committed_tenant_ids.clear()


async def _make_past_due_subscription(
    *, status: str = "past_due", with_period: bool = True
) -> tuple[str, str]:
    """Committed tenant (with billing email) + Paddle subscription via the app
    engine (the webhook handler uses engine sessions). Returns (tenant_id,
    paddle_subscription_id)."""
    from app.database import engine
    from sqlalchemy.ext.asyncio import AsyncSession

    paddle_sub_id = f"sub_{uuid4().hex[:16]}"
    async with AsyncSession(engine) as session:
        tenant = Tenant(
            slug=f"du-{uuid4().hex[:8]}",
            name="Dunning Co",
            settings={"email": "owner@dunning.test"},
        )
        session.add(tenant)
        await session.flush()
        session.add(
            Subscription(
                tenant_id=tenant.id,
                plan_key="pro",
                status=status,
                paddle_subscription_id=paddle_sub_id,
                paddle_customer_id="ctm_dunning_1",
                current_period_end=datetime.utcnow() - timedelta(days=1) if with_period else None,
            )
        )
        tenant_id = str(tenant.id)
        await session.commit()
    _committed_tenant_ids.append(tenant_id)
    return tenant_id, paddle_sub_id


async def _dunning_reminder_rows(paddle_sub_id: str) -> list[Reminder]:
    """All dunning ledger rows for a subscription (engine session, committed).

    Reads with RLS bypassed: this is a cross-tenant test read and the GUC
    restore on engine pool checkout is not guaranteed in the test harness.
    """
    from app.database import engine
    from app.rls import bypass_rls_in_session
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        rows = (
            (
                await session.execute(
                    select(Reminder).where(
                        Reminder.entity_type == "subscription",
                        Reminder.payload["paddle_subscription_id"].astext == paddle_sub_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


async def test_payment_failed_webhook_sends_dunning_email_once(
    monkeypatch: pytest.MonkeyPatch,
    email_recorder: _EmailRecorder,
    portal_session_url: str,
) -> None:
    """transaction.payment_failed → one 'update your payment method' email with
    a Paddle customer-portal link, recorded in the reminders ledger."""
    secret = "whsec_dunning_pf"
    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)
    tenant_id, paddle_sub_id = await _make_past_due_subscription()

    payload = _envelope(
        "transaction.payment_failed",
        {"id": f"txn_{uuid4().hex[:20]}", "subscription_id": paddle_sub_id},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert len(email_recorder.calls) == 1
    call = email_recorder.calls[0]
    assert call["event"] == "subscription_payment_failed"
    assert call["template"] == "payment_failed"
    assert str(call["tenant_id"]) == tenant_id
    assert call["to_email"] == "owner@dunning.test"
    assert portal_session_url in call["html_body"]
    assert "payment" in call["subject"].lower()

    rows = await _dunning_reminder_rows(paddle_sub_id)
    assert len(rows) == 1
    assert rows[0].sequence == 1
    assert rows[0].channel == "email"


async def test_dunning_idempotent_on_webhook_replay(
    monkeypatch: pytest.MonkeyPatch,
    email_recorder: _EmailRecorder,
) -> None:
    """Replays (same event_id) and fresh failed-retry events in the same
    episode never double-email: at most one email per subscription per episode."""
    secret = "whsec_dunning_replay"
    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)
    tenant_id, paddle_sub_id = await _make_past_due_subscription()

    failure = _envelope(
        "transaction.payment_failed",
        {"id": f"txn_{uuid4().hex[:20]}", "subscription_id": paddle_sub_id},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await _post_paddle(client, failure, secret)
        replay = await _post_paddle(client, failure, secret)  # same event_id
        # A distinct event for the same failed episode (Paddle fires one per
        # retry attempt).
        second_attempt = _envelope(
            "transaction.payment_failed",
            {"id": f"txn_{uuid4().hex[:20]}", "subscription_id": paddle_sub_id},
        )
        third = await _post_paddle(client, second_attempt, secret)
        # And the past_due transition itself, delivered late/out of order.
        past_due = _envelope(
            "subscription.past_due",
            {
                "id": paddle_sub_id,
                "status": "past_due",
                "custom_data": {"tenant_id": tenant_id},
            },
        )
        fourth = await _post_paddle(client, past_due, secret)

    assert first.json()["status"] == "ok"
    assert replay.json()["status"] == "duplicate"  # event-id dedupe
    assert third.status_code == 200 and fourth.status_code == 200
    assert len(email_recorder.calls) == 1  # episode guard, not just event dedupe
    assert len(await _dunning_reminder_rows(paddle_sub_id)) == 1


async def test_past_due_webhook_opens_episode(
    monkeypatch: pytest.MonkeyPatch,
    email_recorder: _EmailRecorder,
) -> None:
    """subscription.past_due alone (no transaction.payment_failed) also opens
    the dunning episode."""
    secret = "whsec_dunning_pd"
    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)
    tenant_id, paddle_sub_id = await _make_past_due_subscription()

    payload = _envelope(
        "subscription.past_due",
        {
            "id": paddle_sub_id,
            "status": "past_due",
            "custom_data": {"tenant_id": tenant_id},
            "customer_id": "ctm_dunning_1",
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200, response.text
    assert len(email_recorder.calls) == 1
    assert len(await _dunning_reminder_rows(paddle_sub_id)) == 1


async def test_payment_failed_ignores_recovered_or_unknown_subscriptions(
    monkeypatch: pytest.MonkeyPatch,
    email_recorder: _EmailRecorder,
) -> None:
    """A failure event for a subscription that is not (or no longer) past_due
    must not email — e.g. a failed one-off proration charge under
    prevent_change leaves the subscription active."""
    secret = "whsec_dunning_recovered"
    monkeypatch.setattr("app.paddle_client.settings.paddle_webhook_secret", secret)
    _tenant_id, paddle_sub_id = await _make_past_due_subscription(status="active")

    payload = _envelope(
        "transaction.payment_failed",
        {"id": f"txn_{uuid4().hex[:20]}", "subscription_id": paddle_sub_id},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post_paddle(client, payload, secret)

    assert response.status_code == 200
    assert email_recorder.calls == []
    assert await _dunning_reminder_rows(paddle_sub_id) == []


# --- Scheduler-driven follow-up cadence ----------------------------------------


async def _seed_admin_subscription(
    admin_client: AsyncClient,
    db: Any,
    *,
    status: str,
    period_end: datetime | None,
) -> Subscription:
    from sqlalchemy import select

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    sub = Subscription(
        tenant_id=tenant_id,
        plan_key="pro",
        status=status,
        paddle_subscription_id=f"sub_{uuid4().hex[:16]}",
        paddle_customer_id="ctm_dunning_1",
        current_period_end=period_end,
    )
    db.add(sub)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant is not None
    tenant.settings = {**tenant.settings, "email": "owner@dunning.test"}
    await db.commit()
    return sub


async def test_dunning_followup_cadence_and_cap(
    admin_client: AsyncClient,
    db: Any,
    email_recorder: _EmailRecorder,
) -> None:
    """Episode: email 1 immediately, then one every DUNNING_INTERVAL_DAYS,
    stopping after DUNNING_MAX_REMINDERS total."""
    from app.dunning import DUNNING_INTERVAL_DAYS, DUNNING_MAX_REMINDERS, run_dunning_followups
    from sqlalchemy import select

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_admin_subscription(
        admin_client, db, status="past_due", period_end=datetime.utcnow()
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant is not None

    t0 = datetime.utcnow()

    async def _backdate_latest(created_at: datetime) -> None:
        """Pin the just-sent reminder's created_at to the fake clock so the
        cadence math is deterministic (ORM defaults stamp real time)."""
        row = await db.scalar(
            select(Reminder)
            .where(Reminder.entity_type == "subscription")
            .order_by(Reminder.created_at.desc())
            .limit(1)
        )
        assert row is not None
        row.created_at = created_at
        await db.flush()

    # Immediate sweep: opens the episode.
    assert await run_dunning_followups(db, tenant, t0) == 1
    await _backdate_latest(t0)
    # Same sweep: cadence has not elapsed.
    assert await run_dunning_followups(db, tenant, t0) == 0
    assert len(email_recorder.calls) == 1

    # A hair before the interval → still nothing (cadence is strict).
    assert (
        await run_dunning_followups(
            db, tenant, t0 + timedelta(days=DUNNING_INTERVAL_DAYS, hours=-1)
        )
        == 0
    )
    # Interval elapsed → follow-up 2.
    assert (
        await run_dunning_followups(db, tenant, t0 + timedelta(days=DUNNING_INTERVAL_DAYS, hours=1))
        == 1
    )
    await _backdate_latest(t0 + timedelta(days=DUNNING_INTERVAL_DAYS, hours=1))
    # Not yet → nothing.
    assert (
        await run_dunning_followups(db, tenant, t0 + timedelta(days=DUNNING_INTERVAL_DAYS, hours=2))
        == 0
    )
    # Next interval → follow-up 3 (the cap).
    assert (
        await run_dunning_followups(
            db, tenant, t0 + timedelta(days=2 * DUNNING_INTERVAL_DAYS, hours=1)
        )
        == 1
    )
    await _backdate_latest(t0 + timedelta(days=2 * DUNNING_INTERVAL_DAYS, hours=1))
    # Cap reached: further sweeps send nothing, forever.
    assert await run_dunning_followups(db, tenant, t0 + timedelta(days=30)) == 0
    assert len(email_recorder.calls) == DUNNING_MAX_REMINDERS
    sequences = [c["context"]["sequence"] for c in email_recorder.calls]
    assert sequences == [1, 2, 3]


async def test_dunning_stops_when_payment_recovers(
    admin_client: AsyncClient,
    db: Any,
    email_recorder: _EmailRecorder,
) -> None:
    """A recovered subscription (status back to active) stops the sequence."""
    from app.dunning import run_dunning_followups
    from sqlalchemy import select

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    sub = await _seed_admin_subscription(
        admin_client, db, status="past_due", period_end=datetime.utcnow()
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant is not None

    t0 = datetime.utcnow()
    assert await run_dunning_followups(db, tenant, t0) == 1

    # Payment recovered before the next follow-up was due.
    sub.status = "active"
    await db.commit()
    assert await run_dunning_followups(db, tenant, t0 + timedelta(days=30)) == 0
    assert len(email_recorder.calls) == 1


async def test_dunning_stops_when_subscription_canceled(
    admin_client: AsyncClient,
    db: Any,
    email_recorder: _EmailRecorder,
) -> None:
    from app.dunning import run_dunning_followups
    from sqlalchemy import select

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    sub = await _seed_admin_subscription(
        admin_client, db, status="past_due", period_end=datetime.utcnow()
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant is not None

    t0 = datetime.utcnow()
    assert await run_dunning_followups(db, tenant, t0) == 1

    sub.status = "canceled"
    await db.commit()
    assert await run_dunning_followups(db, tenant, t0 + timedelta(days=30)) == 0
    assert len(email_recorder.calls) == 1


async def test_new_period_opens_a_new_dunning_episode(
    admin_client: AsyncClient,
    db: Any,
    email_recorder: _EmailRecorder,
) -> None:
    """A later failure in a NEW billing period (different period end) emails
    again — episode identity is (subscription, period)."""
    from app.dunning import run_dunning_followups
    from sqlalchemy import select

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    sub = await _seed_admin_subscription(
        admin_client, db, status="past_due", period_end=datetime.utcnow()
    )
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant is not None

    t0 = datetime.utcnow()
    assert await run_dunning_followups(db, tenant, t0) == 1

    # Recovery, then a fresh failure in the next billing period.
    sub.status = "active"
    await db.commit()
    sub.status = "past_due"
    sub.current_period_end = datetime.utcnow() + timedelta(days=30)
    await db.commit()

    assert await run_dunning_followups(db, tenant, t0 + timedelta(days=31)) == 1
    assert len(email_recorder.calls) == 2


async def test_scheduler_sweep_includes_dunning_followups(
    admin_client: AsyncClient,
    db: Any,
    email_recorder: _EmailRecorder,
) -> None:
    """The reminder tick surfaces dunning emails in its summary (wiring)."""
    from app.scheduler import run_reminder_tick

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_admin_subscription(
        admin_client, db, status="past_due", period_end=datetime.utcnow()
    )

    summary = await run_reminder_tick(db)
    assert summary["dunning_reminders"] >= 1
    our_emails = [c for c in email_recorder.calls if str(c["tenant_id"]) == str(tenant_id)]
    assert len(our_emails) == 1
