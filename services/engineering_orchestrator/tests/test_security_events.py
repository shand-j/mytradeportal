from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from engineering_orchestrator.events import (
    normalize_github_issue,
    normalize_production_alert,
    normalize_testflight_submission,
)
from engineering_orchestrator.security import github_signature_valid, signed_payload_valid


def signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_github_signature_and_tamper_detection() -> None:
    body = b'{"action":"opened"}'
    signed = signature("secret", body)
    assert github_signature_valid("secret", body, signed)
    assert not github_signature_valid("secret", body + b" ", signed)
    assert not github_signature_valid("", body, signed)
    assert not github_signature_valid("secret", body, "bad")


def test_signed_payload_has_expiry() -> None:
    body = b"{}"
    timestamp = datetime.now(UTC).isoformat()
    digest = hmac.new(b"secret", f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    assert signed_payload_valid("secret", body, digest, timestamp)
    stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    assert not signed_payload_valid("secret", body, digest, stale)
    assert not signed_payload_valid("secret", body, digest, "not-a-date")


def issue_payload(labels: list[str]) -> dict:
    return {
        "action": "opened",
        "issue": {
            "number": 7,
            "title": "Broken job",
            "body": "It fails",
            "labels": [{"name": label} for label in labels],
            "html_url": "https://github.test/issues/7",
        },
        "repository": {"full_name": "owner/repo"},
    }


def test_issue_requires_ready_label() -> None:
    assert normalize_github_issue(issue_payload(["bug"])) is None
    event = normalize_github_issue(issue_payload(["bug", "agent:ready"]))
    assert event is not None
    assert event.external_id == "github:owner/repo:issue:7"
    assert event.severity == "high"


def test_alert_normalization_ignores_resolved() -> None:
    payload = {
        "alert_id": "a1",
        "repository": "owner/repo",
        "status": "resolved",
        "severity": "critical",
    }
    assert normalize_production_alert(payload) is None
    payload["status"] = "firing"
    payload["deployed_sha"] = "a" * 40
    event = normalize_production_alert(payload)
    assert event is not None
    assert event.is_incident
    assert event.metadata["trusted_alert"] is True


def test_testflight_crash_deduplicates_by_fingerprint() -> None:
    first = normalize_testflight_submission(
        {"id": "submission-1", "kind": "crash", "fingerprint": "NullPointer-example"},
        "owner/repo",
        "stack trace",
    )
    second = normalize_testflight_submission(
        {"id": "submission-2", "kind": "crash", "fingerprint": "NullPointer-example"},
        "owner/repo",
    )
    assert first.external_id == second.external_id
    assert first.body == "stack trace"
    assert first.severity == "high"
