"""Tests for atomic tenant + first-admin bootstrap via POST /tenants."""

from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient


def _bootstrap_payload(slug: str) -> dict[str, str]:
    return {
        "slug": slug,
        "name": f"{slug} Ltd",
        "admin_email": f"admin@{slug}.example.com",
        "admin_password": "bootstrap-pass-123",
        "admin_name": "Bootstrap Admin",
    }


async def test_bootstrap_creates_tenant_and_admin_who_can_login(client: AsyncClient) -> None:
    slug = f"boot-{uuid4().hex[:8]}"
    response = await client.post("/tenants", json=_bootstrap_payload(slug))
    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == slug
    assert data["code"] is not None
    assert len(data["code"]) == 6
    assert data["code"].isdigit()
    assert data["admin_user"]["email"] == f"admin@{slug}.example.com"
    assert data["admin_user"]["role"] == "admin"
    assert data["admin_user"]["tenant_id"] == data["id"]

    login = await client.post(
        "/auth/login",
        json={
            "email": f"admin@{slug}.example.com",
            "password": "bootstrap-pass-123",
            "tenant_slug": slug,
        },
    )
    assert login.status_code == 200
    assert login.json()["email"] == f"admin@{slug}.example.com"
    assert "session" in login.cookies


async def test_bootstrap_without_admin_fields_creates_tenant_only(client: AsyncClient) -> None:
    slug = f"plain-{uuid4().hex[:8]}"
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    assert response.json()["slug"] == slug
    assert response.json()["admin_user"] is None


async def test_bootstrap_rejects_missing_setup_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.routers.tenants._settings.setup_token", "expected-token")
    slug = f"tok-{uuid4().hex[:8]}"
    response = await client.post("/tenants", json=_bootstrap_payload(slug))
    assert response.status_code == 401


async def test_bootstrap_rejects_wrong_setup_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.routers.tenants._settings.setup_token", "expected-token")
    slug = f"tok-{uuid4().hex[:8]}"
    response = await client.post(
        "/tenants",
        json=_bootstrap_payload(slug),
        headers={"X-Setup-Token": "wrong-token"},
    )
    assert response.status_code == 401


async def test_bootstrap_accepts_valid_setup_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.routers.tenants._settings.setup_token", "expected-token")
    slug = f"tok-{uuid4().hex[:8]}"
    response = await client.post(
        "/tenants",
        json=_bootstrap_payload(slug),
        headers={"X-Setup-Token": "expected-token"},
    )
    assert response.status_code == 201
    assert response.json()["admin_user"]["email"] == f"admin@{slug}.example.com"


async def test_bootstrap_rejects_short_admin_password(client: AsyncClient) -> None:
    slug = f"short-{uuid4().hex[:8]}"
    payload = _bootstrap_payload(slug)
    payload["admin_password"] = "2-short"
    response = await client.post("/tenants", json=payload)
    assert response.status_code == 422


async def test_bootstrap_rejects_duplicate_admin_email(client: AsyncClient) -> None:
    """One account per staff email: a second tenant for the same admin email
    409s instead of stacking a duplicate business (onboarding retries)."""
    email = f"dup-{uuid4().hex[:8]}@example.com"
    first = _bootstrap_payload(f"dup-a-{uuid4().hex[:6]}")
    first["admin_email"] = email
    second = _bootstrap_payload(f"dup-b-{uuid4().hex[:6]}")
    second["admin_email"] = email

    response_a = await client.post("/tenants", json=first)
    assert response_a.status_code == 201, response_a.text
    response_b = await client.post("/tenants", json=second)
    assert response_b.status_code == 409
    assert "email" in response_b.json()["detail"].lower()


async def test_bootstrap_rejects_invalid_admin_email(client: AsyncClient) -> None:
    slug = f"email-{uuid4().hex[:8]}"
    payload = _bootstrap_payload(slug)
    payload["admin_email"] = "not-an-email"
    response = await client.post("/tenants", json=payload)
    assert response.status_code == 422


async def test_bootstrap_rejects_partial_admin_fields(client: AsyncClient) -> None:
    slug = f"part-{uuid4().hex[:8]}"
    response = await client.post(
        "/tenants",
        json={"slug": slug, "name": f"{slug} Ltd", "admin_email": f"admin@{slug}.example.com"},
    )
    assert response.status_code == 422


async def test_bootstrap_rejects_duplicate_slug(client: AsyncClient) -> None:
    slug = f"dup-{uuid4().hex[:8]}"
    first = await client.post("/tenants", json=_bootstrap_payload(slug))
    assert first.status_code == 201
    second = await client.post("/tenants", json=_bootstrap_payload(slug))
    assert second.status_code == 409


async def test_email_availability_reports_available_for_unknown_email(
    client: AsyncClient,
) -> None:
    email = f"free-{uuid4().hex[:8]}@example.com"
    response = await client.get("/tenants/email-availability", params={"email": email})
    assert response.status_code == 200
    assert response.json() == {"email": email, "available": True}


async def test_email_availability_reports_taken_for_existing_account(
    client: AsyncClient,
) -> None:
    email = f"taken-{uuid4().hex[:8]}@example.com"
    payload = _bootstrap_payload(f"taken-{uuid4().hex[:6]}")
    payload["admin_email"] = email
    created = await client.post("/tenants", json=payload)
    assert created.status_code == 201, created.text

    response = await client.get("/tenants/email-availability", params={"email": email})
    assert response.status_code == 200
    assert response.json() == {"email": email, "available": False}


async def test_email_availability_lookup_is_case_insensitive(client: AsyncClient) -> None:
    email = f"case-{uuid4().hex[:8]}@example.com"
    payload = _bootstrap_payload(f"case-{uuid4().hex[:6]}")
    payload["admin_email"] = email
    created = await client.post("/tenants", json=payload)
    assert created.status_code == 201, created.text

    response = await client.get("/tenants/email-availability", params={"email": email.upper()})
    assert response.status_code == 200
    assert response.json()["available"] is False


async def test_email_availability_rejects_invalid_email(client: AsyncClient) -> None:
    response = await client.get("/tenants/email-availability", params={"email": "not-an-email"})
    assert response.status_code == 422


async def test_email_availability_requires_setup_token_when_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.routers.tenants._settings.setup_token", "expected-token")
    email = f"tok-{uuid4().hex[:8]}@example.com"

    missing = await client.get("/tenants/email-availability", params={"email": email})
    assert missing.status_code == 401

    wrong = await client.get(
        "/tenants/email-availability",
        params={"email": email},
        headers={"X-Setup-Token": "wrong-token"},
    )
    assert wrong.status_code == 401

    valid = await client.get(
        "/tenants/email-availability",
        params={"email": email},
        headers={"X-Setup-Token": "expected-token"},
    )
    assert valid.status_code == 200
    assert valid.json()["available"] is True


async def test_bootstrap_supabase_rejection_returns_502_not_500(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C23 regression: when Supabase Auth is configured but rejects the admin
    signup, the endpoint must return a clear 502 instead of a bare 500."""
    monkeypatch.setattr("app.routers.tenants.is_supabase_configured", lambda: True)

    def _reject(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Failed to create Supabase user: 422 weak_password")

    monkeypatch.setattr("app.routers.tenants.admin_create_user", _reject)

    response = await client.post("/tenants", json=_bootstrap_payload(f"sb-{uuid4().hex[:8]}"))
    assert response.status_code == 502
    assert "authentication provider" in response.json()["detail"].lower()


async def test_bootstrap_supabase_unreachable_returns_503_not_500(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C23 regression: a network-level failure talking to Supabase Auth must
    return a clear 503 instead of a bare 500."""
    monkeypatch.setattr("app.routers.tenants.is_supabase_configured", lambda: True)

    def _unreachable(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.routers.tenants.admin_create_user", _unreachable)

    response = await client.post("/tenants", json=_bootstrap_payload(f"sbx-{uuid4().hex[:8]}"))
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
