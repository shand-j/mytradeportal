"""Unit tests for the BoQ generation engine."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from mtp_shared import BoQGenerateRequest
from ocerp.services.boq_engine import DdcLlmBackend
from ocerp.services.boq_models import ResolvedCostItem


class _StubKnowledgeStore:
    """Pretends the knowledge collection exists and returns no chunks.

    Lets the BoQ engine exercise the compliance pipeline in unit tests
    without standing up Qdrant or talking to an embedding provider.
    """

    async def search(self, request):
        return []


def _backend() -> DdcLlmBackend:
    return DdcLlmBackend(knowledge_store=_StubKnowledgeStore())


class _FakeResolver:
    """Returns predictable catalogue matches for unit tests."""

    def __init__(self, *args, **kwargs):
        pass

    async def resolve(self, requirements):
        resolved = []
        for req in requirements:
            resolved.append(
                ResolvedCostItem(
                    requirement=req,
                    cost_item={
                        "code": f"DOM-{req.concept}",
                        "description": f"Test {req.concept}",
                        "unit": "each",
                        "unit_price": "10.00",
                        "category": req.category,
                        "supplier": "screwfix",
                        "brand": "Test Brand",
                        "sku": f"SKU-{req.concept}",
                    },
                    resolution_source="domestic_pipeline",
                    score=1.0,
                )
            )
        return resolved, []


@pytest.mark.asyncio
async def test_ddc_llm_backend_generates_boq() -> None:
    generated = {
        "analysis": {
            "job_summary": "Rewire domestic property",
            "room_count": 2,
            "spec_level": "mid_range",
            "regulatory_flags": ["metal_cu_required", "rcd_protection"],
        },
        "requirements": [
            {
                "concept": "double_socket",
                "category": "Switches & Sockets",
                "quantity": 3,
                "attributes": {"gang": 2},
                "notes": "three bedrooms",
            }
        ],
        "notes": "Standard socket additions",
    }

    with (
        patch("ocerp.services.agent_graph.search_cost_items", new=AsyncMock(return_value=[])),
        patch(
            "ocerp.services.agent_graph.generate_boq_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
        patch("ocerp.services.agent_graph.CatalogueResolver", _FakeResolver),
    ):
        backend = _backend()
        request = BoQGenerateRequest(
            description="Complete rewire of a 2 bedroom terraced house",
            trade="electrical",
            region="UK",
        )
        response = await backend.generate(request)

    # Deterministic mandatory items + labour should be present.
    categories = {li.category for li in response.line_items}
    assert "Consumer Units" in categories
    assert "Labour" in categories
    assert response.confidence >= Decimal("0.7")
    assert response.customer_summary_lines
    assert response.margin_indicator is not None
    assert response.margin_indicator.subtotal == response.subtotal


@pytest.mark.asyncio
async def test_ddc_llm_backend_warns_when_resolver_fails() -> None:
    generated = {
        "analysis": {
            "job_summary": "Socket addition",
            "room_count": None,
            "spec_level": "budget",
            "regulatory_flags": [],
        },
        "requirements": [],
        "notes": "No suitable items found",
    }

    class FailingResolver:
        def __init__(self, *args, **kwargs):
            pass

        async def resolve(self, requirements):
            return [], ["Could not resolve requirement 'x' to any catalogue item."]

    with (
        patch("ocerp.services.agent_graph.search_cost_items", new=AsyncMock(return_value=[])),
        patch(
            "ocerp.services.agent_graph.generate_boq_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
        patch("ocerp.services.agent_graph.CatalogueResolver", FailingResolver),
    ):
        backend = _backend()
        request = BoQGenerateRequest(description="Add a socket", trade="electrical", region="UK")
        response = await backend.generate(request)

    assert response.confidence == Decimal("0.0")
    assert any("Could not resolve" in warning for warning in response.warnings)
    assert response.customer_summary_lines


@pytest.mark.asyncio
async def test_ddc_llm_backend_handles_empty_llm_output() -> None:
    generated = {}

    with (
        patch("ocerp.services.agent_graph.search_cost_items", new=AsyncMock(return_value=[])),
        patch(
            "ocerp.services.agent_graph.generate_boq_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
        patch("ocerp.services.agent_graph.CatalogueResolver", _FakeResolver),
    ):
        backend = _backend()
        # A clear rewire description should still produce a meaningful BoQ from
        # the deterministic requirement engine even when the LLM returns nothing.
        request = BoQGenerateRequest(
            description="Full rewire of a 3 bed semi detached house",
            trade="electrical",
            region="UK",
        )
        response = await backend.generate(request)

    assert response.line_items
    assert not response.clarification_questions
    assert any("design contract validation failed" in w.lower() for w in response.warnings)
    assert response.customer_summary_lines


@pytest.mark.asyncio
async def test_ddc_llm_backend_adds_quality_gate_warnings_for_missing_sundries() -> None:
    with (
        patch("ocerp.services.agent_graph.search_cost_items", new=AsyncMock(return_value=[])),
        patch(
            "ocerp.services.agent_graph.generate_boq_from_prompt",
            new=AsyncMock(
                return_value={
                    "analysis": {
                        "job_summary": "Full rewire",
                        "room_count": 3,
                        "spec_level": "budget",
                        "regulatory_flags": ["smoke_alarms_required"],
                    },
                    "requirements": [],
                    "notes": "",
                }
            ),
        ),
        patch("ocerp.services.agent_graph.CatalogueResolver", _FakeResolver),
    ):
        backend = _backend()
        request = BoQGenerateRequest(
            description="Full rewire of a 3 bed semi detached house",
            trade="electrical",
            region="UK",
        )
        response = await backend.generate(request)

    assert any("quality gate" in warning.lower() for warning in response.warnings)
