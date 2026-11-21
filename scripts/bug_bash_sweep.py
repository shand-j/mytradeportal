#!/usr/bin/env python3
"""Generate a pre-beta bug-bash log from the BDD journey inventory."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class Scenario:
    name: str
    tags: tuple[str, ...]


UAT_ITEMS = (
    "Onboarding: tenant, bank details, card gate, free-beta access",
    "Push: foreground, background, terminated, and notification tap routing",
    "Deep links: cold/warm and authenticated/logged-out routes",
    "SMS: delivery, receipts, STOP/START, and fallback",
    "Quote refine, review keyboard UX, and VAT save-then-send",
    "Logo upload and public quote rendering",
    "Invoice lifecycle and card settlement/refund or bank-transfer-only",
    "Stripe Connect onboarding and live status sync",
    "GPS, calendar guardrails, and Apple Calendar subscription",
)


def inventory_feature(path: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    pending_tags: list[str] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("@"):
            pending_tags.extend(tag for tag in line.split() if tag.startswith("@"))
        elif line.startswith("Scenario:") or line.startswith("Scenario Outline:"):
            name = line.split(":", 1)[1].strip()
            scenarios.append(Scenario(name=name, tags=tuple(pending_tags)))
            pending_tags = []
        elif line and not line.startswith("#"):
            pending_tags = []

    return scenarios


def load_statuses(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("status JSON must contain an object")
    return {str(key): str(value).lower() for key, value in data.items()}


def current_commit(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def render_log(
    *,
    features_dir: Path,
    commit: str,
    environment: str,
    tester: str,
    statuses: dict[str, str],
    uat_statuses: dict[str, str],
) -> str:
    valid_statuses = {"pass", "fail", "not-run", "waived", "blocked"}
    lines = [
        "# Pre-beta bug-bash log",
        "",
        f"- Commit: `{commit}`",
        f"- Environment: `{environment}`",
        f"- Tester: `{tester}`",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        "- Live/device evidence: attach only sanitized artifacts; no tokens or PII",
        "",
        "## Journey sweep",
        "",
    ]

    feature_paths = sorted(features_dir.glob("*.feature"))
    total = 0
    totals = dict.fromkeys(valid_statuses, 0)

    for feature_path in feature_paths:
        scenarios = inventory_feature(feature_path)
        lines.append(f"### {feature_path.stem}")
        lines.append("")
        if not scenarios:
            lines.append("- No scenarios found")
            lines.append("")
            continue

        for scenario in scenarios:
            key = f"{feature_path.stem}:{scenario.name}"
            status = statuses.get(key, statuses.get(scenario.name, "not-run"))
            if status not in valid_statuses:
                raise ValueError(
                    f"invalid status {status!r} for {key}; expected one of {sorted(valid_statuses)}"
                )
            totals[status] += 1
            total += 1
            tags = " ".join(scenario.tags)
            tag_suffix = f" ({tags})" if tags else ""
            lines.append(f"- [{status.upper()}] {scenario.name}{tag_suffix}")
        lines.append("")

    lines.extend(
        [
            "## Summary",
            "",
            f"- Feature files: {len(feature_paths)}",
            f"- Scenarios: {total}",
            f"- PASS: {totals['pass']}",
            f"- FAIL: {totals['fail']}",
            f"- NOT-RUN: {totals['not-run']}",
            f"- BLOCKED: {totals['blocked']}",
            f"- WAIVED: {totals['waived']}",
            "",
            "## 9-item UAT smoke",
            "",
        ]
    )

    for item in UAT_ITEMS:
        status = uat_statuses.get(item, "not-run")
        if status not in valid_statuses:
            raise ValueError(
                f"invalid UAT status {status!r}; expected one of {sorted(valid_statuses)}"
            )
        lines.append(f"- [{status.upper()}] {item}")

    lines.extend(
        [
            "",
            "## Defects",
            "",
            "- P0:",
            "- P1:",
            "- P2:",
            "",
            "## Go/no-go",
            "",
            "- Outcome: NO-GO / GO WITH RESTRICTION / GO",
            "- Founder waiver or decision owner:",
            "- Evidence or issue links:",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "features",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "evidence" / "pre-beta-bug-bash.md",
    )
    parser.add_argument("--environment", default="staging")
    parser.add_argument("--tester", default="unassigned")
    parser.add_argument("--commit")
    parser.add_argument("--statuses", type=Path)
    parser.add_argument("--uat-statuses", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    commit = args.commit or current_commit(repo)
    statuses = load_statuses(args.statuses)
    uat_statuses = load_statuses(args.uat_statuses)
    log = render_log(
        features_dir=args.features,
        commit=commit,
        environment=args.environment,
        tester=args.tester,
        statuses=statuses,
        uat_statuses=uat_statuses,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(log, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
