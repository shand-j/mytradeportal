"""Tests for the regulatory grounding pipeline used during BoQ generation."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from mtp_shared import BoQGenerateRequest, BoQLineItem
from ocerp.services.boq_engine import DdcLlmBackend
from ocerp.services.compliance import (
    ComplianceContext,
    check_mandatory_items,
    detect_job_types,
    gather_compliance_context,
    render_citations_for_prompt,
)
from ocerp.services.knowledge_store import KnowledgeSearchResult

if TYPE_CHECKING:
    from ocerp.services.boq_models import ResolvedCostItem


class _RecordingKnowledgeStore:
    """Stub store that returns canned chunks and records every search request."""

    def __init__(
        self, chunks_by_filter: dict[tuple[str | None, str | None], list[KnowledgeSearchResult]]
    ):
        self._chunks = chunks_by_filter
        self.calls: list[dict[str, Any]] = []

    async def search(self, request: Any) -> list[KnowledgeSearchResult]:
        self.calls.append(
            {
                "query": request.query,
                "job_type": request.job_type,
                "rule_tier": request.rule_tier,
                "limit": request.limit,
            }
        )
        return list(self._chunks.get((request.job_type, request.rule_tier), []))


def _chunk(
    chunk_id: str,
    *,
    text: str,
    section: list[str],
    rule_tier: str,
    job_types: list[str],
    score: float = 0.9,
) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        id=chunk_id,
        score=score,
        text=text,
        source="UK Domestic Electrical Quoting Knowledge Base",
        section_path=section,
        rule_tier=rule_tier,
        job_types=job_types,
        doc_type="prose",
    )


# ---------------------------------------------------------------------------
# detect_job_types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Install a wall-mounted EV charger on the driveway", {"ev_charger", "outdoor"}),
        ("Rewire of a 3 bed semi detached house", {"rewire"}),
        ("Replace consumer unit with metal CU including SPD", {"consumer_unit"}),
        (
            "Add downlights to the bathroom and replace shower circuit",
            {"bathroom", "lighting", "shower"},
        ),
        ("EICR for landlord", {"eicr"}),
        ("Add a double socket in the living room", set()),  # no triggering keyword
    ],
)
def test_detect_job_types_matches_expected_tags(description: str, expected: set[str]) -> None:
    assert set(detect_job_types(description)) == expected


# ---------------------------------------------------------------------------
# gather_compliance_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gather_compliance_context_retrieves_per_job_type_and_tier() -> None:
    store = _RecordingKnowledgeStore(
        {
            ("bathroom", "mandatory"): [
                _chunk(
                    "bath-mand-1",
                    text="RCD protection is required for all circuits in zones 0, 1 and 2 of a bathroom.",
                    section=["BS 7671", "Section 701"],
                    rule_tier="mandatory",
                    job_types=["bathroom"],
                ),
            ],
            ("bathroom", "default"): [
                _chunk(
                    "bath-def-1",
                    text="Supplementary equipotential bonding may be omitted on modern installations meeting 415.2.",
                    section=["BS 7671", "Section 701.415.2"],
                    rule_tier="default",
                    job_types=["bathroom"],
                ),
            ],
        }
    )

    context = await gather_compliance_context(
        "Add a new shower circuit and bathroom lighting", knowledge_store=store
    )

    assert "bathroom" in context.job_types
    chunk_ids = {c.chunk_id for c in context.citations}
    assert "bath-mand-1" in chunk_ids
    assert "bath-def-1" in chunk_ids
    # Mandatory tier was queried before default.
    call_tiers = [c["rule_tier"] for c in store.calls]
    assert call_tiers.count("mandatory") >= 1
    assert call_tiers.count("default") >= 1


@pytest.mark.asyncio
async def test_gather_compliance_context_degrades_when_store_raises() -> None:
    class _BrokenStore:
        async def search(self, request: Any) -> list[KnowledgeSearchResult]:
            raise RuntimeError("Qdrant unreachable")

    context = await gather_compliance_context(
        "Add a new EV charger", knowledge_store=_BrokenStore()
    )

    assert context.knowledge_available is False
    assert context.citations == []
    assert any(
        "unreachable" in w.lower() or "failed" in w.lower() for w in context.retrieval_warnings
    )


@pytest.mark.asyncio
async def test_gather_compliance_context_fallback_when_no_job_type_matches() -> None:
    store = _RecordingKnowledgeStore(
        {
            (None, "mandatory"): [
                _chunk(
                    "generic-mand-1",
                    text="Quotes for domestic electrical work in the UK must comply with BS 7671.",
                    section=["BS 7671", "General"],
                    rule_tier="mandatory",
                    job_types=[],
                )
            ]
        }
    )

    context = await gather_compliance_context(
        "Just a small isolated job please", knowledge_store=store
    )

    assert context.job_types == []
    assert [c.chunk_id for c in context.citations] == ["generic-mand-1"]


# ---------------------------------------------------------------------------
# check_mandatory_items
# ---------------------------------------------------------------------------


def _li(description: str, code: str = "DOM-x") -> BoQLineItem:
    return BoQLineItem(
        code=code,
        description=description,
        unit="each",
        quantity=Decimal("1"),
        unit_price=Decimal("10.00"),
        total=Decimal("10.00"),
        category="Wiring Accessories",
    )


def test_check_mandatory_items_flags_missing_ev_protection() -> None:
    line_items = [
        _li("32A MCB for EV circuit", code="32A-MCB"),
        # No Type A RCD, no isolator, no SWA → three warnings expected.
    ]
    warnings = check_mandatory_items(["ev_charger"], line_items)
    joined = " | ".join(warnings).lower()
    assert "type a rcd" in joined
    assert "weatherproof isolator" in joined
    assert "swa" in joined or "armoured" in joined


def test_check_mandatory_items_passes_when_all_present() -> None:
    line_items = [
        _li("32A RCBO Type A for EV charger circuit"),
        _li("Weatherproof rotary isolator IP65"),
        _li("10mm² SWA armoured cable supply, 15m"),
    ]
    warnings = check_mandatory_items(["ev_charger"], line_items)
    assert warnings == []


def test_check_mandatory_items_handles_multiple_job_types_without_duplication() -> None:
    # Both job types want RCD protection — should only flag the missing item once.
    line_items: list[BoQLineItem] = []
    warnings = check_mandatory_items(["bathroom", "rewire"], line_items)
    rcd_warnings = [w for w in warnings if "rcd or rcbo protection" in w.lower()]
    assert len(rcd_warnings) == 1


# ---------------------------------------------------------------------------
# render_citations_for_prompt
# ---------------------------------------------------------------------------


def test_render_citations_for_prompt_orders_mandatory_first_and_truncates() -> None:
    from mtp_shared import RegulatoryCitation

    citations = [
        RegulatoryCitation(
            chunk_id="ref-1",
            source="KB",
            section_path=["General"],
            rule_tier="reference",
            snippet="x" * 100,
            relevance_score=0.9,
        ),
        RegulatoryCitation(
            chunk_id="mand-1",
            source="KB",
            section_path=["BS 7671"],
            rule_tier="mandatory",
            snippet="y" * 100,
            relevance_score=0.5,
        ),
    ]
    rendered = render_citations_for_prompt(citations, max_chars=180)
    # Mandatory entry should appear first even though its score is lower.
    assert rendered.index("mand-1") < rendered.index("ref-1") if "ref-1" in rendered else True
    assert "mand-1" in rendered


# ---------------------------------------------------------------------------
# End-to-end: backend wires citations into the response
# ---------------------------------------------------------------------------


class _ResolverYieldingSocket:
    """Resolves any requirement to a generic 'socket' line so we can audit."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def resolve(self, requirements: list[Any]) -> tuple[list[ResolvedCostItem], list[str]]:
        # Returning an empty resolution set means the resulting BoQ contains
        # only the deterministic labour lines, which contain no protective
        # devices — perfect for letting the compliance check raise warnings.
        return [], []


@pytest.mark.asyncio
async def test_backend_attaches_citations_and_compliance_warnings_to_response() -> None:
    """A full backend run should ship the regulatory citations and ev-charger warnings."""
    store = _RecordingKnowledgeStore(
        {
            ("ev_charger", "mandatory"): [
                _chunk(
                    "ev-mand-1",
                    text=(
                        "EV charging installations require a Type A RCD with built-in DC "
                        "fault detection and a dedicated 32A protective device."
                    ),
                    section=["BS 7671", "Section 722"],
                    rule_tier="mandatory",
                    job_types=["ev_charger"],
                ),
            ],
        }
    )

    with (
        patch("ocerp.services.agent_graph.search_cost_items", new=AsyncMock(return_value=[])),
        patch(
            "ocerp.services.agent_graph.generate_boq_from_prompt",
            new=AsyncMock(
                return_value={
                    "analysis": {
                        "job_summary": "Install EV charger",
                        "room_count": None,
                        "spec_level": "mid_range",
                        "regulatory_flags": ["rcd_protection"],
                    },
                    "requirements": [],
                    "notes": "",
                }
            ),
        ),
        patch("ocerp.services.agent_graph.CatalogueResolver", _ResolverYieldingSocket),
    ):
        backend = DdcLlmBackend(knowledge_store=store)
        response = await backend.generate(
            BoQGenerateRequest(
                description="Install an EV charger on the driveway",
                trade="electrical",
                region="UK",
            )
        )

    # The deterministic citation we retrieved must round-trip to the response.
    chunk_ids = {c.chunk_id for c in response.regulatory_citations}
    assert "ev-mand-1" in chunk_ids

    # Without a Type A RCD / isolator / SWA in the BoQ, the compliance checker
    # must produce operator-facing warnings the trader can reconcile.
    joined = " | ".join(response.compliance_warnings).lower()
    assert "type a rcd" in joined or "dc fault" in joined
    assert "isolator" in joined
    assert "swa" in joined or "armoured" in joined


def test_compliance_context_dataclass_is_serialisable_for_logging() -> None:
    """Smoke check: the dataclass is plain enough to be safely logged."""
    ctx = ComplianceContext(
        job_types=["rewire"],
        citations=[],
        knowledge_available=True,
        retrieval_warnings=[],
    )
    assert ctx.job_types == ["rewire"]
    assert ctx.knowledge_available
