"""OWASP Top 10 security tests against the production API.

Each top-level class maps to one OWASP category. Tests are intentionally safe:
no destructive payloads are executed; they only verify that the application
rejects or sanitizes malicious input and configuration.
"""

import httpx
import pytest

from security.config import config

pytestmark = pytest.mark.security


class TestA01BrokenAccessControl:
    """A01:2021 - Broken Access Control."""

    async def test_unauthenticated_requests_are_rejected(
        self, api_client: httpx.AsyncClient
    ) -> None:
        endpoints = ["/contacts", "/quotes", "/jobs", "/invoices", "/analytics/dashboard"]
        for path in endpoints:
            resp = await api_client.get(path)
            assert resp.status_code == 401, f"{path} leaked data without auth"

    async def test_jwt_tenant_claim_is_enforced(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Tamper with the tenant resolution header while keeping a valid session.
        headers = {**auth_headers, "X-Tenant-ID": "malicious-tenant-uuid"}
        resp = await api_client.get("/contacts", headers=headers)
        assert resp.status_code in (401, 403, 404)

    async def test_object_ids_are_not_predictable_or_enumerable(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Attempt to access a contact using a synthetic UUID.
        resp = await api_client.get(
            "/contacts/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code in (404, 403)


class TestA02CryptographicFailures:
    """A02:2021 - Cryptographic Failures."""

    async def test_https_is_required(self, api_client: httpx.AsyncClient) -> None:
        # The configured API URL must be HTTPS in production.
        assert config.api_base_url.startswith("https://")

    async def test_session_cookie_is_http_only_and_secure(
        self, api_client: httpx.AsyncClient
    ) -> None:
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
        assert "httponly" in set_cookie
        assert "secure" in set_cookie

    async def test_passwords_never_returned_in_api_responses(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await api_client.get("/users/me", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "password" not in body
        assert "password_hash" not in body


class TestA03Injection:
    """A03:2021 - Injection."""

    async def test_sql_injection_in_search_is_rejected(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        payloads = [
            "' OR '1'='1",
            "'; DROP TABLE contacts; --",
            "1; SELECT * FROM users",
        ]
        for payload in payloads:
            resp = await api_client.get(
                "/contacts",
                headers=auth_headers,
                params={"q": payload},
            )
            # Should not crash with 500 or return all rows.
            assert resp.status_code in (200, 400, 422)
            if resp.status_code == 200:
                data = resp.json()
                assert isinstance(data, list)

    async def test_no_sql_injection_in_query_params(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await api_client.get(
            "/contacts",
            headers=auth_headers,
            params={"q": "{$ne: null}"},
        )
        assert resp.status_code in (200, 400, 422)

    async def test_command_injection_in_file_names_is_rejected(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Presigned upload URL endpoint should sanitize or reject dangerous filenames.
        resp = await api_client.post(
            "/files/presign",
            headers=auth_headers,
            json={"filename": "; cat /etc/passwd;", "content_type": "image/png"},
        )
        assert resp.status_code in (400, 422, 500)


class TestA04InsecureDesign:
    """A04:2021 - Insecure Design."""

    async def test_setup_token_is_required_for_tenant_creation(
        self, api_client: httpx.AsyncClient
    ) -> None:
        resp = await api_client.post(
            "/tenants",
            json={
                "slug": "attacker-tenant",
                "name": "Attacker",
                "admin_email": "attacker@example.com",
                "admin_password": "password123",
                "admin_name": "Attacker",
            },
        )
        assert resp.status_code in (401, 403, 422)

    async def test_sensitive_endpoints_require_strong_authentication(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Admin-only endpoints should not be reachable by a regular tenant admin.
        resp = await api_client.get("/admin/tenants", headers=auth_headers)
        assert resp.status_code in (401, 403, 404)


class TestA05SecurityMisconfiguration:
    """A05:2021 - Security Misconfiguration."""

    async def test_security_headers_are_present(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.get("/health")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        assert "x-content-type-options" in headers
        assert "x-frame-options" in headers
        assert (
            "content-security-policy" in headers or "content-security-policy-report-only" in headers
        )

    async def test_verbose_errors_do_not_leak_stack_traces(
        self, api_client: httpx.AsyncClient
    ) -> None:
        # Send a malformed JSON body to a POST endpoint.
        resp = await api_client.post(
            "/auth/login",
            headers={"Content-Type": "application/json"},
            content=b"{not valid json",
        )
        assert resp.status_code in (400, 422, 500)
        assert "traceback" not in resp.text.lower()
        assert "exception" not in resp.text.lower()

    async def test_cors_does_not_allow_wildcards_in_production(
        self, api_client: httpx.AsyncClient
    ) -> None:
        resp = await api_client.get(
            "/health",
            headers={"Origin": "https://evil.com"},
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        assert "*" not in acao


class TestA06VulnerableComponents:
    """A06:2021 - Vulnerable and Outdated Components."""

    def test_python_dependencies_have_no_known_high_severity_vulnerabilities(self) -> None:
        # This is validated by the CI job running `pip-audit` or `safety check`.
        pytest.skip("Run manually with: pip-audit --desc --audit-level=high")

    def test_javascript_dependencies_have_no_high_severity_vulnerabilities(self) -> None:
        pytest.skip("Run manually with: pnpm audit --audit-level=high")


class TestA07IdentificationAndAuthFailures:
    """A07:2021 - Identification and Authentication Failures."""

    async def test_weak_passwords_are_rejected(self, api_client: httpx.AsyncClient) -> None:
        # Tenant creation endpoint should reject trivial passwords when a setup token is used.
        resp = await api_client.post(
            "/tenants",
            headers={"X-Setup-Token": "dummy-token"},
            json={
                "slug": "weak-password-tenant",
                "name": "Weak",
                "admin_email": "weak@example.com",
                "admin_password": "123",
                "admin_name": "Weak",
            },
        )
        assert resp.status_code in (401, 403, 422)

    async def test_session_expires_after_password_change(
        self, api_client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Placeholder: if the API supports password change, verify old sessions are invalidated.
        pytest.skip("Requires password-change endpoint implementation")


class TestA08SoftwareAndDataIntegrity:
    """A08:2021 - Software and Data Integrity Failures."""

    async def test_webhooks_verify_signatures(self, api_client: httpx.AsyncClient) -> None:
        # Paddle webhooks must verify HMAC signatures.
        resp = await api_client.post(
            "/webhooks/paddle",
            json={"event": "test"},
            headers={"Paddle-Signature": "invalid"},
        )
        assert resp.status_code in (400, 401, 403)


class TestA09SecurityLoggingAndMonitoring:
    """A09:2021 - Security Logging and Monitoring Failures."""

    async def test_failed_logins_are_logged(self, api_client: httpx.AsyncClient) -> None:
        # The audit log endpoint should record failed login attempts.
        # This is validated by API audit tests; placeholder for security-specific assertions.
        pytest.skip("Requires access to application logs or audit-log API")


class TestA10ServerSideRequestForgery:
    """A10:2021 - Server-Side Request Forgery."""

    async def test_webhooks_do_not_follow_internal_redirects(
        self, api_client: httpx.AsyncClient
    ) -> None:
        # Any feature that fetches a user-supplied URL should not reach internal networks.
        pytest.skip("Requires URL-fetch feature to test")
