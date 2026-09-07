"""Tests for rate-limiting on hot endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from app.limiter import limiter
from app.models import Tenant, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
def _enable_rate_limiter() -> Iterator[None]:
    """Re-enable the limiter for these tests and clear its in-memory buckets."""
    previous = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()
        limiter.enabled = previous


@pytest.mark.asyncio
async def test_login_rate_limit_kicks_in_after_five_attempts(
    client: AsyncClient,
    db: AsyncSession,
    _enable_rate_limiter: None,
) -> None:
    """The 6th rapid login from one IP must be rejected with 429."""
    tenant = Tenant(slug=f"rate-{uuid4().hex[:6]}", name="Rate Tenant")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    db.add(
        User(
            tenant_id=tenant.id,
            email="rate@test.local",
            full_name="Rate Tester",
            role="admin",
            password_hash=get_password_hash("correct-password"),
            is_active=True,
        )
    )
    await db.commit()

    host_header = {"host": f"{tenant.slug}.localhost"}
    bad_credentials = {"email": "rate@test.local", "password": "wrong"}

    # Five attempts: all fail with 401 (invalid credentials), none rate-limited.
    for _ in range(5):
        response = await client.post("/auth/login", headers=host_header, json=bad_credentials)
        assert response.status_code == 401, response.text

    # Sixth attempt within the same minute hits the limit.
    sixth = await client.post("/auth/login", headers=host_header, json=bad_credentials)
    assert sixth.status_code == 429, sixth.text


@pytest.mark.asyncio
async def test_login_rate_limit_does_not_leak_into_other_tests(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """When the limiter fixture is NOT used, the autouse disable keeps it off."""
    tenant = Tenant(slug=f"unrate-{uuid4().hex[:6]}", name="Unrate Tenant")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    db.add(
        User(
            tenant_id=tenant.id,
            email="unrate@test.local",
            full_name="Unrate",
            role="admin",
            password_hash=get_password_hash("correct-password"),
            is_active=True,
        )
    )
    await db.commit()

    host_header = {"host": f"{tenant.slug}.localhost"}
    bad_credentials = {"email": "unrate@test.local", "password": "wrong"}

    # Ten attempts should all be 401, not 429.
    statuses = []
    for _ in range(10):
        response = await client.post("/auth/login", headers=host_header, json=bad_credentials)
        statuses.append(response.status_code)
    assert all(code == 401 for code in statuses), statuses


@pytest.mark.asyncio
async def test_public_quote_request_rate_limit_kicks_in_after_ten(
    client: AsyncClient,
    db: AsyncSession,
    _enable_rate_limiter: None,
) -> None:
    """The 11th public quote-request submission from one IP must return 429."""
    from app.rls import bypass_rls_in_session
    from app.utils.tenant_code import generate_unique_tenant_code

    await bypass_rls_in_session(db)
    slug = f"pubrate-{uuid4().hex[:6]}"
    code = await generate_unique_tenant_code(db)
    db.add(Tenant(slug=slug, code=code, name="Pub Rate Ltd"))
    await db.flush()

    payload = {
        "contact": {"name": "Persistent Homeowner", "email": "persist@example.com"},
        "category": "consumer_unit",
    }

    # Ten submissions: all accepted, none rate-limited.
    for _ in range(10):
        response = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
        assert response.status_code == 201, response.text

    # Eleventh within the same minute hits the limit.
    eleventh = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    assert eleventh.status_code == 429, eleventh.text
