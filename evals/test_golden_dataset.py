"""Parametrised golden-dataset evaluation for the domestic electrical AI agent."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

if TYPE_CHECKING:
    import httpx

from scorer import score_case

pytestmark = [pytest.mark.asyncio, pytest.mark.eval]


RESULTS_DIR = Path(__file__).parent / "results"
GOLDEN_YAML = Path(__file__).parent / "golden_dataset.yaml"


def _load_cases() -> list[dict[str, Any]]:
    with GOLDEN_YAML.open() as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    cases: list[dict[str, Any]] = data["test_cases"]
    return cases


GOLDEN_CASES = _load_cases()


def _infer_property_type(case: dict[str, Any]) -> str | None:
    """Map a case onto a property_type hint for the OCERP backend."""
    text = case["input"].lower()
    if "bungalow" in text:
        return "bungalow"
    if "flat" in text:
        return "1_bed_flat"
    if "terrace" in text or "terraced" in text:
        return "2_bed_house"
    if "detached" in text:
        return "4_bed_house"
    if "semi" in text:
        return "3_bed_house"
    room_count = (case.get("expected") or {}).get("room_count")
    if room_count == 1:
        return "1_bed_flat"
    if room_count == 2:
        return "2_bed_house"
    if room_count == 3:
        return "3_bed_house"
    if room_count == 4:
        return "4_bed_house"
    if room_count == 5:
        return "5_bed_house"
    return None


async def _generate_boq(
    ocerp_client: httpx.AsyncClient,
    case: dict[str, Any],
    tenant_settings: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "description": case["input"],
        "trade": "electrical",
        "region": "UK",
        "property_type": _infer_property_type(case),
        "tenant_settings": tenant_settings,
    }
    response = await ocerp_client.post("/ocerp/v1/boq/generate", json=payload)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["id"])
async def test_golden_case(
    ocerp_client: httpx.AsyncClient,
    case: dict[str, Any],
    tenant_settings: dict[str, Any],
) -> None:
    """Run a single golden case through OCERP and assert the hard pass criteria.

    This test is opt-in via the EVAL_PER_CASE environment variable because it
    makes one LLM call per case.  The summary test is the default regression
    target.
    """
    if not os.environ.get("EVAL_PER_CASE"):
        pytest.skip("set EVAL_PER_CASE=1 to run per-case LLM evaluations")

    response = await _generate_boq(ocerp_client, case, tenant_settings)
    report = score_case(case, response)

    # Persist the raw response + report for regression analysis.
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{case['id']}.json"
    with result_path.open("w") as fh:
        json.dump(
            {
                "case": case,
                "response": response,
                "passed": report.passed,
                "criteria_results": [
                    {
                        "criterion": r.criterion,
                        "passed": r.passed,
                        "detail": r.detail,
                        "soft": r.soft,
                    }
                    for r in report.criteria_results
                ],
                "summary": report.summary,
            },
            fh,
            indent=2,
            default=str,
        )

    failures = [r for r in report.criteria_results if r.passed is False and not r.soft]
    if failures:
        detail = "\n".join(f"  - {r.criterion}: {r.detail}" for r in failures)
        pytest.fail(f"Case {case['id']} failed {len(failures)} hard criterion(s):\n{detail}")


async def test_golden_dataset_summary(
    golden_cases: list[dict[str, Any]],
    ocerp_client: httpx.AsyncClient,
    tenant_settings: dict[str, Any],
) -> None:
    """Run every case once and write an aggregate regression report."""
    reports = []
    for case in golden_cases:
        response = await _generate_boq(ocerp_client, case, tenant_settings)
        reports.append(score_case(case, response))

    passed = sum(1 for r in reports if r.passed)
    total = len(reports)
    by_difficulty: dict[str, dict[str, int]] = {}
    for r in reports:
        by_difficulty.setdefault(r.difficulty, {"passed": 0, "total": 0})
        by_difficulty[r.difficulty]["total"] += 1
        if r.passed:
            by_difficulty[r.difficulty]["passed"] += 1

    summary: dict[str, Any] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "by_difficulty": by_difficulty,
        "cases": [
            {
                "id": r.case_id,
                "category": r.category,
                "difficulty": r.difficulty,
                "passed": r.passed,
                "failed_criteria": [
                    c.criterion for c in r.criteria_results if c.passed is False
                ],
                # Per-case self-diagnostics so a future eval failure says
                # WHY without anyone having to grep results/*.json.
                "material_total": r.summary.get("material_total"),
                "expected_material_range": r.summary.get("expected_material_range"),
                "material_cost_delta": r.summary.get("material_cost_delta"),
                "material_cost_delta_pct": r.summary.get("material_cost_delta_pct"),
                "top_material_items": r.summary.get("top_material_items"),
            }
            for r in reports
        ],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = RESULTS_DIR / "summary.json"
    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)

    print(json.dumps(summary, indent=2))

    threshold = float(os.environ.get("GOLDEN_PASS_RATE_THRESHOLD", "0.0"))
    assert summary["pass_rate"] >= threshold, (
        f"Pass rate {summary['pass_rate']} below threshold {threshold}. "
        "See evals/results/summary.json for details."
    )
