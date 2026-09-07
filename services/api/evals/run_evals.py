"""Golden-set evaluation harness for the AI quote generation pipeline.

Runs the golden jobs in ``golden_jobs.json`` through the quote pipeline and
scores each result on four criteria:

- expected_kinds coverage (labour/material/callout kinds present)
- expected_keywords hit-rate (line-item descriptions mention >= N terms)
- ex-VAT total within the guide price band
- line-item count sanity (3-12 items)

Two modes:

- default (offline): replays canned LLM responses from ``fixtures/`` so the
  harness logic is testable without API keys.
- ``--live``: calls the real LLM via
  :func:`app.rag.generation.generate_quote_from_prompt` with an empty catalogue
  and default tenant settings. Requires ``LLM_*`` settings to be configured.

Usage (from ``services/api``)::

    python -m evals.run_evals                       # offline, canned fixtures
    python -m evals.run_evals --live                # real LLM, empty catalogue
    python -m evals.run_evals --live --with-retrieval
                                                     # real LLM + real Qdrant
                                                     # /lexical retrieval
    python -m evals.run_evals --threshold 80        # custom pass-rate gate
    python -m evals.run_evals --json-out out.json   # persist per-job scores
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

# Allow standalone execution (``python evals/run_evals.py``) by putting
# ``services/api`` on the path so the ``app`` package imports cleanly.
_API_ROOT = Path(__file__).resolve().parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.rag.validation import validate_generated_quote  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = EVALS_DIR / "golden_jobs.json"
FIXTURES_PATH = EVALS_DIR / "fixtures" / "canned_responses.json"

# Line-item count sanity bounds, matching the guidance in the LLM system prompt.
MIN_LINE_ITEMS = 3
MAX_LINE_ITEMS = 12

# Default business pricing rules for live runs, mirroring what a typical tenant
# would have configured. The catalogue is intentionally empty: the eval checks
# the model's own guide-pricing knowledge.
DEFAULT_TENANT_SETTINGS: dict[str, Any] = {
    "minimum_charge": "75.00",
    "markup_percent": "15",
    "hourly_labour_rate": "65.00",
}

VALID_KINDS = {"labour", "material", "callout"}


@dataclass
class GoldenJob:
    id: str
    description: str
    property_type: str | None
    expected_kinds: list[str]
    expected_keywords: list[str]
    min_keyword_hits: int
    price_band_gbp: tuple[Decimal, Decimal]
    # Minimum number of *material* line items whose ``code`` must reference a
    # catalogue item returned from retrieval. 0 means no requirement (labour /
    # callout-only jobs). Only enforced when ``--with-retrieval`` is on.
    min_grounded_lines: int = 0


@dataclass
class JobScore:
    job_id: str
    kinds_ok: bool
    keywords_ok: bool
    price_ok: bool
    count_ok: bool
    grounding_ok: bool
    confidence: float
    total: Decimal
    line_count: int
    grounded_lines: int = 0
    error: str | None = None
    details: list[str] = field(default_factory=list)
    retrieval_status: str | None = None
    retrieved_count: int = 0
    confidence_capped: bool = False
    top_relevance: float = 0.0
    auto_grounded: int = 0
    labour_snapped: int = 0

    @property
    def passed(self) -> bool:
        # Grounding is deliberately not part of the pass gate: it measures
        # retrieval quality (whether the catalogue offered the right items), not
        # LLM behaviour. When Kimi correctly ignores irrelevant retrieved items
        # (e.g. burglar alarms for a smoke-alarm query) the grounding count is
        # low but the quote is still right. The rate is still emitted below.
        return (
            self.error is None
            and self.kinds_ok
            and self.keywords_ok
            and self.price_ok
            and self.count_ok
        )


def load_golden_jobs(path: Path = GOLDEN_PATH) -> list[GoldenJob]:
    """Load and parse the golden dataset."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    jobs: list[GoldenJob] = []
    for entry in raw:
        band = entry["price_band_gbp"]
        jobs.append(
            GoldenJob(
                id=entry["id"],
                description=entry["description"],
                property_type=entry.get("property_type"),
                expected_kinds=list(entry["expected_kinds"]),
                expected_keywords=list(entry["expected_keywords"]),
                min_keyword_hits=int(entry["min_keyword_hits"]),
                price_band_gbp=(Decimal(str(band[0])), Decimal(str(band[1]))),
                min_grounded_lines=int(entry.get("min_grounded_lines", 0)),
            )
        )
    return jobs


def load_fixtures(path: Path = FIXTURES_PATH) -> dict[str, Any]:
    """Load the canned LLM responses used for offline runs."""
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


async def generate_live(
    job: GoldenJob, *, with_retrieval: bool = False
) -> tuple[
    dict[str, Any],
    str | None,
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Call the real LLM pipeline (imports are lazy so offline runs need no key).

    Returns ``(generated, retrieval_status, cost_items, retrieval_quality)``.
    ``cost_items`` is the real retrieved-items list (used for grounding score
    AND passed into validation so the confidence formula sees the same items
    the LLM did). ``retrieval_quality`` is the score against the configured
    gates, or ``None`` when retrieval was not exercised.
    """
    from app.rag.generation import generate_quote_from_prompt

    cost_items: list[dict[str, Any]] = []
    retrieval_status: str | None = None
    retrieval_quality: dict[str, Any] | None = None
    if with_retrieval:
        from app.rag.retrieval import (
            compute_retrieval_quality,
            search_cost_items_with_status,
        )

        cost_items, retrieval_status = await search_cost_items_with_status(job.description)
        retrieval_quality = compute_retrieval_quality(cost_items)

    generated = await generate_quote_from_prompt(
        job_description=job.description,
        cost_items=cost_items,
        tenant_settings=DEFAULT_TENANT_SETTINGS,
        property_type=job.property_type,
    )
    return generated, retrieval_status, cost_items, retrieval_quality


def score_job(
    job: GoldenJob,
    generated: dict[str, Any],
    validated: dict[str, Any],
    *,
    catalogue_codes: set[str] | None = None,
) -> JobScore:
    """Score one generated quote against the golden expectations.

    Kind and keyword scoring use the raw LLM line items (which carry ``kind``);
    price and count scoring use the validated line items, which are what would
    actually land on the quote. When ``catalogue_codes`` is provided, grounding
    counts how many material lines cite one of those codes.
    """
    raw_lines = generated.get("line_items", []) or []
    validated_lines = validated.get("line_items", []) or []

    kinds_present = {str(line.get("kind", "")).lower() for line in raw_lines}
    missing_kinds = [k for k in job.expected_kinds if k not in kinds_present]
    kinds_ok = not missing_kinds

    haystack = " ".join(str(line.get("description", "")) for line in raw_lines).lower()
    hits = [kw for kw in job.expected_keywords if kw.lower() in haystack]
    keywords_ok = len(hits) >= job.min_keyword_hits

    total = sum(
        (line["quantity"] * line["unit_price"] for line in validated_lines),
        Decimal("0"),
    )
    low, high = job.price_band_gbp
    price_ok = low <= total <= high

    line_count = len(validated_lines)
    count_ok = MIN_LINE_ITEMS <= line_count <= MAX_LINE_ITEMS

    grounded_lines = 0
    if catalogue_codes is not None:
        # Count validated (post-processed) lines so auto-grounded material
        # lines credit the aggregate. LLM-only grounding is still visible via
        # the ``auto_grounded`` field on JobScore.
        grounded_lines = sum(
            1
            for line in validated_lines
            if str(line.get("kind", "")).lower() == "material"
            and str(line.get("code") or "") in catalogue_codes
        )
    # Grounding is only enforced when retrieval ran (catalogue_codes is not
    # None); no-retrieval baselines still get an ``ok`` on this dimension so
    # baseline-vs-Phase-1 comparisons stay meaningful.
    grounding_ok = catalogue_codes is None or grounded_lines >= job.min_grounded_lines

    details: list[str] = []
    if missing_kinds:
        details.append(f"missing kinds: {missing_kinds}")
    if not keywords_ok:
        details.append(f"keyword hits {len(hits)}/{job.min_keyword_hits}: {hits}")
    if not price_ok:
        details.append(f"total £{total} outside band £{low}-£{high}")
    if not count_ok:
        details.append(f"line count {line_count} outside {MIN_LINE_ITEMS}-{MAX_LINE_ITEMS}")
    if not grounding_ok:
        details.append(f"grounded lines {grounded_lines}/{job.min_grounded_lines}")

    return JobScore(
        job_id=job.id,
        kinds_ok=kinds_ok,
        keywords_ok=keywords_ok,
        price_ok=price_ok,
        count_ok=count_ok,
        grounding_ok=grounding_ok,
        confidence=float(validated.get("confidence", 0.0)),
        total=total,
        line_count=line_count,
        grounded_lines=grounded_lines,
        details=details,
    )


async def run_eval(
    jobs: list[GoldenJob],
    *,
    live: bool,
    with_retrieval: bool = False,
    fixtures: dict[str, Any] | None = None,
) -> list[JobScore]:
    """Run every golden job through the pipeline and return per-job scores."""
    if not live and fixtures is None:
        fixtures = load_fixtures()

    scores: list[JobScore] = []
    for job in jobs:
        retrieval_status: str | None = None
        retrieved_count = 0
        catalogue_codes: set[str] | None = None
        retrieval_quality: dict[str, Any] | None = None
        try:
            if live:
                (
                    generated,
                    retrieval_status,
                    cost_items,
                    retrieval_quality,
                ) = await generate_live(job, with_retrieval=with_retrieval)
                retrieved_count = len(cost_items)
                catalogue_codes = (
                    {str(item["code"]) for item in cost_items if item.get("code") is not None}
                    if with_retrieval
                    else None
                )
            else:
                assert fixtures is not None
                if job.id not in fixtures:
                    raise KeyError(f"no canned fixture for job '{job.id}'")
                generated = fixtures[job.id]
                cost_items = []
            validated = validate_generated_quote(
                generated=generated,
                retrieved_items=cost_items,
                tenant_settings=DEFAULT_TENANT_SETTINGS,
                retrieval_quality=retrieval_quality,
            )
            score = score_job(job, generated, validated, catalogue_codes=catalogue_codes)
            score.retrieval_status = retrieval_status
            score.retrieved_count = retrieved_count
            score.confidence_capped = bool(validated.get("confidence_capped"))
            score.auto_grounded = int(validated.get("auto_grounded", 0))
            score.labour_snapped = int(validated.get("labour_snapped", 0))
            if retrieval_quality is not None:
                score.top_relevance = float(retrieval_quality.get("top_relevance", 0.0))
            scores.append(score)
        except Exception as exc:
            scores.append(
                JobScore(
                    job_id=job.id,
                    kinds_ok=False,
                    keywords_ok=False,
                    price_ok=False,
                    count_ok=False,
                    grounding_ok=False,
                    confidence=0.0,
                    total=Decimal("0"),
                    line_count=0,
                    error=f"{type(exc).__name__}: {exc}",
                    retrieval_status=retrieval_status,
                    retrieved_count=retrieved_count,
                )
            )
    return scores


def print_report(scores: list[JobScore], threshold: float) -> float:
    """Print the per-job table plus aggregate summary; return overall pass rate."""
    print(
        f"{'job':<28} {'kinds':<6} {'kw':<6} {'price':<6} {'count':<6} "
        f"{'grnd':<6} {'conf':<5} total"
    )
    print("-" * 84)
    for s in scores:
        if s.error:
            print(f"{s.job_id:<28} ERROR  {s.error}")
            continue
        marks = [
            "ok" if s.kinds_ok else "FAIL",
            "ok" if s.keywords_ok else "FAIL",
            "ok" if s.price_ok else "FAIL",
            "ok" if s.count_ok else "FAIL",
            "ok" if s.grounding_ok else "FAIL",
        ]
        print(
            f"{s.job_id:<28} {marks[0]:<6} {marks[1]:<6} {marks[2]:<6} "
            f"{marks[3]:<6} {marks[4]:<6} {s.confidence:<5.2f} £{s.total}"
        )
        for detail in s.details:
            print(f"{'':<28} - {detail}")

    total = len(scores)
    passed = sum(1 for s in scores if s.passed)
    pass_rate = 100.0 * passed / total if total else 0.0

    def rate(ok: int) -> str:
        return f"{100.0 * ok / total:.0f}%" if total else "n/a"

    print("\nAggregate:")
    print(f"  kinds coverage:  {rate(sum(1 for s in scores if s.kinds_ok))}")
    print(f"  keyword hit-rate: {rate(sum(1 for s in scores if s.keywords_ok))}")
    print(f"  price in band:   {rate(sum(1 for s in scores if s.price_ok))}")
    print(f"  count sanity:    {rate(sum(1 for s in scores if s.count_ok))}")
    print(f"  catalogue grounded lines: {rate(sum(1 for s in scores if s.grounding_ok))}")

    statuses = [s.retrieval_status for s in scores if s.retrieval_status is not None]
    if statuses:
        grounded = sum(1 for s in statuses if s == "grounded")
        avg_items = sum(s.retrieved_count for s in scores) / max(len(scores), 1)
        print(f"  retrieval grounded: {rate(grounded)} (avg {avg_items:.1f} items/query)")
        total_grounded_lines = sum(s.grounded_lines for s in scores)
        print(f"  total material lines citing catalogue: {total_grounded_lines}")
        capped = sum(1 for s in scores if s.confidence_capped)
        print(f"  confidence capped by retrieval-quality gate: {rate(capped)}")
        top_rels = [s.top_relevance for s in scores if s.top_relevance > 0]
        if top_rels:
            print(f"  mean top-relevance: {sum(top_rels) / len(top_rels):.3f}")
        total_auto = sum(s.auto_grounded for s in scores)
        jobs_with_auto = sum(1 for s in scores if s.auto_grounded > 0)
        print(
            f"  auto-grounded material lines (fuzzy fallback): {total_auto} "
            f"across {jobs_with_auto} job(s)"
        )
        total_snap = sum(s.labour_snapped for s in scores)
        jobs_with_snap = sum(1 for s in scores if s.labour_snapped > 0)
        print(
            f"  labour lines snapped to tenant hourly rate: {total_snap} "
            f"across {jobs_with_snap} job(s)"
        )

    passing_conf = [s.confidence for s in scores if s.passed]
    failing_conf = [s.confidence for s in scores if not s.passed and s.error is None]
    if passing_conf:
        print(f"  mean confidence (passing): {sum(passing_conf) / len(passing_conf):.2f}")
    if failing_conf:
        print(f"  mean confidence (failing): {sum(failing_conf) / len(failing_conf):.2f}")

    print(f"\nOverall pass rate: {pass_rate:.0f}% ({passed}/{total}), threshold {threshold:.0f}%")
    return pass_rate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the real LLM instead of replaying canned fixtures.",
    )
    parser.add_argument(
        "--with-retrieval",
        action="store_true",
        help=(
            "Exercise the retrieval layer (Qdrant if embeddings are configured, "
            "else Postgres lexical fallback). Only meaningful with --live."
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Persist per-job scores as JSON for before/after comparison.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=70.0,
        help="Minimum overall pass rate (percent) for a zero exit code (default: 70).",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=GOLDEN_PATH,
        help="Path to the golden jobs JSON file.",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=FIXTURES_PATH,
        help="Path to the canned-response fixtures JSON file (offline mode).",
    )
    args = parser.parse_args(argv)

    if args.live and args.with_retrieval:
        # Preflight Qdrant: an unreachable vector store makes every job fail
        # identically with ``ResponseHandlingException: All connection attempts
        # failed``, which reads like an LLM problem. Better to bail loudly with
        # a clear message than to burn ~20 minutes on 15 identical errors.
        try:
            from app.config import settings as _api_settings
            from qdrant_client import QdrantClient

            probe = QdrantClient(url=_api_settings.qdrant_url, timeout=3)
            probe.get_collection(_api_settings.qdrant_collection_name)
            probe.close()
        except Exception as exc:
            print(
                f"error: cannot reach Qdrant at {_api_settings.qdrant_url} "
                f"(collection {_api_settings.qdrant_collection_name!r}): {exc}\n"
                f"start it with: docker compose up -d qdrant",
                file=sys.stderr,
            )
            return 2

    jobs = load_golden_jobs(args.golden)
    fixtures = None if args.live else load_fixtures(args.fixtures)
    scores = asyncio.run(
        run_eval(
            jobs,
            live=args.live,
            with_retrieval=args.with_retrieval,
            fixtures=fixtures,
        )
    )
    pass_rate = print_report(scores, args.threshold)
    if args.json_out is not None:
        args.json_out.write_text(
            json.dumps(
                {
                    "pass_rate": pass_rate,
                    "threshold": args.threshold,
                    "live": args.live,
                    "with_retrieval": args.with_retrieval,
                    "scores": [{**asdict(s), "total": str(s.total)} for s in scores],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nWrote per-job scores to {args.json_out}")
    return 0 if pass_rate >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
