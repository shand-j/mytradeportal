from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from engineering_orchestrator.github import GitHubClient
from fakes import HEAD_SHA, make_settings

if TYPE_CHECKING:
    from pathlib import Path


class Response:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def json(self) -> Any:
        return self.payload


def test_github_compare_and_pr_contract(tmp_path: Path, monkeypatch) -> None:
    client = GitHubClient(make_settings(tmp_path, github_token="controller"))
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, path: str, **kwargs: Any) -> Response:
        calls.append((method, path, kwargs))
        if path.endswith("/pulls") and method == "GET":
            return Response([])
        if path.endswith("/pulls") and method == "POST":
            return Response({"number": 12, "html_url": "https://github.test/pull/12"})
        if "/compare/" in path:
            return Response(
                {
                    "files": [
                        {"filename": "services/api/app/example.py", "changes": 4},
                        {"filename": "services/api/tests/test_example.py", "changes": 6},
                    ]
                }
            )
        return Response({})

    monkeypatch.setattr(client, "_request", request)
    comparison = client.compare("a" * 40, HEAD_SHA)
    assert comparison["engineering_changed_files"] == [
        "services/api/app/example.py",
        "services/api/tests/test_example.py",
    ]
    assert comparison["engineering_diff_lines"] == 10

    pull = client.create_pull_request(
        title="Fix example",
        body="Evidence",
        head="agent/run-1",
        labels=["agent:needs-review"],
        issue_number=7,
    )
    assert pull["number"] == 12
    assert any(path.endswith("/issues/12/labels") for _, path, _ in calls)
    assert any(path.endswith("/issues/7/comments") for _, path, _ in calls)


def test_hotfix_dispatch_contains_immutable_release_inputs(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path, github_token="controller")
    client = GitHubClient(settings)
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, path: str, **kwargs: Any) -> Response:
        calls.append((method, path, kwargs))
        return Response({})

    monkeypatch.setattr(client, "_request", request)
    before = datetime.now(UTC)
    dispatched = client.dispatch_hotfix("run-1", "hotfix/run-1", "api", "a" * 40, HEAD_SHA)
    assert dispatched >= before
    method, path, kwargs = calls[0]
    assert method == "POST"
    assert path.endswith("/hotfix.yml/dispatches")
    assert kwargs["json"]["ref"] == "hotfix/run-1"
    assert kwargs["json"]["inputs"] == {
        "run_id": "run-1",
        "service": "api",
        "base_sha": "a" * 40,
        "head_sha": HEAD_SHA,
        "branch": "hotfix/run-1",
        "staging_health_url": settings.hotfix_staging_health_url,
        "production_health_url": settings.hotfix_production_health_url,
    }
