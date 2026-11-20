"""CORS coverage for public browser origins."""

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient
from mtp_shared import InsecureProductionConfigError, Settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    [
        "https://landing-staging-192c.up.railway.app",
        "https://demo.mytradeportal.co.uk",
        "https://tenant-123.mytradeportal.co.uk",
    ],
)
async def test_public_staging_and_tenant_origins_allowed(origin: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "authorization" in {
        value.strip().lower()
        for value in response.headers["access-control-allow-headers"].split(",")
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    [
        "https://evilmytradeportal.co.uk",
        "https://demo.mytradeportal.co.uk.evil.example",
        "https://demo-mytradeportal-co.uk",
        "http://demo.mytradeportal.co.uk",
        "https://landing-staging-192c.up.railway.app.evil.example",
    ],
)
async def test_disallowed_lookalike_origins(origin: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_credentialed_staging_request() -> None:
    origin = "https://landing-staging-192c.up.railway.app"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_production_rejects_wildcard_origin_regex() -> None:
    settings = Settings(
        environment="production",
        allowed_origins="https://www.mytradeportal.co.uk",
        allowed_origin_regex=r"https://.*\.example\.com",
        auth_secret_key="production-secret",
        app_role_password="production-app-password",
        minio_access_key="production-minio-access",
        minio_secret_key="production-minio-secret",
    )

    with pytest.raises(InsecureProductionConfigError, match="allowed_origin_regex"):
        settings.validate_production()
