from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engineering_orchestrator.config import Settings
from engineering_orchestrator.domain import (
    CheckResult,
    EngineeringEvent,
    EngineeringRun,
    EventSource,
    TriageResult,
    WorkerResult,
)
from engineering_orchestrator.runtime import Runtime
from engineering_orchestrator.store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
ROLLBACK_SHA = "c" * 40


class FakeWorker:
    def __init__(self, checks: list[CheckResult] | None = None, dry_run: bool = False) -> None:
        self.checks = checks or [CheckResult(command="pytest", exit_code=0, output="passed")]
        self.dry_run = dry_run

    def execute(self, run: EngineeringRun, triage: TriageResult, base_ref: str) -> WorkerResult:
        return WorkerResult(
            sandbox_id="sandbox-test",
            branch=f"{'hotfix' if run.event.is_incident else 'agent'}/{run.id}",
            base_sha=BASE_SHA if self.dry_run is False else base_ref,
            head_sha="" if self.dry_run else HEAD_SHA,
            changed_files=[] if self.dry_run else ["services/api/app/example.py"],
            diff_lines=0 if self.dry_run else 4,
            diff=""
            if self.dry_run
            else "diff --git a/services/api/app/example.py b/services/api/app/example.py",
            checks=[] if self.dry_run else self.checks,
            summary="implemented",
            target_service="api",
            dry_run=self.dry_run,
        )


class FakeGitHub:
    def __init__(self) -> None:
        self.pull_requests: list[dict[str, Any]] = []
        self.comparisons: list[tuple[str, str]] = []
        self.dispatches: list[tuple[str, str, str, str, str]] = []
        self.issues: list[tuple[str, str, list[str]]] = []
        self.comments: list[tuple[int, str]] = []
        self.workflow_conclusion = "success"

    def create_pull_request(self, **kwargs: Any) -> dict[str, Any]:
        self.pull_requests.append(kwargs)
        number = len(self.pull_requests)
        return {"number": number, "html_url": f"https://github.test/pull/{number}"}

    def compare(self, base: str, head: str) -> dict[str, Any]:
        self.comparisons.append((base, head))
        return {
            "merge_base_commit": {"sha": base},
            "commits": [{"sha": head}],
            "engineering_changed_files": ["services/api/app/example.py"],
            "engineering_diff_lines": 4,
        }

    def dispatch_hotfix(
        self, run_id: str, branch: str, service: str, base_sha: str, head_sha: str
    ) -> Any:
        from datetime import UTC, datetime

        self.dispatches.append((run_id, branch, service, base_sha, head_sha))
        return datetime.now(UTC)

    def wait_for_hotfix(self, dispatched_at: Any, branch: str, head_sha: str) -> dict[str, Any]:
        return {"conclusion": self.workflow_conclusion, "html_url": "https://github.test/actions/1"}

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        self.issues.append((title, body, labels))
        return {"number": 42, "html_url": "https://github.test/issues/42"}

    def comment_issue(self, issue_number: int, body: str) -> None:
        self.comments.append((issue_number, body))


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "mode": "dry_run",
        "database_url": f"sqlite:///{tmp_path}/runs.db",
        "repository": "owner/repo",
        "api_auth_token": "operator-token",
        "github_webhook_secret": "github-secret",
        "alert_webhook_secret": "alert-secret",
        "testflight_webhook_secret": "testflight-secret",
        "hotfix_enabled": True,
        "hotfix_allowed_services": ["api"],
        "hotfix_allowed_path_prefixes": ["services/api/app/"],
        "hotfix_staging_health_url": "https://staging.example.test/ready",
        "hotfix_production_health_url": "https://api.example.test/ready",
        "hotfix_poll_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def make_runtime(
    tmp_path: Path,
    *,
    worker: FakeWorker | None = None,
    github: FakeGitHub | None = None,
    llm: Any = None,
    **settings_overrides: Any,
) -> Runtime:
    settings = make_settings(tmp_path, **settings_overrides)
    return Runtime(
        settings,
        store=RunStore(settings.database_url),
        worker=worker or FakeWorker(),
        github=github or FakeGitHub(),
        llm=llm,
    )


def github_event(repository: str = "owner/repo") -> EngineeringEvent:
    return EngineeringEvent(
        source=EventSource.GITHUB_ISSUE,
        external_id="github:owner/repo:issue:1",
        repository=repository,
        title="Fix the example",
        body="The example fails when used twice.",
        issue_number=1,
    )


def incident_event() -> EngineeringEvent:
    return EngineeringEvent(
        source=EventSource.PRODUCTION_ALERT,
        external_id="alert:incident-1",
        repository="owner/repo",
        title="Production errors are elevated",
        body="The example endpoint is failing.",
        severity="critical",
        metadata={
            "alert_status": "firing",
            "trusted_alert": True,
            "service": "api",
            "deployed_sha": BASE_SHA,
            "rollback_sha": ROLLBACK_SHA,
        },
    )
