from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .domain import EngineeringEvent, EventSource


def normalize_github_issue(payload: dict[str, Any]) -> EngineeringEvent | None:
    if payload.get("action") not in {"opened", "reopened", "labeled"}:
        return None
    issue = payload.get("issue") or {}
    repository = payload.get("repository") or {}
    labels = {str(label.get("name", "")) for label in issue.get("labels", [])}
    if "agent:ready" not in labels:
        return None
    number = int(issue["number"])
    full_name = str(repository["full_name"])
    return EngineeringEvent(
        source=EventSource.GITHUB_ISSUE,
        external_id=f"github:{full_name}:issue:{number}",
        repository=full_name,
        title=str(issue.get("title") or f"Issue #{number}"),
        body=str(issue.get("body") or ""),
        issue_number=number,
        severity="high" if "bug" in labels else "medium",
        metadata={"labels": sorted(labels), "url": issue.get("html_url", "")},
    )


def normalize_production_alert(payload: dict[str, Any]) -> EngineeringEvent | None:
    if payload.get("status") != "firing":
        return None
    alert_id = str(payload["alert_id"])
    severity = str(payload.get("severity", "medium")).lower()
    if severity not in {"low", "medium", "high", "critical"}:
        severity = "medium"
    return EngineeringEvent(
        source=EventSource.PRODUCTION_ALERT,
        external_id=f"alert:{alert_id}",
        repository=str(payload["repository"]),
        title=str(payload.get("title") or alert_id),
        body=str(payload.get("summary") or payload.get("description") or ""),
        severity=severity,  # type: ignore[arg-type]
        metadata={
            "alert_status": "firing",
            "trusted_alert": True,
            "service": str(payload.get("service") or "unknown"),
            "deployed_sha": str(payload.get("deployed_sha") or ""),
            "rollback_sha": str(payload.get("rollback_sha") or ""),
            "runbook": str(payload.get("runbook") or ""),
        },
    )


def normalize_testflight_submission(
    payload: dict[str, Any], repository: str, crash_log: str = ""
) -> EngineeringEvent:
    kind = str(payload.get("kind") or payload.get("type") or "feedback")
    submission_id = str(payload.get("id") or payload.get("submission_id"))
    attributes = payload.get("attributes") or {}
    is_crash = "crash" in kind
    comment = str(
        attributes.get("comment") or attributes.get("feedback") or payload.get("comment") or ""
    )
    log = crash_log or str(attributes.get("crashLog") or attributes.get("crash_log") or "")
    fingerprint = str(payload.get("fingerprint") or attributes.get("fingerprint") or submission_id)
    source = EventSource.TESTFLIGHT_CRASH if is_crash else EventSource.TESTFLIGHT_FEEDBACK
    external_kind = "crash" if is_crash else "feedback"
    external_key = fingerprint if is_crash else submission_id
    return EngineeringEvent(
        source=source,
        external_id=f"testflight:{external_kind}:{external_key}",
        repository=repository,
        title=(f"TestFlight crash: {fingerprint}" if is_crash else "TestFlight beta feedback"),
        body="\n\n".join(part for part in [comment, log] if part),
        severity="high" if is_crash else "low",
        metadata={
            "submission_id": submission_id,
            "build": str(attributes.get("build") or payload.get("build") or ""),
            "app_version": str(attributes.get("appVersion") or payload.get("app_version") or ""),
            "device": str(attributes.get("device") or payload.get("device") or ""),
            "os_version": str(attributes.get("osVersion") or payload.get("os_version") or ""),
            "fingerprint": fingerprint,
        },
    )


def new_received_at() -> datetime:
    return datetime.now(UTC)
