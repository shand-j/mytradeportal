"""Minimal Mailpit REST client for the deployed write suite.

Staging and PR environments route outbound email to a shared Mailpit
instance (see docs/ci-pr-environments.md). Tests assert that customer/staff
emails were actually sent and extract magic/doc tokens from the captured
links.

Requires MAILPIT_URL (root URL, no trailing slash) and MAILPIT_BASIC_AUTH
("user:password"). Both are GitHub secrets for the staging workflow.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass

import httpx

MAILPIT_URL = os.environ.get("MAILPIT_URL", "").rstrip("/")
MAILPIT_BASIC_AUTH = os.environ.get("MAILPIT_BASIC_AUTH", "")


def mailpit_configured() -> bool:
    return bool(MAILPIT_URL and MAILPIT_BASIC_AUTH)


@dataclass
class CapturedEmail:
    subject: str
    text: str
    html: str


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=MAILPIT_URL,
        headers={
            "Authorization": f"Basic {base64.b64encode(MAILPIT_BASIC_AUTH.encode()).decode()}"
        },
        timeout=15.0,
    )


def wait_for_email(
    to: str,
    *,
    subject_includes: str | None = None,
    timeout_ms: int = 90_000,
) -> CapturedEmail:
    """Poll until an email to ``to`` (optionally matching a subject substring)
    arrives, then return its full contents."""
    if not mailpit_configured():
        raise RuntimeError("MAILPIT_URL / MAILPIT_BASIC_AUTH not set")
    deadline = time.monotonic() + timeout_ms / 1000
    wanted = to.lower()
    with _client() as client:
        while True:
            resp = client.get("/api/v1/messages")
            resp.raise_for_status()
            messages = resp.json().get("messages", [])
            match = next(
                (
                    m
                    for m in messages
                    if any((t.get("Address") or "").lower() == wanted for t in m.get("To", []))
                    and (subject_includes is None or subject_includes in m.get("Subject", ""))
                ),
                None,
            )
            if match is not None:
                full = client.get(f"/api/v1/message/{match['ID']}")
                full.raise_for_status()
                body = full.json()
                return CapturedEmail(
                    subject=body.get("Subject", ""),
                    text=body.get("Text") or "",
                    html=body.get("HTML") or "",
                )
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"no Mailpit email to {to}"
                    + (f' with subject containing "{subject_includes}"' if subject_includes else "")
                    + f" within {timeout_ms}ms"
                )
            time.sleep(3)
