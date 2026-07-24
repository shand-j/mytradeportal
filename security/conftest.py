"""Shared pytest fixtures for the security test suite."""

from collections.abc import AsyncIterator

import httpx
import pytest

from security.config import config


@pytest.fixture(scope="session", autouse=True)
def _validate_config() -> None:
    config.validate()


@pytest.fixture(scope="session")
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    """Unauthenticated API client."""
    async with httpx.AsyncClient(base_url=config.api_base_url, follow_redirects=False) as client:
        yield client


@pytest.fixture(scope="session")
async def primary_auth() -> dict[str, str]:
    """Login as the primary tenant admin and return auth headers."""
    async with httpx.AsyncClient(base_url=config.api_base_url, follow_redirects=False) as client:
        response = await client.post(
            "/auth/login",
            data={
                "tenant_slug": config.tenant_slug,
                "email": config.admin_email,
                "password": config.admin_password,
            },
        )
        assert response.status_code == 200, f"Primary login failed: {response.text}"
        # The API returns the session as an HTTP-only cookie.
        cookies = response.headers.get("set-cookie", "")
        return {"Cookie": cookies.split(";")[0]}


@pytest.fixture(scope="session")
async def secondary_auth() -> dict[str, str] | None:
    """Login as the secondary tenant admin, if configured."""
    if not config.secondary_admin_email:
        return None
    async with httpx.AsyncClient(base_url=config.api_base_url, follow_redirects=False) as client:
        response = await client.post(
            "/auth/login",
            data={
                "tenant_slug": config.secondary_tenant_slug,
                "email": config.secondary_admin_email,
                "password": config.secondary_admin_password,
            },
        )
        assert response.status_code == 200, f"Secondary login failed: {response.text}"
        cookies = response.headers.get("set-cookie", "")
        return {"Cookie": cookies.split(";")[0]}


@pytest.fixture(scope="session")
async def auth_headers(primary_auth: dict[str, str]) -> dict[str, str]:
    """Convenience alias for primary tenant auth headers."""
    return primary_auth
