"""SOC2 common-criteria control tests.

These tests act as evidence that key security controls are operating
effectively. They map to Trust Services Criteria for Security (CC6.1, CC6.6,
CC7.2, CC8.1, etc.).
"""

import httpx
import pytest

from security.config import config

pytestmark = pytest.mark.security


class TestSOC2CC61:
    """CC6.1 - Logical access controls restrict access."""

    async def test_authentication_required_for_all_tenant_data(
        self, api_client: httpx.AsyncClient
    ) -> None:
        paths = ["/contacts", "/quotes", "/jobs", "/invoices", "/payments"]
        for path in paths:
            resp = await api_client.get(path)
            assert resp.status_code == 401, f"{path} accessible without authentication"

    async def test_tenant_isolation_enforced(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        headers = {**auth_headers, "X-Tenant-ID": "fake-tenant"}
        resp = await api_client.get("/contacts", headers=headers)
        assert resp.status_code in (401, 403, 404)


class TestSOC2CC66:
    """CC6.6 - Encryption protects data."""

    async def test_api_uses_https(self, api_client: httpx.AsyncClient) -> None:
        assert config.api_base_url.startswith("https://")

    async def test_session_cookie_is_secure(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.post(
            "/auth/login",
            data={
                "tenant_slug": config.tenant_slug,
                "email": config.admin_email,
                "password": config.admin_password,
            },
        )
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "secure" in set_cookie
        assert "httponly" in set_cookie


class TestSOC2CC72:
    """CC7.2 - System monitoring detects security events."""

    def test_audit_logs_exist_for_sensitive_operations(self) -> None:
        # The audit log model exists; detailed validation is done via API audit tests.
        pytest.skip("Validated by services/api/tests/test_audit.py")


class TestSOC2CC81:
    """CC8.1 - Change management controls."""

    def test_migrations_are_not_run_at_container_runtime(self) -> None:
        # Production containers use preDeployCommand for schema init, not CMD migrations.
        # This is validated by the Dockerfile and CI reviews.
        pytest.skip("Validated by Dockerfile and CI review process")
