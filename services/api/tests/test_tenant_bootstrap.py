"""Tests for atomic tenant + first-admin bootstrap via POST /tenants."""

from uuid import uuid4

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
