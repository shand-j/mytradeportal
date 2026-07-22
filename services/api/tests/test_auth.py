"""Tests for authentication and user management endpoints."""

from uuid import uuid4

import pytest
from app.models import Tenant, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_admin_user(db: AsyncSession) -> tuple[Tenant, User, str]:
    """Create a tenant and an admin user with a known password."""
    tenant = Tenant(slug=f"test-{uuid4().hex[:8]}", name="Test Electrical")
    db.add(tenant)
    await db.flush()

    # RLS forbids inserting into ``users`` unless the session has declared
    # which tenant it is operating on.
    await set_tenant_in_session(db, tenant.id)

    password = "test-password-123"
    user = User(
        tenant_id=tenant.id,
        email="admin@test.local",
        full_name="Test Admin",
        role="admin",
        password_hash=get_password_hash(password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return tenant, user, password


@pytest.fixture
async def admin_credentials(client: AsyncClient, db: AsyncSession) -> dict:
    """Return login credentials for a freshly created admin user."""
    tenant, _, password = await _create_admin_user(db)
    return {
        "host": f"{tenant.slug}.localhost",
        "email": "admin@test.local",
        "password": password,
        "tenant_id": str(tenant.id),
    }


async def test_login_success(client: AsyncClient, admin_credentials: dict) -> None:
    response = await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == admin_credentials["email"]
    assert data["role"] == "admin"
    assert "session" in response.cookies


async def test_login_invalid_password(client: AsyncClient, admin_credentials: dict) -> None:
    response = await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_me_returns_authenticated_user(client: AsyncClient, admin_credentials: dict) -> None:
    await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    response = await client.get("/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == admin_credentials["email"]


async def test_logout_clears_cookie(client: AsyncClient, admin_credentials: dict) -> None:
    await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    response = await client.post("/auth/logout")
    assert response.status_code == 200
    assert response.cookies.get("session") is None


async def test_create_user_requires_admin(client: AsyncClient, admin_credentials: dict) -> None:
    await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    response = await client.post(
        "/users",
        json={
            "email": "newuser@test.local",
            "full_name": "New User",
            "password": "new-password-123",
            "role": "technician",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@test.local"
    assert data["role"] == "technician"


async def test_login_with_supabase_user(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Supabase Auth is configured, login succeeds via Supabase identity."""
    tenant = Tenant(slug=f"test-{uuid4().hex[:8]}", name="Test Electrical")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)

    supabase_uid = str(uuid4())
    user = User(
        tenant_id=tenant.id,
        email="sbuser@test.local",
        full_name="Supabase User",
        role="admin",
        password_hash=None,
        supabase_uid=supabase_uid,
        is_active=True,
    )
    db.add(user)
    await db.commit()

    monkeypatch.setattr("app.routers.auth.is_supabase_configured", lambda: True)
    async def _sign_in(email: str, password: str) -> dict:
        return {"user": {"id": supabase_uid}}

    monkeypatch.setattr("app.routers.auth.sign_in_with_password", _sign_in)

    response = await client.post(
        "/auth/login",
        headers={"host": f"{tenant.slug}.localhost"},
        json={"email": user.email, "password": "any-password"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == user.email
    assert "session" in response.cookies


async def test_login_fails_when_supabase_rejects_credentials(
    client: AsyncClient, admin_credentials: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Supabase is configured but rejects credentials, do not fall back local."""
    monkeypatch.setattr("app.routers.auth.is_supabase_configured", lambda: True)
    async def _sign_in(email: str, password: str) -> None:
        return None

    monkeypatch.setattr("app.routers.auth.sign_in_with_password", _sign_in)

    response = await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    assert response.status_code == 401
