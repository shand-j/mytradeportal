from pathlib import Path

import pytest

pytestmark = pytest.mark.security


@pytest.fixture(scope="session", autouse=True)
def _validate_config() -> None:
    pass


def test_security_audit_selects_matching_environment() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "security-audit.yml"
    ).read_text(encoding="utf-8")

    assert "inputs.environment == 'staging'" in workflow
    assert "'MyTradePortal / staging'" in workflow
    assert "python -m security.validate_target" in workflow
    assert "python -m security.sanitize_artifacts" in workflow


def test_security_audit_requires_both_tenant_sets() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "security-audit.yml"
    ).read_text(encoding="utf-8")

    for name in (
        "SECURITY_TENANT_SLUG",
        "SECURITY_ADMIN_EMAIL",
        "SECURITY_ADMIN_PASSWORD",
        "SECURITY_SECONDARY_TENANT_SLUG",
        "SECURITY_SECONDARY_ADMIN_EMAIL",
        "SECURITY_SECONDARY_ADMIN_PASSWORD",
    ):
        assert name in workflow
