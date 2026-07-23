"""Compliance grounding for the BoQ engine.

This module is the bridge between the regulatory knowledge base (loaded into
the ``quoting_knowledge`` Qdrant collection by the data pipeline) and the
quote-generation pipeline. Its responsibilities are:

1. **Detect job types** from a customer description using the same heuristic
   vocabulary the knowledge loader uses to tag chunks, so retrieval can be
   filtered to the right slice of regulation.
2. **Retrieve mandatory + default chunks** for the detected job types.
3. **Build deterministic citations** to return alongside the BoQ. Citations
   come from the chunks we actually retrieved — never from the LLM — so the
   regulatory grounding cannot hallucinate a source.
4. **Audit the resolved BoQ** against a small rule set of mandatory items
   per job type. Missing items produce compliance warnings the operator must
   reconcile before sending the quote to the customer.

Failures to reach Qdrant degrade gracefully: the BoQ is still produced and a
warning is added so the operator knows the quote has not been grounded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtp_shared import BoQLineItem, RegulatoryCitation

if TYPE_CHECKING:
    from collections.abc import Iterable

from ocerp.services.knowledge_store import (
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    KnowledgeStore,
)

logger = logging.getLogger(__name__)


# Job-type keyword heuristics. These mirror the tags the knowledge loader
# attaches to chunks (see ``data_pipeline.knowledge_loader._JOB_TYPE_HINTS``)
# so that ``job_type=rewire`` matches both detection and retrieval.
_JOB_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "rewire": ("rewire", "rewiring", "full rewire"),
    "consumer_unit": (
        "consumer unit",
        "fuse box",
        "fusebox",
        "distribution board",
        "fuse board",
        "cu upgrade",
    ),
    "ev_charger": (
        "ev charger",
        "ev charging",
        "chargepoint",
        "vehicle charger",
        "electric vehicle",
    ),
    "bathroom": (
        "bathroom",
        "shower room",
        "wet room",
        "en-suite",
        "ensuite",
        "zone 0",
        "zone 1",
        "zone 2",
    ),
    "outdoor": (
        "outdoor",
        "garden",
        "shed",
        "outbuilding",
        "garage supply",
        "external socket",
        "driveway",
        "patio",
    ),
    "shower": ("electric shower", "shower circuit"),
    "eicr": ("eicr", "condition report", "periodic inspection"),
    "lighting": ("downlight", "light fitting", "lighting circuit", "spotlight"),
    "alarm": (
        "smoke alarm",
        "fire alarm",
        "heat detector",
        "interlinked alarm",
    ),
    "solar_pv": ("solar", "solar pv", "battery storage"),
    "smart_home": ("smart home", "knx", "dali", "zigbee", "z-wave"),
}


# Mandatory items per job type. Each entry is a list of (label, match_terms)
# tuples; the BoQ passes the check if ANY ``match_term`` substring appears in
# either a line item's ``description`` or ``code`` (case-insensitive).
#
# These rules deliberately err on the side of asking the operator to confirm
# rather than silently skipping items — false positives become an audit nag,
# false negatives become a compliance liability.
_MANDATORY_ITEMS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "rewire": [
        ("Metal consumer unit with SPD", ("consumer unit", "cu ", "fuse board")),
        ("Interlinked mains smoke alarm", ("smoke alarm", "smoke detector")),
        ("Main earth bonding / equipotential bonding", ("earth bond", "bonding")),
        ("RCD or RCBO protection", ("rcd", "rcbo")),
    ],
    "consumer_unit": [
        ("Metal consumer unit enclosure", ("consumer unit", "cu enclosure")),
        ("Surge Protection Device (SPD)", ("spd", "surge protection")),
        ("RCD or RCBO protection", ("rcd", "rcbo")),
    ],
    "ev_charger": [
        ("Dedicated 32A protective device for EV circuit", ("32a", "rcbo", "mcb")),
        (
            "Type A RCD protection (or built-in DC fault detection)",
            ("type a rcd", "type a", "dc fault"),
        ),
        ("Weatherproof isolator", ("isolator", "weatherproof")),
        ("SWA / armoured cable supply", ("swa", "armoured")),
    ],
    "bathroom": [
        ("RCD protection for bathroom circuits", ("rcd", "rcbo")),
        (
            "Supplementary equipotential bonding (or modern installation note)",
            ("supplementary bonding", "equipotential"),
        ),
    ],
    "outdoor": [
        ("Weatherproof IP-rated accessory or enclosure", ("ip54", "ip55", "ip65", "weatherproof")),
        ("RCD protection on outdoor circuits", ("rcd", "rcbo")),
    ],
    "shower": [
        ("Dedicated shower MCB/RCBO sized for the unit", ("rcbo", "mcb", "shower")),
    ],
    "alarm": [
        ("Interlinked mains smoke / heat alarm", ("smoke alarm", "heat detector", "interlinked")),
    ],
}


@dataclass(frozen=True)
class ComplianceContext:
    """The grounding context attached to a BoQ generation request."""

    job_types: list[str]
    citations: list[RegulatoryCitation]
    knowledge_available: bool
    retrieval_warnings: list[str]


def detect_job_types(description: str) -> list[str]:
    """Return the set of job-type tags that match the customer description."""
    haystack = (description or "").lower()
    detected = [
        tag for tag, hints in _JOB_TYPE_HINTS.items() if any(hint in haystack for hint in hints)
    ]
    # Stable ordering for reproducibility.
    return sorted(set(detected))


def _snippet(text: str, max_chars: int = 320) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    cutoff = text.rfind(". ", 0, max_chars)
    if cutoff < max_chars // 2:
        cutoff = max_chars
    return text[:cutoff].rstrip() + "…"


def _result_to_citation(
    result: KnowledgeSearchResult,
    *,
    job_type: str | None,
) -> RegulatoryCitation:
    return RegulatoryCitation(
        chunk_id=result.id,
        source=result.source,
        section_path=list(result.section_path),
        rule_tier=result.rule_tier,
        job_type=job_type,
        snippet=_snippet(result.text),
        relevance_score=float(result.score),
    )


def _dedupe_citations(citations: Iterable[RegulatoryCitation]) -> list[RegulatoryCitation]:
    seen: set[str] = set()
    deduped: list[RegulatoryCitation] = []
    for citation in citations:
        if citation.chunk_id in seen:
            continue
        seen.add(citation.chunk_id)
        deduped.append(citation)
    return deduped


async def gather_compliance_context(
    description: str,
    *,
    knowledge_store: KnowledgeStore | None = None,
    per_job_type_limit: int = 3,
    fallback_limit: int = 3,
) -> ComplianceContext:
    """Detect job types from ``description`` and gather grounding citations.

    For every detected job type we retrieve the top mandatory and default
    chunks. If no job type is detected we still pull a few mandatory chunks
    via a plain semantic search so the LLM has SOME regulatory ballast.

    Args:
        description: Raw customer-facing job description.
        knowledge_store: Optional pre-built store; injected by tests.
        per_job_type_limit: Max mandatory + default chunks to keep per job
            type. Kept low because the prompt window is finite and the most
            relevant chunk per tier is what matters.
        fallback_limit: Number of chunks to retrieve when no job type is
            detected.

    Returns:
        A :class:`ComplianceContext` whose ``citations`` are safe to surface
        to the customer and to attach to the BoQ. When Qdrant is unreachable
        ``knowledge_available`` is False and the caller is expected to add a
        warning to the response.
    """
    job_types = detect_job_types(description)
    store = knowledge_store or KnowledgeStore()

    citations: list[RegulatoryCitation] = []
    warnings: list[str] = []
    knowledge_available = True

    try:
        if job_types:
            for job_type in job_types:
                for tier in ("mandatory", "default"):
                    try:
                        results = await store.search(
                            KnowledgeSearchRequest(
                                query=description,
                                job_type=job_type,
                                rule_tier=tier,
                                limit=per_job_type_limit,
                            )
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.warning(
                            "knowledge.retrieval_failed",
                            extra={"job_type": job_type, "tier": tier, "err": str(exc)},
                        )
                        knowledge_available = False
                        warnings.append(f"Knowledge retrieval failed for {job_type}/{tier}: {exc}")
                        continue
                    citations.extend(_result_to_citation(r, job_type=job_type) for r in results)
        else:
            try:
                results = await store.search(
                    KnowledgeSearchRequest(
                        query=description,
                        rule_tier="mandatory",
                        limit=fallback_limit,
                    )
                )
                citations.extend(_result_to_citation(r, job_type=None) for r in results)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("knowledge.retrieval_failed_fallback", extra={"err": str(exc)})
                knowledge_available = False
                warnings.append(f"Knowledge retrieval failed: {exc}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("knowledge.unexpected_failure")
        knowledge_available = False
        warnings.append(f"Compliance grounding failed: {exc}")

    if not citations and knowledge_available:
        # No regulatory chunks for this job is a soft signal, not an error: many
        # trivial jobs ("add one socket") simply have no specific rule. Leave
        # ``citations`` empty so consumers can see it and surface their own UI
        # cue if needed, but don't pollute the BoQ ``warnings`` channel.
        logger.info(
            "compliance.no_chunks", extra={"job_types": job_types, "description": description[:120]}
        )

    return ComplianceContext(
        job_types=job_types,
        citations=_dedupe_citations(citations),
        knowledge_available=knowledge_available,
        retrieval_warnings=warnings,
    )


def _haystack(line_items: list[BoQLineItem]) -> str:
    parts: list[str] = []
    for li in line_items:
        parts.append((li.description or "").lower())
        parts.append((li.code or "").lower())
        parts.append((li.notes or "").lower())
    return " | ".join(parts)


def check_mandatory_items(
    job_types: list[str],
    line_items: list[BoQLineItem],
) -> list[str]:
    """Return human-readable warnings for mandatory items missing from the BoQ.

    The warnings are framed as operator nags ("BoQ may be missing X — confirm
    before sending") rather than hard failures because the heuristic match is
    intentionally loose; we'd rather generate a few false alarms than ship a
    quote that omits a safety-critical line.
    """
    haystack = _haystack(line_items)
    warnings: list[str] = []
    seen_labels: set[str] = set()
    for job_type in job_types:
        rules = _MANDATORY_ITEMS.get(job_type)
        if not rules:
            continue
        for label, match_terms in rules:
            if label in seen_labels:
                continue
            if any(term in haystack for term in match_terms):
                continue
            seen_labels.add(label)
            warnings.append(
                f"Compliance check ({job_type}): BoQ may be missing '{label}'. "
                "Confirm before sending to customer."
            )
    return warnings


def render_citations_for_prompt(citations: list[RegulatoryCitation], max_chars: int = 4000) -> str:
    """Render citations as a compact block for inclusion in the LLM prompt.

    Mandatory chunks come first and are guaranteed to fit even if the prompt
    budget forces truncation. Each chunk is annotated with its ``chunk_id``
    so the LLM can reference it explicitly in its output if it chooses.
    """
    if not citations:
        return ""

    ordered = sorted(
        citations,
        key=lambda c: (
            0 if c.rule_tier == "mandatory" else 1 if c.rule_tier == "default" else 2,
            -c.relevance_score,
        ),
    )

    rendered: list[str] = []
    total = 0
    for c in ordered:
        section = " > ".join(c.section_path) if c.section_path else "(root)"
        entry = f"- [{c.rule_tier}] [{c.chunk_id}] {c.source} — {section}\n  {c.snippet}"
        if total + len(entry) > max_chars and rendered:
            break
        rendered.append(entry)
        total += len(entry)
    return "\n".join(rendered)
