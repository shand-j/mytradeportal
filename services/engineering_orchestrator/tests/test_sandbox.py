from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from engineering_orchestrator.domain import EngineeringRun, TriageResult
from engineering_orchestrator.github import GitHubTokenProvider
from engineering_orchestrator.sandbox import DryRunWorker, RailwaySandboxWorker
from fakes import github_event, make_settings

if TYPE_CHECKING:
    from pathlib import Path


def test_target_service_must_be_unambiguous(tmp_path: Path) -> None:
    assert RailwaySandboxWorker._target_service(["services/api/app/main.py"]) == "api"
    assert RailwaySandboxWorker._target_service(["mobile/app/index.tsx"]) == "mobile"
    assert (
        RailwaySandboxWorker._target_service(
            ["services/api/app/main.py", "services/admin/manage.py"]
        )
        == "multiple"
    )
    assert RailwaySandboxWorker._target_service(["docs/readme.md"]) == "unknown"


def test_sandbox_output_redacts_injected_credentials(tmp_path: Path) -> None:
    worker = RailwaySandboxWorker(make_settings(tmp_path))
    worker._secrets = ["very-secret-token"]
    assert worker._redact("token=very-secret-token") == "token=[REDACTED]"


def test_git_authentication_uses_github_basic_auth() -> None:
    command = RailwaySandboxWorker._authenticated_git()
    assert "Authorization: Basic" in command
    assert "x-access-token" in command
    assert "Bearer" not in command


def test_dry_run_worker_never_claims_a_commit() -> None:
    run = EngineeringRun.from_event(github_event())
    result = DryRunWorker().execute(run, TriageResult(summary="test"), "main")
    assert result.dry_run
    assert result.head_sha == ""
    assert result.changed_files == []


def test_controller_token_cannot_be_reused_by_sandbox(tmp_path: Path) -> None:
    provider = GitHubTokenProvider(make_settings(tmp_path, github_token="controller-token"))
    with pytest.raises(RuntimeError, match="cannot be shared"):
        provider.worker_token()

    separated = GitHubTokenProvider(
        make_settings(
            tmp_path,
            github_token="controller-token",
            sandbox_github_token="worker-token",
        )
    )
    assert separated.worker_token() == "worker-token"


def test_live_mode_rejects_static_token_without_worker_separation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="distinct sandbox GitHub token"):
        make_settings(tmp_path, mode="live", github_token="controller-token")


def test_staged_diff_secret_scanner() -> None:
    assert RailwaySandboxWorker._diff_contains_secret("token=sk-" + "A" * 24)
    assert RailwaySandboxWorker._diff_contains_secret("-----BEGIN PRIVATE KEY-----")
    assert not RailwaySandboxWorker._diff_contains_secret("OPENAI_API_KEY=your-key-here")
