from pathlib import Path

import pytest

from security.sanitize_artifacts import configured_secrets, redact, sanitize_files

pytestmark = pytest.mark.security


@pytest.fixture(scope="session", autouse=True)
def _validate_config() -> None:
    pass


def test_redact_removes_configured_bearer_and_jwt_values() -> None:
    jwt = ".".join(("eyJ" + "a" * 10, "b" * 12, "c" * 20))
    source = (
        "Authorization: Bearer " + ("z" * 24) + "\n"
        f"JWT={jwt}\n"
        "Cookie: session=cookie-secret\n"
        "configured=test-password\n"
    )

    result = redact(source, ("test-password", "super-secret-token"))

    assert "super-secret-token" not in result
    assert jwt not in result
    assert "test-password" not in result
    assert "cookie-secret" not in result
    assert "session=[REDACTED]" in result


def test_configured_secrets_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_ADMIN_PASSWORD", "only-in-environment")
    assert "only-in-environment" in configured_secrets()


def test_sanitize_files_writes_replacement(tmp_path: Path) -> None:
    source = tmp_path / "results.xml"
    source.write_text(
        "Authorization: Bearer " + ("z" * 24),
        encoding="utf-8",
    )
    output = tmp_path / "sanitized"

    written = sanitize_files((source,), output)

    assert len(written) == 1
    assert "[REDACTED]" in written[0].read_text(encoding="utf-8")
