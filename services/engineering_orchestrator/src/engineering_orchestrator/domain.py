from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventSource(StrEnum):
    GITHUB_ISSUE = "github_issue"
    TESTFLIGHT_CRASH = "testflight_crash"
    TESTFLIGHT_FEEDBACK = "testflight_feedback"
    PRODUCTION_ALERT = "production_alert"


class RunStatus(StrEnum):
    QUEUED = "queued"
    TRIAGING = "triaging"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    AWAITING_REVIEW = "awaiting_review"
    HOTFIX_DEPLOYING = "hotfix_deploying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


TERMINAL_STATUSES = {
    RunStatus.AWAITING_REVIEW,
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.BLOCKED,
}


class EngineeringEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: EventSource
    external_id: str
    repository: str
    title: str
    body: str = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    issue_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_incident(self) -> bool:
        return (
            self.source == EventSource.PRODUCTION_ALERT
            and self.severity in {"high", "critical"}
            and self.metadata.get("alert_status") == "firing"
        )


class TriageResult(BaseModel):
    summary: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    reproduction_steps: list[str] = Field(default_factory=list)
    suspected_paths: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    command: str
    exit_code: int
    output: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


class WorkerResult(BaseModel):
    sandbox_id: str = ""
    branch: str
    base_sha: str
    head_sha: str = ""
    changed_files: list[str] = Field(default_factory=list)
    diff_lines: int = 0
    diff: str = ""
    checks: list[CheckResult] = Field(default_factory=list)
    summary: str = ""
    target_service: str = "unknown"
    dry_run: bool = False


class ReviewResult(BaseModel):
    approved: bool
    findings: list[str] = Field(default_factory=list)


class ReleaseResult(BaseModel):
    status: Literal["opened_pr", "deployed", "blocked", "failed"]
    url: str = ""
    reasons: list[str] = Field(default_factory=list)
    post_incident_pr_url: str = ""


class EngineeringRun(BaseModel):
    id: str
    event: EngineeringEvent
    status: RunStatus = RunStatus.QUEUED
    triage: TriageResult | None = None
    worker: WorkerResult | None = None
    review: ReviewResult | None = None
    release: ReleaseResult | None = None
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_event(cls, event: EngineeringEvent) -> EngineeringRun:
        return cls(id=str(uuid4()), event=event)

    def mark(self, status: RunStatus) -> None:
        self.status = status
        self.updated_at = datetime.now(UTC)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES
