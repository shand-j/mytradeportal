from __future__ import annotations

from typing import TYPE_CHECKING

from .domain import EngineeringRun, ReleaseResult, ReviewResult, WorkerResult
from .policy import HotfixPolicy

if TYPE_CHECKING:
    from .config import Settings
    from .github import GitHubClient


class ReleaseService:
    def __init__(
        self,
        settings: Settings,
        github: GitHubClient,
        policy: HotfixPolicy | None = None,
    ) -> None:
        self.settings = settings
        self.github = github
        self.policy = policy or HotfixPolicy(settings)

    def open_pr(self, run: EngineeringRun, incident: bool = False) -> ReleaseResult:
        worker = self._worker(run)
        labels = ["agent:needs-review"]
        if incident:
            labels.append("incident:needs-human-review")
        pull = self.github.create_pull_request(
            title=f"[agent] {run.event.title}"[:250],
            body=self._pr_body(run),
            head=worker.branch,
            labels=labels,
            issue_number=run.event.issue_number,
        )
        return ReleaseResult(status="opened_pr", url=pull["html_url"])

    def hotfix(self, run: EngineeringRun) -> ReleaseResult:
        worker = self._worker(run)
        review = run.review or ReviewResult(approved=False, findings=["Review is missing"])
        comparison = self.github.compare(worker.base_sha, worker.head_sha)
        reasons = self.policy.evaluate(run.event, worker, review, comparison)
        if reasons:
            opened = self.open_pr(run, incident=True)
            return ReleaseResult(
                status="blocked",
                url=opened.url,
                reasons=reasons,
            )
        dispatched_at = self.github.dispatch_hotfix(
            run.id,
            worker.branch,
            worker.target_service,
            worker.base_sha,
            worker.head_sha,
        )
        workflow = self.github.wait_for_hotfix(dispatched_at, worker.branch, worker.head_sha)
        if workflow.get("conclusion") != "success":
            return ReleaseResult(
                status="failed",
                url=str(workflow.get("html_url") or ""),
                reasons=[f"hotfix workflow concluded {workflow.get('conclusion')!r}"],
            )
        followup = self.github.create_pull_request(
            title=f"[post-incident] {run.event.title}"[:250],
            body=self._pr_body(run)
            + "\n\nThis hotfix was deployed through the guarded incident workflow. Review and merge it to prevent regression on the next main deployment.",
            head=worker.branch,
            labels=["agent:post-incident", "incident:needs-human-review"],
        )
        return ReleaseResult(
            status="deployed",
            url=str(workflow.get("html_url") or ""),
            post_incident_pr_url=str(followup["html_url"]),
        )

    def _pr_body(self, run: EngineeringRun) -> str:
        worker = self._worker(run)
        checks = "\n".join(
            f"- `{'PASS' if check.passed else 'FAIL'}` `{check.command}`" for check in worker.checks
        )
        findings = "\n".join(
            f"- {finding}" for finding in (run.review.findings if run.review else [])
        )
        return (
            f"## Engineering run `{run.id}`\n\n"
            f"Source: `{run.event.source.value}` / `{run.event.external_id}`\n\n"
            f"{run.triage.summary if run.triage else run.event.title}\n\n"
            f"### Verification\n{checks or '- No checks recorded'}\n\n"
            f"### Independent review\n{findings or '- No findings'}\n\n"
            f"Base: `{worker.base_sha}`\n\nHead: `{worker.head_sha}`\n\n"
            "Full sandbox commands and outputs are retained in the orchestrator run record."
        )

    @staticmethod
    def _worker(run: EngineeringRun) -> WorkerResult:
        if run.worker is None:
            raise RuntimeError("Worker evidence is missing")
        return run.worker
