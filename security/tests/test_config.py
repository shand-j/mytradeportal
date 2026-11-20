import pytest

from security.config import SecurityConfig

pytestmark = pytest.mark.security


def test_production_requires_primary_and_secondary_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECURITY_ENVIRONMENT", "production")
    required = {
        "SECURITY_API_BASE_URL": "https://api.example.com",
        "SECURITY_TENANT_SLUG": "security-primary",
        "SECURITY_ADMIN_EMAIL": "primary@example.com",
        "SECURITY_ADMIN_PASSWORD": "test-primary-password",
        "SECURITY_SECONDARY_TENANT_SLUG": "security-secondary",
        "SECURITY_SECONDARY_ADMIN_EMAIL": "secondary@example.com",
        "SECURITY_SECONDARY_ADMIN_PASSWORD": "test-secondary-password",
    }
    for name in required:
        monkeypatch.setenv(name, required[name])

    SecurityConfig.validate()

    monkeypatch.delenv("SECURITY_SECONDARY_ADMIN_PASSWORD")
    with pytest.raises(RuntimeError, match="SECURITY_SECONDARY_ADMIN_PASSWORD"):
        SecurityConfig.validate()
