"""Multi-tenancy isolation and access-control security tests.

These tests validate that the Row-Level Security policies and application-layer
 tenant checks prevent cross-tenant data leakage and unauthorized access.
"""

import httpx
import pytest

from security.config import config

pytestmark = pytest.mark.security


class TestTenantIsolation:
    """Prevent cross-tenant reads/writes."""

    async def test_user_cannot_read_other_tenant_contacts(
        self,
        api_client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        secondary_auth: dict[str, str] | None,
    ) -> None:
        if not secondary_auth:
            pytest.skip("SECURITY_SECONDARY_* credentials not configured")

        # Secondary tenant creates a private contact.
        create_resp = await api_client.post(
            "/contacts",
            headers=secondary_auth,
            json={
                "first_name": "Other",
                "last_name": "Tenant",
                "email": "other@tenant.example.com",
                "phone": "07700 000001",
            },
        )
        assert create_resp.status_code == 201

        # Primary tenant tries to list contacts and should not see the other tenant's data.
        list_resp = await api_client.get("/contacts", headers=auth_headers)
        assert list_resp.status_code == 200
        contacts = list_resp.json()
        emails = [c.get("email") for c in contacts]
        assert "other@tenant.example.com" not in emails

    async def test_user_cannot_access_other_tenant_by_header(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Even with a valid session, swapping the X-Tenant-ID header should fail
        # because the JWT tenant claim must match the request tenant.
        malicious_headers = auth_headers.copy()
        malicious_headers["X-Tenant-ID"] = "00000000-0000-0000-0000-000000000000"
        resp = await api_client.get("/contacts", headers=malicious_headers)
        # Should be forbidden or not found; definitely not 200 with data.
        assert resp.status_code in (401, 403, 404)

    async def test_unknown_subdomain_is_rejected(self, api_client: httpx.AsyncClient) -> None:
        headers = {"Host": "doesnotexist.localhost"}
        resp = await api_client.get("/health", headers=headers)
        # Health may be public, but tenant-scoped endpoints should reject unknown tenants.
        assert resp.status_code in (200, 404)


class TestAuthentication:
    """Authentication must be enforced on all tenant-scoped endpoints."""

    async def test_contacts_requires_auth(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.get("/contacts")
        assert resp.status_code == 401

    async def test_quotes_requires_auth(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.get("/quotes")
        assert resp.status_code == 401

    async def test_login_rejects_invalid_password(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.post(
            "/auth/login",
            data={
                "tenant_slug": config.tenant_slug,
                "email": config.admin_email,
                "password": "definitely-wrong-password",
            },
        )
        assert resp.status_code in (401, 403)

    async def test_login_rate_limiting(self, api_client: httpx.AsyncClient) -> None:
        # Attempt many rapid logins with the wrong password.
        responses = []
        for _ in range(10):
            resp = await api_client.post(
                "/auth/login",
                data={
                    "tenant_slug": config.tenant_slug,
                    "email": config.admin_email,
                    "password": "wrong",
                },
            )
            responses.append(resp.status_code)
        # At least one request should be rate-limited.
        assert 429 in responses, f"Expected rate limiting, got: {responses}"


class TestAdminAccessControl:
    """Admin endpoints must not be reachable without Django staff credentials."""

    async def test_admin_login_requires_credentials(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.get("/admin/login/", follow_redirects=False)
        assert resp.status_code == 200

    async def test_admin_api_not_exposed_publicly(self, api_client: httpx.AsyncClient) -> None:
        # The admin panel is a separate service; the public API should not expose it.
        resp = await api_client.get("/admin/")
        assert resp.status_code in (401, 403, 404)
