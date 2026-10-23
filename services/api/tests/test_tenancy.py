"""Tests for tenant resolution and isolation primitives."""

import pytest
from app.main import app
from app.models import Tenant
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_health_check() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_tenant_resolved_from_subdomain(client: AsyncClient, db: AsyncSession) -> None:
    tenant = Tenant(slug="demo", name="Demo Electrical")
    db.add(tenant)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/contacts", headers={"host": "demo.localhost"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unknown_subdomain_is_rejected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/contacts", headers={"host": "unknown.localhost"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_custom_domain_is_not_a_tenant_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: api.mytradeportal.co.uk matched the {slug}.<base> pattern,
    so bare logins through the branded API host 401'd (tenant "api" not
    found). The API's own domain must resolve as a bare host."""
    from app.dependencies import _extract_tenant_slug

    monkeypatch.setattr("app.config.PUBLIC_API_BASE_URL", "https://api.mytradeportal.co.uk")
    assert _extract_tenant_slug("api.mytradeportal.co.uk") is None
    # Tenant subdomains on the same base domain still resolve.
    assert _extract_tenant_slug("demo.mytradeportal.co.uk") == "demo"
