#!/usr/bin/env python3
"""Diagnostic: for a single golden job, print what retrieval returns and what
the LLM produces, so we can tell whether grounding failures are Kimi's fault
or retrieval's fault.

Usage (from ``services/api``)::

    python -m evals.diagnose_job smoke-alarms
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from evals.run_evals import DEFAULT_TENANT_SETTINGS, load_golden_jobs  # noqa: E402


async def diagnose(job_id: str) -> int:
    jobs = {job.id: job for job in load_golden_jobs()}
    if job_id not in jobs:
        print(f"unknown job id: {job_id}", file=sys.stderr)
        print(f"available: {', '.join(sorted(jobs))}", file=sys.stderr)
        return 2

    job = jobs[job_id]
    from app.rag.generation import generate_quote_from_prompt
    from app.rag.retrieval import search_cost_items_with_status, search_knowledge_chunks

    print(f"=== Job: {job.id} ===")
    print(f"Description: {job.description}\n")
    print(f"Expected: kinds={job.expected_kinds} keywords={job.expected_keywords}")
    print(f"Grounding target: min {job.min_grounded_lines} lines")
    print(f"Price band: £{job.price_band_gbp[0]}-£{job.price_band_gbp[1]}\n")

    items, status = await search_cost_items_with_status(job.description)
    print(f"=== Retrieval: status={status}, {len(items)} items ===")
    for i, item in enumerate(items, start=1):
        score = item.get("score")
        score_str = f"{score:.3f}" if isinstance(score, float) else str(score)
        print(
            f"  {i}. score={score_str} | "
            f"{item['description'][:100]}... | "
            f"code={item['code']} | £{item['unit_price']}/{item['unit']}"
        )
    print()

    knowledge = await search_knowledge_chunks(job.description, top_k=3)
    print(f"=== Knowledge: {len(knowledge)} chunks ===")
    for i, chunk in enumerate(knowledge, start=1):
        score = chunk.get("score")
        score_str = f"{score:.3f}" if isinstance(score, float) else str(score)
        summary = (chunk.get("text") or "").split("\n", 1)[0][:100]
        print(
            f"  {i}. score={score_str} | doc={chunk.get('doc_type')} | "
            f"src={chunk.get('source')} | {summary}"
        )
    print()

    generated = await generate_quote_from_prompt(
        job_description=job.description,
        cost_items=items,
        tenant_settings=DEFAULT_TENANT_SETTINGS,
        property_type=job.property_type,
        knowledge_chunks=knowledge,
    )

    print("=== LLM output ===")
    print(f"Notes: {generated.get('notes', '')}")
    print(f"Assumptions: {generated.get('assumptions', [])}\n")
    print("Line items:")
    total = 0.0
    grounded_count = 0
    for line in generated.get("line_items", []) or []:
        kind = line.get("kind")
        code = line.get("code")
        ref = line.get("catalogue_ref")
        qty = float(line.get("quantity", 0) or 0)
        price = float(line.get("unit_price", 0) or 0)
        subtotal = qty * price
        total += subtotal
        if kind == "material" and code:
            grounded_count += 1
        marker = (
            "GROUNDED"
            if code and kind == "material"
            else "ungrounded"
            if kind == "material"
            else "-"
        )
        print(
            f"  [{kind:<8}] ref={ref!s:<6} code={code!s:<25} "
            f"qty={qty:<6.1f} @ £{price:<7.2f} = £{subtotal:<8.2f} {marker}"
        )
        print(f"    desc: {line.get('description', '')[:100]}")
    print(
        f"\nTotal: £{total:.2f} | material grounded: {grounded_count} "
        f"| target: >= {job.min_grounded_lines}"
    )

    from app.rag.retrieval import compute_retrieval_quality
    from app.rag.validation import validate_generated_quote

    quality = compute_retrieval_quality(items)
    validated = validate_generated_quote(
        generated=generated,
        retrieved_items=items,
        tenant_settings=DEFAULT_TENANT_SETTINGS,
        retrieval_quality=quality,
    )
    print("\n=== After validation (auto-grounding + confidence gates) ===")
    print(
        f"confidence: {validated['confidence']:.2f} "
        f"(capped={validated['confidence_capped']}) | "
        f"auto_grounded: {validated['auto_grounded']} lines | "
        f"labour_snapped: {validated.get('labour_snapped', 0)} lines"
    )
    print(
        f"retrieval quality: passes_gates={quality['passes_gates']} "
        f"top_relevance={quality['top_relevance']} citations={quality['citations']}"
    )
    val_total = 0.0
    val_grounded = 0
    for line in validated["line_items"]:
        kind = line.get("kind")
        code = line.get("code")
        qty = float(line.get("quantity") or 0)
        price = float(line.get("unit_price") or 0)
        subtotal = qty * price
        val_total += subtotal
        if kind == "material" and code:
            val_grounded += 1
        marker = "GROUNDED" if code and kind == "material" else "-"
        print(
            f"  [{kind or '-':<8}] code={code!s:<28} "
            f"qty={qty:<6.1f} @ £{price:<7.2f} = £{subtotal:<8.2f} {marker}"
        )
    print(f"\nValidated total: £{val_total:.2f} | grounded material lines: {val_grounded}")
    for warning in validated.get("warnings", []):
        print(f"  warn: {warning}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("job_id", help="Golden job id (e.g. smoke-alarms)")
    args = parser.parse_args()
    sys.exit(asyncio.run(diagnose(args.job_id)))


if __name__ == "__main__":
    main()
