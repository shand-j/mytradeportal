from __future__ import annotations

from typing import TYPE_CHECKING

from engineering_orchestrator.domain import CheckResult, EngineeringRun, RunStatus
from engineering_orchestrator.flow import EngineeringFlow
from fakes import FakeGitHub, FakeWorker, github_event, incident_event, make_runtime
from stub_llm import StubLLM, prompt_text

if TYPE_CHECKING:
    from pathlib import Path


def llm() -> StubLLM:
    return StubLLM(
        responses=[
            {
                "summary": "Fix the example regression",
                "acceptance_criteria": ["The example can be used twice"],
                "reproduction_steps": ["Call the example twice"],
                "suspected_paths": ["services/api/app/example.py"],
            },
            {"approved": True, "findings": []},
        ]
    )


def execute(runtime, event) -> EngineeringRun:
    run = EngineeringRun.from_event(event)
    runtime.store.save(run)
    flow = EngineeringFlow(runtime=runtime, llm=runtime._llm)
    flow.kickoff(inputs={"run_id": run.id})
    result = runtime.store.get(run.id)
    assert result is not None
    return result


def test_normal_change_runs_crewai_and_opens_pr(tmp_path: Path) -> None:
    github = FakeGitHub()
    stub = llm()
    runtime = make_runtime(tmp_path, github=github, llm=stub)
    run = execute(runtime, github_event())
    assert run.status == RunStatus.AWAITING_REVIEW
    assert run.release.url == "https://github.test/pull/1"
    assert len(github.pull_requests) == 1
    assert len(stub.calls) == 2
    assert "Fix the example" in prompt_text(stub.calls[0])
    assert "diff --git" in prompt_text(stub.calls[1])
    runtime.close()


def test_verified_incident_dispatches_hotfix_and_opens_followup_pr(tmp_path: Path) -> None:
    github = FakeGitHub()
    runtime = make_runtime(tmp_path, github=github, llm=llm())
    run = execute(runtime, incident_event())
    assert run.status == RunStatus.COMPLETED
    assert run.release.status == "deployed"
    assert run.release.post_incident_pr_url == "https://github.test/pull/1"
    assert len(github.dispatches) == 1
    assert github.pull_requests[0]["labels"] == [
        "agent:post-incident",
        "incident:needs-human-review",
    ]
    runtime.close()


def test_denied_incident_opens_pr_without_dispatch(tmp_path: Path) -> None:
    github = FakeGitHub()
    runtime = make_runtime(tmp_path, github=github, llm=llm(), hotfix_enabled=False)
    run = execute(runtime, incident_event())
    assert run.status == RunStatus.BLOCKED
    assert "autonomous hotfixes are disabled" in run.release.reasons
    assert github.dispatches == []
    assert github.pull_requests[0]["labels"] == [
        "agent:needs-review",
        "incident:needs-human-review",
    ]
    runtime.close()


def test_failed_independent_check_stops_before_review_or_pr(tmp_path: Path) -> None:
    github = FakeGitHub()
    stub = llm()
    worker = FakeWorker(checks=[CheckResult(command="pytest", exit_code=1, output="failed")])
    runtime = make_runtime(tmp_path, worker=worker, github=github, llm=stub)
    run = execute(runtime, github_event())
    assert run.status == RunStatus.FAILED
    assert "pytest" in run.error
    assert len(stub.calls) == 1
    assert github.pull_requests == []
    runtime.close()


def test_dry_run_finishes_without_external_writes(tmp_path: Path) -> None:
    github = FakeGitHub()
    runtime = make_runtime(tmp_path, worker=FakeWorker(dry_run=True), github=github)
    run = execute(runtime, github_event())
    assert run.status == RunStatus.COMPLETED
    assert run.worker.dry_run
    assert github.pull_requests == []
    runtime.close()
