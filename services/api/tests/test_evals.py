"""Offline tests for the AI quote golden-set eval harness.

These tests only exercise the harness logic and fixture parsing using the
canned responses in ``evals/fixtures/`` — no LLM API keys required. Live runs
against a real model stay manual via ``python -m evals.run_evals --live``.
"""

import json
from decimal import Decimal

import pytest
from evals.run_evals import (
    GOLDEN_PATH,
    JOB_SUMMARY_FIXTURES_PATH,
    MAX_LINE_ITEMS,
    MIN_LINE_ITEMS,
    GoldenJob,
    load_fixtures,
    load_golden_jobs,
    main,
    run_eval,
    score_job,
)

pytestmark = pytest.mark.evals

REQUIRED_JOB_FIELDS = {
    "id",
    "description",
    "property_type",
    "expected_kinds",
    "expected_keywords",
    "min_keyword_hits",
    "price_band_gbp",
}


def test_golden_jobs_parse() -> None:
    raw = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert len(raw) == 15
    for entry in raw:
        assert set(entry) >= REQUIRED_JOB_FIELDS, f"missing fields in {entry.get('id')}"
        assert len(entry["price_band_gbp"]) == 2
        assert entry["price_band_gbp"][0] < entry["price_band_gbp"][1]
        assert 1 <= entry["min_keyword_hits"] <= len(entry["expected_keywords"])

    jobs = load_golden_jobs()
    assert len(jobs) == 15
    assert len({job.id for job in jobs}) == 15
    for job in jobs:
        assert set(job.expected_kinds) <= {"labour", "material", "callout"}
        assert all(isinstance(b, Decimal) for b in job.price_band_gbp)


def test_fixtures_cover_all_golden_jobs() -> None:
    fixtures = load_fixtures()
    jobs = load_golden_jobs()
    for job in jobs:
        assert job.id in fixtures, f"no canned fixture for {job.id}"
        lines = fixtures[job.id]["line_items"]
        assert MIN_LINE_ITEMS <= len(lines) <= MAX_LINE_ITEMS
        for line in lines:
            assert {"description", "kind", "quantity", "unit", "unit_price"} <= set(line)


def test_job_summary_fixtures_cover_all_golden_jobs() -> None:
    fixtures = load_fixtures(JOB_SUMMARY_FIXTURES_PATH)
    jobs = load_golden_jobs()
    for job in jobs:
        assert job.id in fixtures, f"no job-summary canned fixture for {job.id}"
        lines = fixtures[job.id]["line_items"]
        assert 1 <= len(lines) <= 8
        for line in lines:
            assert {"description", "kind", "quantity", "unit", "unit_price"} <= set(line)
            # Job-summary fixtures must be plain-English task lines.
            assert line["kind"] == "labour"
            assert line["unit"] == "job"


async def test_offline_run_passes_threshold() -> None:
    """The canned fixtures represent 'good' LLM output: the full offline run
    should comfortably beat the default 70% gate."""
    jobs = load_golden_jobs()
    scores = await run_eval(jobs, live=False)
    assert len(scores) == len(jobs)
    assert all(score.error is None for score in scores)
    pass_rate = 100.0 * sum(1 for s in scores if s.passed) / len(scores)
    assert pass_rate >= 70.0


async def test_run_eval_records_missing_fixture_as_error() -> None:
    jobs = load_golden_jobs()
    scores = await run_eval(jobs[:1], live=False, fixtures={})
    assert scores[0].error is not None
    assert not scores[0].passed


def _make_job(**overrides: object) -> GoldenJob:
    base: dict[str, object] = {
        "id": "unit-test",
        "description": "test job",
        "property_type": None,
        "expected_kinds": ["labour", "material"],
        "expected_keywords": ["socket", "cable"],
        "min_keyword_hits": 2,
        "price_band_gbp": (Decimal("100"), Decimal("500")),
    }
    base.update(overrides)
    return GoldenJob(**base)  # type: ignore[arg-type]


def _generated(lines: list[dict[str, object]]) -> dict[str, object]:
    return {"line_items": lines, "assumptions": [], "notes": ""}


def _line(description: str, kind: str, price: str) -> dict[str, object]:
    return {
        "description": description,
        "kind": kind,
        "quantity": 1,
        "unit": "job",
        "unit_price": float(price),
        "code": None,
        "reason": "",
    }


def _validated(lines: list[tuple[str, str]]) -> dict[str, object]:
    """Build a validated result: list of (quantity, unit_price) pairs."""
    return {
        "line_items": [
            {
                "description": f"line {i}",
                "quantity": Decimal(qty),
                "unit_price": Decimal(price),
                "code": None,
                "reason": "",
            }
            for i, (qty, price) in enumerate(lines)
        ],
        "confidence": 0.5,
        "warnings": [],
        "assumptions": [],
        "notes": "",
    }


def test_score_job_pass() -> None:
    job = _make_job()
    generated = _generated(
        [
            _line("Install double socket labour", "labour", "170"),
            _line("Cable materials", "material", "80"),
        ]
    )
    validated = _validated([("1", "170"), ("1", "80"), ("1", "45")])
    score = score_job(job, generated, validated)
    assert score.passed
    assert score.total == Decimal("295")
    assert score.line_count == 3


def test_score_job_catches_missing_kind() -> None:
    job = _make_job(expected_kinds=["labour", "callout"])
    generated = _generated(
        [_line("socket labour", "labour", "170"), _line("cable materials", "material", "80")]
    )
    validated = _validated([("1", "170"), ("1", "80"), ("1", "45")])
    score = score_job(job, generated, validated)
    assert not score.kinds_ok
    assert not score.passed


def test_score_job_catches_price_outside_band() -> None:
    job = _make_job()
    generated = _generated(
        [_line("socket labour", "labour", "170"), _line("cable materials", "material", "80")]
    )
    validated = _validated([("1", "900"), ("1", "80"), ("1", "45")])
    score = score_job(job, generated, validated)
    assert not score.price_ok
    assert not score.passed


def test_score_job_catches_low_keyword_hits() -> None:
    job = _make_job(expected_keywords=["socket", "cable", "rcd"], min_keyword_hits=3)
    generated = _generated(
        [_line("socket labour", "labour", "170"), _line("cable materials", "material", "80")]
    )
    validated = _validated([("1", "170"), ("1", "80"), ("1", "45")])
    score = score_job(job, generated, validated)
    assert not score.keywords_ok
    assert not score.passed


def test_score_job_catches_line_count_out_of_range() -> None:
    job = _make_job()
    generated = _generated([_line("socket cable labour", "labour", "50")])
    validated = _validated([("1", "50"), ("1", "50")])
    score = score_job(job, generated, validated)
    assert not score.count_ok
    assert not score.passed


def test_main_offline_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Overall pass rate" in out
    assert "ev-charger-install" in out


def test_main_exits_nonzero_when_threshold_unmet() -> None:
    """A 100% threshold cannot be met if any single job fails."""
    exit_code = main(["--threshold", "101"])
    assert exit_code == 1


async def test_offline_run_job_summary_passes_threshold() -> None:
    """The job-summary canned fixtures should pass the style-aware scoring."""
    jobs = load_golden_jobs()
    scores = await run_eval(jobs, live=False, line_style="job_summary")
    assert len(scores) == len(jobs)
    assert all(score.error is None for score in scores)
    pass_rate = 100.0 * sum(1 for s in scores if s.passed) / len(scores)
    assert pass_rate >= 70.0


def test_score_job_job_summary_rejects_non_task_lines() -> None:
    """In job_summary style, a material/per-metre line fails the style check
    (the kinds column becomes style conformance)."""
    job = _make_job()
    generated = _generated(
        [
            _line("Install two double sockets", "labour", "170"),
            {
                "description": "20m twin and earth cable",
                "kind": "material",
                "quantity": 20,
                "unit": "m",
                "unit_price": 4.5,
                "code": None,
                "reason": "",
            },
        ]
    )
    validated = _validated([("1", "170"), ("20", "4.5")])
    score = score_job(job, generated, validated, line_style="job_summary")
    assert not score.kinds_ok
    assert not score.passed


def test_score_job_job_summary_accepts_task_lines() -> None:
    job = _make_job()
    generated = _generated(
        [
            _line("Install two double sockets", "labour", "170"),
            _line("Run the cable and test", "labour", "80"),
        ]
    )
    validated = _validated([("1", "170"), ("1", "80")])
    score = score_job(job, generated, validated, line_style="job_summary")
    assert score.passed


def test_main_offline_job_summary_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--line-style", "job_summary"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Line style: job_summary" in out
    assert "Overall pass rate" in out
