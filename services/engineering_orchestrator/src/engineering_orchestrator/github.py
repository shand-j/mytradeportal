from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
import jwt

if TYPE_CHECKING:
    from .config import Settings


class GitHubTokenProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cached_token = ""
        self._expires_at = datetime.min.replace(tzinfo=UTC)
        self._worker_cached_token = ""
        self._worker_expires_at = datetime.min.replace(tzinfo=UTC)

    def token(self) -> str:
        static = self.settings.github_token.get_secret_value()
        if static:
            return static
        if datetime.now(UTC) >= self._expires_at - timedelta(minutes=2):
            self._cached_token, self._expires_at = self._installation_token()
        return self._cached_token

    def worker_token(self) -> str:
        sandbox_token = self.settings.sandbox_github_token.get_secret_value()
        if sandbox_token:
            return sandbox_token
        if self.settings.github_token.get_secret_value():
            raise RuntimeError(
                "A static controller token cannot be shared with sandboxes; configure "
                "ENGINEERING_SANDBOX_GITHUB_TOKEN without Actions permission"
            )
        if datetime.now(UTC) >= self._worker_expires_at - timedelta(minutes=2):
            self._worker_cached_token, self._worker_expires_at = self._installation_token(
                permissions={"contents": "write", "pull_requests": "write"}
            )
        return self._worker_cached_token

    def _installation_token(
        self, permissions: dict[str, str] | None = None
    ) -> tuple[str, datetime]:
        if not (
            self.settings.github_app_id
            and self.settings.github_app_installation_id
            and self.settings.github_app_private_key.get_secret_value()
        ):
            raise RuntimeError("GitHub credentials are not configured")
        now = datetime.now(UTC)
        app_jwt = jwt.encode(
            {
                "iat": int((now - timedelta(minutes=1)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": self.settings.github_app_id,
            },
            self.settings.github_app_private_key.get_secret_value().replace("\\n", "\n"),
            algorithm="RS256",
        )
        response = httpx.post(
            f"{self.settings.github_api_url}/app/installations/"
            f"{self.settings.github_app_installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
            json={"permissions": permissions} if permissions else None,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
        return str(payload["token"]), expires_at


class GitHubClient:
    def __init__(self, settings: Settings, tokens: GitHubTokenProvider | None = None) -> None:
        self.settings = settings
        self.tokens = tokens or GitHubTokenProvider(settings)
        self.client = httpx.Client(base_url=settings.github_api_url, timeout=60)

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self.client.request(
            method,
            path,
            headers={
                "Authorization": f"Bearer {self.tokens.token()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            **kwargs,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub {method} {path} failed: HTTP {response.status_code}")
        return response

    def get_commit_sha(self, ref: str) -> str:
        response = self._request("GET", f"/repos/{self.settings.repository}/commits/{quote(ref)}")
        return str(response.json()["sha"])

    def compare(self, base: str, head: str) -> dict[str, Any]:
        path = (
            f"/repos/{self.settings.repository}/compare/"
            f"{quote(base, safe='')}...{quote(head, safe='')}"
        )
        payload: dict[str, Any] = self._request("GET", path).json()
        files = payload.get("files") or []
        payload["engineering_changed_files"] = [item["filename"] for item in files]
        payload["engineering_diff_lines"] = sum(int(item.get("changes", 0)) for item in files)
        return payload

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str | None = None,
        labels: list[str] | None = None,
        issue_number: int | None = None,
    ) -> dict[str, Any]:
        base = base or self.settings.base_branch
        owner = self.settings.repository.split("/", 1)[0]
        existing: list[dict[str, Any]] = self._request(
            "GET",
            f"/repos/{self.settings.repository}/pulls",
            params={"state": "open", "head": f"{owner}:{head}", "base": base},
        ).json()
        pull: dict[str, Any]
        if existing:
            pull = existing[0]
        else:
            pull = self._request(
                "POST",
                f"/repos/{self.settings.repository}/pulls",
                json={"title": title, "body": body, "head": head, "base": base},
            ).json()
        if labels:
            self._request(
                "POST",
                f"/repos/{self.settings.repository}/issues/{pull['number']}/labels",
                json={"labels": labels},
            )
        if issue_number:
            self.comment_issue(
                issue_number, f"Engineering run opened PR #{pull['number']}: {pull['html_url']}"
            )
        return pull

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        payload: dict[str, Any] = self._request(
            "POST",
            f"/repos/{self.settings.repository}/issues",
            json={"title": title, "body": body, "labels": labels},
        ).json()
        return payload

    def comment_issue(self, issue_number: int, body: str) -> None:
        self._request(
            "POST",
            f"/repos/{self.settings.repository}/issues/{issue_number}/comments",
            json={"body": body},
        )

    def dispatch_hotfix(
        self, run_id: str, branch: str, service: str, base_sha: str, head_sha: str
    ) -> datetime:
        dispatched_at = datetime.now(UTC)
        self._request(
            "POST",
            f"/repos/{self.settings.repository}/actions/workflows/"
            f"{quote(self.settings.hotfix_workflow)}/dispatches",
            json={
                "ref": branch,
                "inputs": {
                    "run_id": run_id,
                    "service": service,
                    "base_sha": base_sha,
                    "head_sha": head_sha,
                    "branch": branch,
                    "staging_health_url": self.settings.hotfix_staging_health_url,
                    "production_health_url": self.settings.hotfix_production_health_url,
                },
            },
        )
        return dispatched_at

    def wait_for_hotfix(
        self, dispatched_at: datetime, branch: str, head_sha: str
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.hotfix_wait_seconds
        run: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            payload = self._request(
                "GET",
                f"/repos/{self.settings.repository}/actions/workflows/"
                f"{quote(self.settings.hotfix_workflow)}/runs",
                params={"event": "workflow_dispatch", "branch": branch, "per_page": 20},
            ).json()
            for candidate in payload.get("workflow_runs", []):
                created = datetime.fromisoformat(candidate["created_at"].replace("Z", "+00:00"))
                if candidate.get("head_sha") == head_sha and created >= dispatched_at - timedelta(
                    minutes=2
                ):
                    run = candidate
                    break
            if run and run.get("status") == "completed":
                return run
            time.sleep(self.settings.hotfix_poll_seconds)
        raise TimeoutError("Timed out waiting for the hotfix workflow")
