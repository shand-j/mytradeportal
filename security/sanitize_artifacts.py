"""Sanitize security-audit JUnit and report artifacts before upload."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

SECRET_ENV_NAMES = (
    "SECURITY_TENANT_SLUG",
    "SECURITY_ADMIN_EMAIL",
    "SECURITY_ADMIN_PASSWORD",
    "SECURITY_SECONDARY_TENANT_SLUG",
    "SECURITY_SECONDARY_ADMIN_EMAIL",
    "SECURITY_SECONDARY_ADMIN_PASSWORD",
    "SECURITY_API_BASE_URL",
    "SECURITY_WEB_BASE_URL",
    "SECURITY_ADMIN_BASE_URL",
)

BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+={0,2}")
JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
)
COOKIE_PATTERN = re.compile(
    r"(?i)\b(?:session|access_token|refresh_token|auth_token|jwt)=[^;\s,]+"
)


def redact(text: str, extra_secrets: Iterable[str] = ()) -> str:
    """Replace configured values and common token representations."""
    redacted = text
    for secret in extra_secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = BEARER_PATTERN.sub("[REDACTED]", redacted)
    redacted = JWT_PATTERN.sub("[REDACTED]", redacted)
    redacted = COOKIE_PATTERN.sub(lambda match: match.group(0).split("=", 1)[0] + "=[REDACTED]", redacted)
    return redacted


def configured_secrets() -> tuple[str, ...]:
    return tuple(value for name in SECRET_ENV_NAMES if (value := os.environ.get(name, "")))


def sanitize_files(paths: Iterable[Path], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    secrets = configured_secrets()
    written: list[Path] = []
    for source in paths:
        if not source.exists():
            continue
        target = output_dir / source.name
        target.write_text(redact(source.read_text(errors="replace"), secrets), encoding="utf-8")
        written.append(target)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("security-artifacts"))
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args()

    sanitize_files(args.files, args.output)


if __name__ == "__main__":
    main()
