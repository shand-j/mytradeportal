from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from engineering_orchestrator.domain import CheckResult, EngineeringRun, ReviewResult, TriageResult
from engineering_orchestrator.policy import HotfixPolicy
from fakes import BASE_SHA, FakeGitHub, FakeWorker, incident_event, make_settings

if TYPE_CHECKING:
    from pathlib import Path


def evidence(tmp_path: Path):
    event = incident_event()
    worker = FakeWorker().execute(
        EngineeringRun.from_event(event), TriageResult(summary="test"), BASE_SHA
    )
    comparison = FakeGitHub().compare(BASE_SHA, worker.head_sha)
    return event, worker, ReviewResult(approved=True), comparison


def test_policy_accepts_narrow_verified_hotfix(tmp_path: Path) -> None:
    event, worker, review, comparison = evidence(tmp_path)
    policy = HotfixPolicy(make_settings(tmp_path))
    assert policy.evaluate(event, worker, review, comparison) == []


@pytest.mark.parametrize(
    "mutation",
    [
        "disabled",
        "untrusted",
        "failed_check",
        "rejected_review",
        "wrong_base",
        "forbidden_path",
        "too_large",
        "missing_rollback",
        "wrong_service",
    ],
)
def test_policy_denies_unsafe_hotfixes(tmp_path: Path, mutation: str) -> None:
    event, worker, review, comparison = evidence(tmp_path)
    settings = make_settings(tmp_path)
    if mutation == "disabled":
        settings.hotfix_enabled = False
    elif mutation == "untrusted":
        event.metadata["trusted_alert"] = False
    elif mutation == "failed_check":
        worker.checks = [CheckResult(command="pytest", exit_code=1)]
    elif mutation == "rejected_review":
        review.approved = False
    elif mutation == "wrong_base":
        event.metadata["deployed_sha"] = "f" * 40
    elif mutation == "forbidden_path":
        comparison = deepcopy(comparison)
        comparison["engineering_changed_files"] = [".github/workflows/ci.yml"]
    elif mutation == "too_large":
        comparison = deepcopy(comparison)
        comparison["engineering_diff_lines"] = 1000
    elif mutation == "missing_rollback":
        event.metadata["rollback_sha"] = ""
    elif mutation == "wrong_service":
        worker.target_service = "admin"
    reasons = HotfixPolicy(settings).evaluate(event, worker, review, comparison)
    assert reasons, mutation
