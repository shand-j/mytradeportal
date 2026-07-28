"""Tests for the OpenConstructionERP HTTP client."""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from app.clients.ocerp import OCERPClient, build_quote_from_ocerp_response
from app.models import Quote
from mtp_shared import (
    BoQGenerateRequest,
    BoQGenerateResponse,
    BoQLineItem,
    PriceLookupRequest,
    PriceLookupResponse,
    RetrievalEvidence,
    StandardInfo,
    StandardsListResponse,
)


@pytest.mark.asyncio
async def test_generate_boq() -> None:
    expected = BoQGenerateResponse(
        line_items=[
            BoQLineItem(
                code="ELEC-SOCKET-ADD",
                description="Install one additional double socket",
                unit="each",
                quantity=Decimal("2"),
                unit_price=Decimal("85.00"),
                total=Decimal("170.00"),
            )
        ],
        subtotal=Decimal("170.00"),
        total=Decimal("204.00"),
        confidence=Decimal("1.0"),
    )
    mock_response = AsyncMock()
    mock_response.json = Mock(return_value=expected.model_dump(mode="json"))
    mock_response.raise_for_status = Mock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        async with OCERPClient(base_url="http://ocerp-test") as client:
            result = await client.generate_boq(BoQGenerateRequest(description="Add two sockets"))

    assert result.line_items[0].code == "ELEC-SOCKET-ADD"
    assert result.total == Decimal("204.00")


@pytest.mark.asyncio
async def test_lookup_price() -> None:
    expected = PriceLookupResponse(
        code="ELEC-SOCKET-ADD",
        description="Install one additional double socket",
        unit="each",
        unit_price=Decimal("85.00"),
        region="UK",
        found=True,
    )
    mock_response = AsyncMock()
    mock_response.json = Mock(return_value=expected.model_dump(mode="json"))
    mock_response.raise_for_status = Mock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        async with OCERPClient(base_url="http://ocerp-test") as client:
            result = await client.lookup_price(
                PriceLookupRequest(code="ELEC-SOCKET-ADD", region="UK")
            )

    assert result.found is True
    assert result.unit_price == Decimal("85.00")


@pytest.mark.asyncio
async def test_list_standards() -> None:
    expected = StandardsListResponse(
        standards=[StandardInfo(code="nrm1", name="NRM 1", region="UK")]
    )
    mock_response = AsyncMock()
    mock_response.json = Mock(return_value=expected.model_dump(mode="json"))
    mock_response.raise_for_status = Mock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        async with OCERPClient(base_url="http://ocerp-test") as client:
            result = await client.list_standards(region="UK")

    assert len(result.standards) == 1
    assert result.standards[0].code == "nrm1"


def test_build_quote_from_ocerp_response() -> None:
    quote = Quote(
        tenant_id="00000000-0000-0000-0000-000000000001",
        contact_id="00000000-0000-0000-0000-000000000002",
    )
    response = BoQGenerateResponse(
        line_items=[
            BoQLineItem(
                code="ELEC-SOCKET-ADD",
                description="Socket",
                unit="each",
                quantity=Decimal("2"),
                labour_hours=Decimal("0.50"),
                labour_rate=Decimal("45.00"),
                labour_total=Decimal("45.00"),
                material_cost=Decimal("40.00"),
                material_total=Decimal("80.00"),
                plant_cost=Decimal("0.00"),
                plant_total=Decimal("0.00"),
                unit_price=Decimal("85.00"),
                total=Decimal("170.00"),
            )
        ],
        subtotal=Decimal("170.00"),
        vat_amount=Decimal("34.00"),
        total=Decimal("204.00"),
        confidence=Decimal("1.0"),
        notes="Test",
        standard="nrm1",
        retrieval_evidence=RetrievalEvidence(
            knowledge_available=True,
            job_types=["consumer_unit"],
            citations_used=2,
            source_documents=["UK Domestic Electrical Quoting Knowledge Base"],
            top_relevance_score=0.87,
            quality_score=1.0,
            quality_gate_passed=True,
        ),
    )

    build_quote_from_ocerp_response(quote, response)

    assert quote.bill_of_quantities is not None
    assert len(quote.bill_of_quantities.line_items) == 1
    assert quote.bill_of_quantities.line_items[0].labour_hours == Decimal("0.50")
    assert quote.bill_of_quantities.total == Decimal("204.00")
    assert quote.bill_of_quantities.confidence == Decimal("1.0")
    assert quote.bill_of_quantities.standard == "nrm1"
    assert quote.bill_of_quantities.retrieval_evidence.get("citations_used") == 2

    assert len(quote.line_items) == 1
    assert quote.line_items[0].total == Decimal("170.00")
    assert quote.subtotal == Decimal("170.00")
    assert quote.total == Decimal("204.00")


def test_build_quote_from_ocerp_response_preserves_retrieval_quality_gate_fields() -> None:
    quote = Quote(
        tenant_id="00000000-0000-0000-0000-000000000001",
        contact_id="00000000-0000-0000-0000-000000000002",
    )
    response = BoQGenerateResponse(
        line_items=[],
        subtotal=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        total=Decimal("0.00"),
        confidence=Decimal("0.7"),
        retrieval_evidence=RetrievalEvidence(
            knowledge_available=True,
            job_types=["rewire"],
            citations_used=1,
            source_documents=["UK Domestic Electrical Quoting Knowledge Base"],
            top_relevance_score=0.91,
            quality_score=0.5,
            quality_gate_passed=False,
            quality_gate_reasons=["insufficient citations"],
            fallback_policy_applied="warn_only",
            confidence_capped=False,
        ),
    )

    build_quote_from_ocerp_response(quote, response)

    assert quote.bill_of_quantities is not None
    assert quote.bill_of_quantities.retrieval_evidence.get("quality_gate_passed") is False
    assert quote.bill_of_quantities.retrieval_evidence.get("quality_gate_reasons") == [
        "insufficient citations"
    ]
    assert quote.bill_of_quantities.retrieval_evidence.get("fallback_policy_applied") == "warn_only"
