"""Agentic penetration-test orchestrator.

Spawns multiple white-hat LLM agents, each focused on a specific OWASP category or
multi-tenancy concern, and consolidates their findings into a single report. A
security-engineer agent then proposes concrete remediation steps.

Environment variables:
    OPENAI_API_KEY          - Required for LLM calls.
    LLM_MODEL               - Model to use (default: gpt-4o-mini).
    SECURITY_TARGET_URL     - Public URL of the target deployment.
    SECURITY_API_BASE_URL   - API base URL.
    SECURITY_ADMIN_BASE_URL   - Django admin base URL.
    AGENT_ARTIFACT_DIR      - Where to write reports (default: security/reports).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import litellm

from security.agents.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    SECURITY_ENGINEER_SYSTEM_PROMPT,
    WHITE_HAT_PROMPTS,
)


@dataclass
class Finding:
    category: str
    severity: str
    title: str
    description: str
    evidence: str
    remediation: str


@dataclass
class ConsolidatedReport:
    target: str
    summary: str
    findings: list[Finding]
    coverage: dict[str, Any]
    roadmap: list[dict[str, Any]]


def _build_context() -> str:
    """Gather the application context the agents will analyze."""
    repo_root = Path(__file__).resolve().parents[2]

    context_parts = [
        f"Target URL: {os.environ.get('SECURITY_TARGET_URL', 'not-set')}",
        f"API Base URL: {os.environ.get('SECURITY_API_BASE_URL', 'not-set')}",
        f"Admin Base URL: {os.environ.get('SECURITY_ADMIN_BASE_URL', 'not-set')}",
        "",
        "== Project structure ==",
    ]

    # Include key files as context.
    key_files = [
        "pyproject.toml",
        "services/api/app/main.py",
        "services/api/app/dependencies.py",
        "services/api/app/rls.py",
        "services/api/app/routers/auth.py",
        "services/api/app/routers/quotes.py",
        "services/api/app/routers/invoices.py",
        "services/api/app/routers/tenants.py",
        "web/app/package.json",
        "web/app/src/lib/api/client.ts",
        ".railway/railway.ts",
    ]
    for rel_path in key_files:
        full_path = repo_root / rel_path
        if full_path.exists():
            context_parts.append(f"\n--- {rel_path} ---\n")
            context_parts.append(full_path.read_text()[:4000])
    return "\n".join(context_parts)


async def _call_llm(system: str, user: str, expect_json: bool = True) -> str:
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    timeout = int(os.environ.get("LLM_TIMEOUT_SECONDS", "300"))
    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        timeout=timeout,
        max_tokens=4000,
    )
    content = response.choices[0].message.content or ""
    if expect_json:
        # Strip markdown fences if the model returns them.
        content = content.removeprefix("```json").removeprefix("```")
        content = content.removesuffix("```")
    return content.strip()


def _parse_findings(raw: str, category: str) -> list[Finding]:
    """Best-effort parser for agent findings."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("findings", [data])
        return [
            Finding(
                category=category,
                severity=item.get("severity", "info").lower(),
                title=item.get("title", "Untitled"),
                description=item.get("description", ""),
                evidence=item.get("evidence", ""),
                remediation=item.get("remediation", ""),
            )
            for item in data
            if isinstance(item, dict)
        ]
    except json.JSONDecodeError:
        # Fallback: wrap the raw text as a single informational finding.
        return [
            Finding(
                category=category,
                severity="info",
                title="Raw agent output",
                description="The agent did not return structured JSON.",
                evidence=raw[:2000],
                remediation="Review the agent output manually.",
            )
        ]


async def _run_white_hat_agent(agent: Any, context: str) -> list[Finding]:
    print(f"[orchestrator] Running {agent.name}...")
    raw = await _call_llm(agent.system, context)
    findings = _parse_findings(raw, agent.owasp_category)
    print(f"[orchestrator] {agent.name} produced {len(findings)} findings")
    return findings


async def _consolidate(findings: list[Finding], context: str) -> ConsolidatedReport:
    print("[orchestrator] Consolidating findings...")
    findings_json = json.dumps([asdict(f) for f in findings], indent=2)
    user = f"Context:\n{context[:2000]}\n\nAgent findings:\n{findings_json}"
    raw = await _call_llm(ORCHESTRATOR_SYSTEM_PROMPT, user)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "summary": "Consolidation failed; see raw output.",
            "findings": [],
            "coverage": {},
            "roadmap": [],
        }

    return ConsolidatedReport(
        target=os.environ.get("SECURITY_TARGET_URL", "unknown"),
        summary=data.get("summary", ""),
        findings=[
            Finding(
                category=f.get("category", "general"),
                severity=f.get("severity", "info"),
                title=f.get("title", "Untitled"),
                description=f.get("description", ""),
                evidence=f.get("evidence", ""),
                remediation=f.get("remediation", ""),
            )
            for f in data.get("findings", [])
        ],
        coverage=data.get("coverage", {}),
        roadmap=data.get("roadmap", []),
    )


async def _generate_remediation(report: ConsolidatedReport) -> dict[str, Any]:
    print("[orchestrator] Generating remediation plan...")
    raw = await _call_llm(
        SECURITY_ENGINEER_SYSTEM_PROMPT,
        json.dumps(
            {
                "target": report.target,
                "summary": report.summary,
                "findings": [asdict(f) for f in report.findings],
            },
            indent=2,
        ),
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "Failed to parse remediation output", "raw": raw}


async def run_penetration_test() -> tuple[ConsolidatedReport, dict[str, Any]]:
    """Run the full agentic penetration test workflow."""
    context = _build_context()
    findings: list[Finding] = []
    for agent in WHITE_HAT_PROMPTS:
        findings.extend(await _run_white_hat_agent(agent, context))
    report = await _consolidate(findings, context)
    remediation = await _generate_remediation(report)
    return report, remediation


async def main() -> int:
    artifact_dir = Path(os.environ.get("AGENT_ARTIFACT_DIR", "security/reports"))
    artifact_dir.mkdir(parents=True, exist_ok=True)

    report, remediation = await run_penetration_test()

    timestamp = asyncio.get_event_loop().time()
    report_path = artifact_dir / f"pen_test_report_{timestamp:.0f}.json"
    remediation_path = artifact_dir / f"remediation_plan_{timestamp:.0f}.json"

    report_path.write_text(
        json.dumps(
            {
                "target": report.target,
                "summary": report.summary,
                "findings": [asdict(f) for f in report.findings],
                "coverage": report.coverage,
                "roadmap": report.roadmap,
            },
            indent=2,
        )
    )

    remediation_path.write_text(json.dumps(remediation, indent=2))

    print(f"[orchestrator] Report saved: {report_path}")
    print(f"[orchestrator] Remediation saved: {remediation_path}")

    # Print critical/high findings to stdout for CI visibility.
    for finding in report.findings:
        if finding.severity in {"critical", "high"}:
            print(f"[!] {finding.severity.upper()}: {finding.title}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
