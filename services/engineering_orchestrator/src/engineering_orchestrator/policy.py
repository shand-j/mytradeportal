from __future__ import annotations

import fnmatch
import re
from typing import TYPE_CHECKING, Any

from .domain import EngineeringEvent, EventSource, ReviewResult, WorkerResult

if TYPE_CHECKING:
    from .config import Settings

BLOCKED_HOTFIX_PATTERNS = (
    ".github/*",
    ".railway/*",
    "scripts/ci/*",
    "scripts/init_db.py",
    "services/engineering_orchestrator/*",
    "docker-compose*",
    "**/.env*",
    "**/*.pem",
    "**/*.key",
    "**/migrations/*",
    "**/auth/*",
    "**/auth.py",
    "**/security.py",
    "**/tenancy.py",
    "**/payments/*",
    "**/billing/*",
    "**/stripe/*",
    "**/paddle/*",
)


class HotfixPolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(
        self,
        event: EngineeringEvent,
        worker: WorkerResult,
        review: ReviewResult,
        comparison: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        if not self.settings.hotfix_enabled:
            reasons.append("autonomous hotfixes are disabled")
        if event.source != EventSource.PRODUCTION_ALERT or not event.is_incident:
            reasons.append("the trigger is not a firing high/critical production alert")
        if event.metadata.get("trusted_alert") is not True:
            reasons.append("the alert trust boundary is missing")
        if worker.dry_run:
            reasons.append("dry-run evidence cannot authorize a deployment")
        if worker.target_service not in self.settings.hotfix_allowed_services:
            reasons.append(f"service {worker.target_service!r} is not hotfix-eligible")
        alert_service = event.metadata.get("service")
        if alert_service and alert_service != worker.target_service:
            reasons.append("the changed service differs from the alerting service")
        if not worker.checks or any(check.exit_code != 0 for check in worker.checks):
            reasons.append("one or more independent sandbox checks did not pass")
        if not review.approved:
            reasons.append("independent review did not approve the change")
        if event.metadata.get("deployed_sha") != worker.base_sha:
            reasons.append("the hotfix base differs from the reported production SHA")
        rollback_sha = str(event.metadata.get("rollback_sha") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", rollback_sha):
            reasons.append("a full rollback commit SHA is required")
        if not self.settings.hotfix_staging_health_url.startswith("https://"):
            reasons.append("an HTTPS staging health URL is required")
        if not self.settings.hotfix_production_health_url.startswith("https://"):
            reasons.append("an HTTPS production health URL is required")

        changed_files = list(comparison.get("engineering_changed_files") or [])
        diff_lines = int(comparison.get("engineering_diff_lines") or 0)
        if not changed_files:
            reasons.append("GitHub reported an empty diff")
        if len(changed_files) > self.settings.hotfix_max_changed_files:
            reasons.append("the changed-file limit was exceeded")
        if diff_lines > self.settings.hotfix_max_diff_lines:
            reasons.append("the diff-line limit was exceeded")
        if not self.settings.hotfix_allowed_path_prefixes:
            reasons.append("no hotfix path allow-list is configured")
        for path in changed_files:
            if not any(
                path.startswith(prefix) for prefix in self.settings.hotfix_allowed_path_prefixes
            ):
                reasons.append(f"path {path!r} is outside the hotfix allow-list")
            if any(fnmatch.fnmatch(path, pattern) for pattern in BLOCKED_HOTFIX_PATTERNS):
                reasons.append(f"path {path!r} is always excluded from autonomous hotfixes")

        merge_base = (comparison.get("merge_base_commit") or {}).get("sha")
        if merge_base != worker.base_sha:
            reasons.append("GitHub could not confirm the production base commit")
        commits = comparison.get("commits") or []
        if not commits or commits[-1].get("sha") != worker.head_sha:
            reasons.append("GitHub could not confirm the hotfix head commit")
        return list(dict.fromkeys(reasons))
