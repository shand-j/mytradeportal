"""Tests for authentication and user management endpoints."""

from typing import Any
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
async def admin_credentials(client: AsyncClient, db: AsyncSession) -> dict[str, Any]:
    """Return login credentials for a freshly created admin user."""
    tenant, _, password = await _create_admin_user(db)
    return {
        "host": f"{tenant.slug}.localhost",
        "email": "admin@test.local",
        "password": password,
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
    }


async def test_login_success(client: AsyncClient, admin_credentials: dict[str, Any]) -> None:
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


async def test_login_invalid_password(
    client: AsyncClient, admin_credentials: dict[str, Any]
) -> None:
    response = await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401


async def test_token_returns_bearer_and_authorizes_me(
    client: AsyncClient, admin_credentials: dict[str, Any]
) -> None:
    """The native /auth/token endpoint returns a Bearer token that authorizes
    a subsequent request via the Authorization header (no cookie)."""
    response = await client.post(
        "/auth/token",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["tenant_slug"] == admin_credentials["tenant_slug"]
    assert data["user"]["email"] == admin_credentials["email"]
    tenant_id = data["user"]["tenant_id"]

    me = await client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {data['access_token']}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert me.status_code == 200
    assert me.json()["email"] == admin_credentials["email"]


async def test_token_invalid_password(
    client: AsyncClient, admin_credentials: dict[str, Any]
) -> None:
    response = await client.post(
        "/auth/token",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401


async def test_token_with_bare_domain_falls_back_to_email_lookup(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Native clients often call /auth/token against localhost with no tenant
    context. The backend should resolve the tenant from the user's email."""
    tenant, user, password = await _create_admin_user(db)
    response = await client.post(
        "/auth/token",
        headers={"host": "localhost:8000"},
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_slug"] == tenant.slug
    assert data["user"]["email"] == user.email


async def test_login_with_explicit_tenant_slug(client: AsyncClient, db: AsyncSession) -> None:
    """An explicit tenant_slug authenticates a non-default tenant's user even
    when the Host header carries no tenant subdomain (bare domain)."""
    tenant, user, password = await _create_admin_user(db)
    response = await client.post(
        "/auth/login",
        json={
            "email": user.email,
            "password": password,
            "tenant_slug": tenant.slug,
        },
    )
    assert response.status_code == 200
    assert response.json()["email"] == user.email
    assert "session" in response.cookies


async def test_login_tenant_slug_overrides_host_subdomain(
    client: AsyncClient, db: AsyncSession
) -> None:
    """When both are present, tenant_slug wins over Host-subdomain resolution."""
    tenant, user, password = await _create_admin_user(db)
    other = Tenant(slug=f"other-{uuid4().hex[:8]}", name="Other Electrical")
    db.add(other)
    await db.commit()
    response = await client.post(
        "/auth/login",
        headers={"host": f"{other.slug}.localhost"},
        json={
            "email": user.email,
            "password": password,
            "tenant_slug": tenant.slug,
        },
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(tenant.id)


async def test_login_with_unknown_tenant_slug_is_401(
    client: AsyncClient, admin_credentials: dict[str, Any]
) -> None:
    response = await client.post(
        "/auth/login",
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
            "tenant_slug": "no-such-tenant",
        },
    )
    assert response.status_code == 401


async def test_login_with_tenant_slug_and_wrong_password_is_401(
    client: AsyncClient, db: AsyncSession
) -> None:
    tenant, user, _ = await _create_admin_user(db)
    response = await client.post(
        "/auth/login",
        json={
            "email": user.email,
            "password": "wrong-password",
            "tenant_slug": tenant.slug,
        },
    )
    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_me_returns_authenticated_user(
    client: AsyncClient, admin_credentials: dict[str, Any]
) -> None:
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


async def test_logout_clears_cookie(client: AsyncClient, admin_credentials: dict[str, Any]) -> None:
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


async def test_create_user_requires_admin(
    client: AsyncClient, admin_credentials: dict[str, Any]
) -> None:
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

    async def _sign_in(email: str, password: str) -> dict[str, Any]:
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
    client: AsyncClient, admin_credentials: dict[str, Any], monkeypatch: pytest.MonkeyPatch
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


async def test_login_falls_back_to_bcrypt_when_supabase_unreachable(
    client: AsyncClient, admin_credentials: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Supabase outage must not 500 login: users with a local password hash
    still authenticate via bcrypt. Bad credentials are unaffected — a clean
    Supabase rejection returns None and never reaches the fallback."""
    import httpx

    monkeypatch.setattr("app.routers.auth.is_supabase_configured", lambda: True)

    async def _sign_in(email: str, password: str) -> None:
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr("app.routers.auth.sign_in_with_password", _sign_in)

    response = await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    assert response.status_code == 200
    assert response.json()["email"] == admin_credentials["email"]


# --------------------------------------------------------------------------
# Password reset flow


@pytest.fixture
def deterministic_reset_token(monkeypatch: pytest.MonkeyPatch) -> str:
    """Patch ``secrets.token_urlsafe`` so tests know the token that will land."""
    token = "test-token-" + "x" * 40
    monkeypatch.setattr("app.routers.auth.secrets.token_urlsafe", lambda _n: token)
    return token


@pytest.fixture(autouse=True)
def stub_email_send(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Swallow email sends during auth tests + record them for assertions."""
    sent: list[dict[str, Any]] = []

    async def _fake_send(**kwargs: Any) -> dict[str, Any]:
        sent.append(kwargs)
        return {"recipient": kwargs.get("to_email"), "subject": kwargs.get("subject")}

    monkeypatch.setattr("app.routers.auth.send_email", _fake_send)
    return sent


async def test_password_reset_request_returns_generic_for_unknown_email(
    client: AsyncClient,
) -> None:
    """Unknown emails must not be enumerated: same response as a real reset."""
    response = await client.post(
        "/auth/password-reset/request",
        json={"email": "nobody@example.com"},
    )
    assert response.status_code == 200
    assert "a reset link has been sent" in response.json()["detail"]


async def test_password_reset_request_issues_token_for_known_user(
    client: AsyncClient,
    admin_credentials: dict[str, Any],
    deterministic_reset_token: str,
    stub_email_send: list[dict[str, Any]],
) -> None:
    """Real user → reset email is sent with the token embedded in the link."""
    response = await client.post(
        "/auth/password-reset/request",
        json={"email": admin_credentials["email"]},
    )
    assert response.status_code == 200
    assert "a reset link has been sent" in response.json()["detail"]

    assert len(stub_email_send) == 1
    email = stub_email_send[0]
    assert email["to_email"] == admin_credentials["email"]
    assert deterministic_reset_token in email["html_body"]
    assert deterministic_reset_token in email["text_body"]


async def test_password_reset_confirm_updates_password(
    client: AsyncClient,
    admin_credentials: dict[str, Any],
    deterministic_reset_token: str,
) -> None:
    """Happy path: request → confirm → old password rejected, new one works."""
    await client.post(
        "/auth/password-reset/request",
        json={"email": admin_credentials["email"]},
    )

    new_password = "NewSecureP@ssw0rd!"
    confirm = await client.post(
        "/auth/password-reset/confirm",
        json={"token": deterministic_reset_token, "new_password": new_password},
    )
    assert confirm.status_code == 200
    assert confirm.json()["detail"] == "Password updated"

    old = await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={
            "email": admin_credentials["email"],
            "password": admin_credentials["password"],
        },
    )
    assert old.status_code == 401

    new = await client.post(
        "/auth/login",
        headers={"host": admin_credentials["host"]},
        json={"email": admin_credentials["email"], "password": new_password},
    )
    assert new.status_code == 200


async def test_password_reset_confirm_rejects_invalid_token(client: AsyncClient) -> None:
    """A random token must be rejected with 400."""
    response = await client.post(
        "/auth/password-reset/confirm",
        json={"token": "a" * 64, "new_password": "SomeOtherP@ssw0rd!"},
    )
    assert response.status_code == 400


async def test_password_reset_confirm_rejects_used_token(
    client: AsyncClient,
    admin_credentials: dict[str, Any],
    deterministic_reset_token: str,
) -> None:
    """Second use of the same token must fail (single-use guarantee)."""
    await client.post(
        "/auth/password-reset/request",
        json={"email": admin_credentials["email"]},
    )

    first = await client.post(
        "/auth/password-reset/confirm",
        json={"token": deterministic_reset_token, "new_password": "FirstUseP@ssw0rd!"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/auth/password-reset/confirm",
        json={"token": deterministic_reset_token, "new_password": "SecondUseP@ssw0rd!"},
    )
    assert second.status_code == 400
