import pytest

from security.config import SecurityConfig

pytestmark = pytest.mark.security


@pytest.fixture(scope="session", autouse=True)
def _validate_config() -> None:
    """Override security/conftest.py::_validate_config for this unit-test module.

    These tests call SecurityConfig.validate() directly, so they intentionally
    do not require a live target or live credentials.
    """


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


def test_local_environment_requires_primary_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_ENVIRONMENT", "local")
    monkeypatch.setenv("SECURITY_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("SECURITY_TENANT_SLUG", "security-primary")
    monkeypatch.setenv("SECURITY_ADMIN_EMAIL", "primary@example.com")
    monkeypatch.setenv("SECURITY_ADMIN_PASSWORD", "test-primary-password")
    monkeypatch.delenv("SECURITY_SECONDARY_TENANT_SLUG", raising=False)
    monkeypatch.delenv("SECURITY_SECONDARY_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("SECURITY_SECONDARY_ADMIN_PASSWORD", raising=False)

    SecurityConfig.validate()


def test_primary_credentials_are_always_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_ENVIRONMENT", "local")
    monkeypatch.setenv("SECURITY_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("SECURITY_TENANT_SLUG", "security-primary")
    monkeypatch.setenv("SECURITY_ADMIN_EMAIL", "primary@example.com")
    monkeypatch.delenv("SECURITY_ADMIN_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="SECURITY_ADMIN_PASSWORD"):
        SecurityConfig.validate()
