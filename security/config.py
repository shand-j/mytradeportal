"""Security test configuration.

All values are read from environment variables so the same suite can run
locally, in CI, or against production without code changes.
"""

import os


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for security tests")
    return value


class SecurityConfig:
    """Runtime settings for the security test suite."""

    # Target environment
    environment: str = os.environ.get("SECURITY_ENVIRONMENT", "production")

    # Web / API endpoints
    web_base_url: str = os.environ.get("SECURITY_WEB_BASE_URL", "").rstrip("/")
    api_base_url: str = os.environ.get("SECURITY_API_BASE_URL", "").rstrip("/")
    admin_base_url: str = os.environ.get("SECURITY_ADMIN_BASE_URL", "").rstrip("/")

    # Primary tenant credentials (valid account)
    tenant_slug: str = os.environ.get("SECURITY_TENANT_SLUG", "")
    admin_email: str = os.environ.get("SECURITY_ADMIN_EMAIL", "")
    admin_password: str = os.environ.get("SECURITY_ADMIN_PASSWORD", "")

    # Secondary tenant for isolation tests
    secondary_tenant_slug: str = os.environ.get("SECURITY_SECONDARY_TENANT_SLUG", "")
    secondary_admin_email: str = os.environ.get("SECURITY_SECONDARY_ADMIN_EMAIL", "")
    secondary_admin_password: str = os.environ.get("SECURITY_SECONDARY_ADMIN_PASSWORD", "")

    # API tokens populated by fixtures during test runs
    primary_token: str | None = None
    secondary_token: str | None = None

    @classmethod
    def validate(cls) -> None:
        """Fail fast if required production values are missing."""
        if cls.environment == "production":
            _require("SECURITY_API_BASE_URL")
            _require("SECURITY_TENANT_SLUG")
            _require("SECURITY_ADMIN_EMAIL")
            _require("SECURITY_ADMIN_PASSWORD")


# Convenience module-level instance
config = SecurityConfig()
