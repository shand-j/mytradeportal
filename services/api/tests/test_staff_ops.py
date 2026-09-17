"""Tests for the staff ops AI cost leaderboard (GET /staff/ops/ai-costs, #61)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from app import config as app_config
from app.models import AiRollupOrgDay, Tenant, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

PLATFORM_STAFF_EMAIL = "founder@mtp.local"


async def _platform_staff_client(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncClient:
    """An authenticated client whose user is on the PLATFORM_STAFF_EMAILS list."""
    monkeypatch.setattr(app_config, "PLATFORM_STAFF_EMAILS", PLATFORM_STAFF_EMAIL)
    tenant = Tenant(slug=f"ops-{uuid4().hex[:8]}", name="Ops Home Tenant")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)

    password = "ops-password-123"
    user = User(
        tenant_id=tenant.id,
        email=PLATFORM_STAFF_EMAIL,
        full_name="Platform Ops",
        role="owner",
        password_hash=get_password_hash(password),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    response = await client.post(
        "/auth/login",
        headers={"host": f"{tenant.slug}.localhost"},
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200
    client.headers["X-Tenant-ID"] = str(tenant.id)
    return client


def _month_start() -> date:
    now = datetime.utcnow()
    return date(now.year, now.month, 1)


def _org_day(tenant_id: UUID, day: date, **overrides: Any) -> AiRollupOrgDay:
    kwargs: dict[str, Any] = {
        "tenant_id": tenant_id,
        "date": day,
        "users_active": 1,
        "generations": 2,
        "retries": 0,
        "tokens_input": 200,
        "tokens_output": 80,
        "tokens_cached": 10,
        "est_cost_usd": Decimal("0.004000"),
        "cost_gbp": Decimal("0.0032"),
        "latency_p50": 1.0,
        "latency_p95": 2.0,
        "latency_p99": 3.0,
        "quotes_sent": 1,
    }
    kwargs.update(overrides)
    return AiRollupOrgDay(**kwargs)


async def test_ai_costs_leaderboard_for_platform_staff(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    staff = await _platform_staff_client(client, db, monkeypatch)
    month_start = _month_start()

    big = Tenant(slug="big-sparks", name="Big Sparks Ltd")
    small = Tenant(slug="small-sparks", name="Small Sparks")
    db.add_all([big, small])
    await db.flush()

    # Current month: big org spends £30 across two days; small org £10.
    db.add_all(
        [
            _org_day(
                big.id,
                month_start,
                users_active=2,
                cost_gbp=Decimal("20.0000"),
                est_cost_usd=Decimal("25.000000"),
                generations=8,
                retries=1,
                latency_p50=1.0,
                latency_p95=4.0,
                latency_p99=8.0,
                quotes_sent=3,
            ),
            _org_day(
                big.id,
                month_start.replace(day=2),
                users_active=1,
                cost_gbp=Decimal("10.0000"),
                est_cost_usd=Decimal("12.000000"),
                generations=4,
                latency_p50=2.0,
                latency_p95=5.0,
                latency_p99=10.0,
            ),
            _org_day(
                small.id,
                month_start,
                cost_gbp=Decimal("10.0000"),
                est_cost_usd=Decimal("12.000000"),
                generations=5,
                latency_p50=0.5,
                latency_p95=1.0,
                latency_p99=2.0,
            ),
            # Previous month: must be excluded from the current-month window.
            _org_day(big.id, date(2020, 1, 1), cost_gbp=Decimal("999.0000")),
        ]
    )
    await db.flush()

    response = await staff.get("/staff/ops/ai-costs")
    assert response.status_code == 200
    payload = response.json()

    assert payload["period"] == f"{month_start.year:04d}-{month_start.month:02d}"
    assert payload["month_start"] == month_start.isoformat()

    leaderboard = payload["leaderboard"]
    assert [entry["slug"] for entry in leaderboard] == ["big-sparks", "small-sparks"]

    big_entry = leaderboard[0]
    assert big_entry["name"] == "Big Sparks Ltd"
    assert big_entry["users_active"] == 3  # sum of daily distinct users
    assert big_entry["generations"] == 12
    assert big_entry["retries"] == 1
    assert big_entry["tokens_input"] == 400  # 2 days × 200 tokens
    assert big_entry["quotes_sent"] == 4  # 3 + 1 default on the second day
    assert big_entry["cost_gbp"] == pytest.approx(30.0)
    assert big_entry["est_cost_usd"] == pytest.approx(37.0)
    # Generation-weighted daily percentiles: (8x + 4y) / 12.
    assert big_entry["latency_p50"] == pytest.approx((8 * 1.0 + 4 * 2.0) / 12)
    assert big_entry["latency_p95"] == pytest.approx((8 * 4.0 + 4 * 5.0) / 12)
    assert big_entry["latency_p99"] == pytest.approx((8 * 8.0 + 4 * 10.0) / 12)
    assert big_entry["latency_p99"] >= big_entry["latency_p95"] >= big_entry["latency_p50"]

    small_entry = leaderboard[1]
    assert small_entry["cost_gbp"] == pytest.approx(10.0)
    assert small_entry["keep_rate"] is None  # no feedback folded

    # Cohort p50/p95/p99 across the two orgs' monthly figures.
    cohort = payload["cohort"]
    assert cohort["orgs"] == 2
    # Costs sorted: [10.0, 30.0] → nearest-rank p50 = 10, p95/p99 = 30.
    assert cohort["cost_gbp"] == {"p50": 10.0, "p95": 30.0, "p99": 30.0}
    # Per-org p99s sorted: [2.0, 9.333...] → p50 = 2.0, p95/p99 ≈ 9.33.
    assert cohort["latency_p99"]["p50"] == pytest.approx(2.0)
    assert cohort["latency_p99"]["p95"] == pytest.approx((8 * 8.0 + 4 * 10.0) / 12)
    assert cohort["latency_p99"]["p99"] == pytest.approx((8 * 8.0 + 4 * 10.0) / 12)


async def test_ai_costs_rejects_non_staff_user(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid tenant staff user NOT on the platform allowlist gets the
    standard staff-gate 403, even though they are an admin in their tenant."""
    monkeypatch.setattr(app_config, "PLATFORM_STAFF_EMAILS", PLATFORM_STAFF_EMAIL)
    tenant = Tenant(slug=f"plain-{uuid4().hex[:8]}", name="Plain Electrical")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)

    password = "admin-password-123"
    user = User(
        tenant_id=tenant.id,
        email="admin@test.local",
        full_name="Tenant Admin",
        role="admin",
        password_hash=get_password_hash(password),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    login = await client.post(
        "/auth/login",
        headers={"host": f"{tenant.slug}.localhost"},
        json={"email": user.email, "password": password},
    )
    assert login.status_code == 200
    client.headers["X-Tenant-ID"] = str(tenant.id)

    response = await client.get("/staff/ops/ai-costs")
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


async def test_ai_costs_rejects_unauthenticated(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No token at all → the same 401 every authenticated staff endpoint gives."""
    monkeypatch.setattr(app_config, "PLATFORM_STAFF_EMAILS", PLATFORM_STAFF_EMAIL)
    response = await client.get("/staff/ops/ai-costs")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_ai_costs_empty_allowlist_rejects_everyone(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unconfigured environment (empty allowlist) exposes nothing."""
    monkeypatch.setattr(app_config, "PLATFORM_STAFF_EMAILS", "")
    tenant = Tenant(slug=f"ops-{uuid4().hex[:8]}", name="Ops Home Tenant")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)

    password = "ops-password-123"
    user = User(
        tenant_id=tenant.id,
        email=PLATFORM_STAFF_EMAIL,
        full_name="Platform Ops",
        role="owner",
        password_hash=get_password_hash(password),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    login = await client.post(
        "/auth/login",
        headers={"host": f"{tenant.slug}.localhost"},
        json={"email": user.email, "password": password},
    )
    assert login.status_code == 200
    client.headers["X-Tenant-ID"] = str(tenant.id)

    response = await client.get("/staff/ops/ai-costs")
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
