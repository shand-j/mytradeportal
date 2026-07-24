"""Unit tests for the catalogue resolver."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from ocerp.services.boq_models import BoQRequirement
from ocerp.services.resolver import CatalogueResolver


@pytest.mark.asyncio
async def test_resolver_prefers_domestic_pipeline() -> None:
    domestic = [
        {
            "code": "DOM-sf-123",
            "description": "British General 13A 2-Gang DP Switched Socket",
            "unit": "each",
            "unit_price": "4.16",
            "category": "Switches & Sockets",
            "supplier": "screwfix",
            "brand": "British General",
            "score": 0.85,
        }
    ]

    with patch(
        "ocerp.services.resolver.search_cost_items",
        new=AsyncMock(return_value=domestic),
    ):
        resolver = CatalogueResolver()
        req = BoQRequirement(
            id="sock",
            concept="double_socket",
            category="Switches & Sockets",
            attributes={"gang": 2, "usb": False},
            quantity=Decimal("1"),
        )
        result = await resolver.resolve_one(req)

    assert result is not None
    assert result.resolution_source == "domestic_pipeline"
    assert result.cost_item["code"] == "DOM-sf-123"


@pytest.mark.asyncio
async def test_resolver_returns_none_when_no_domestic_match() -> None:
    with patch(
        "ocerp.services.resolver.search_cost_items",
        new=AsyncMock(return_value=[]),
    ):
        resolver = CatalogueResolver()
        req = BoQRequirement(
            id="spd",
            concept="spd_module",
            category="Consumer Units",
            attributes={"spd": True},
            quantity=Decimal("1"),
        )
        result = await resolver.resolve_one(req)

    assert result is None


@pytest.mark.asyncio
async def test_resolver_skips_low_score_candidates() -> None:
    domestic = [
        {
            "code": "DOM-sf-999",
            "description": "Something unrelated",
            "unit": "each",
            "unit_price": "1.00",
            "category": "Switches & Sockets",
            "score": 0.01,
        }
    ]

    with patch(
        "ocerp.services.resolver.search_cost_items",
        new=AsyncMock(side_effect=[domestic, []]),
    ):
        resolver = CatalogueResolver(min_score=0.15)
        req = BoQRequirement(
            id="sock",
            concept="double_socket",
            category="Switches & Sockets",
            attributes={"gang": 2},
            quantity=Decimal("1"),
        )
        result = await resolver.resolve_one(req)

    assert result is None


@pytest.mark.asyncio
async def test_resolver_caches_results() -> None:
    domestic = [
        {
            "code": "DOM-sf-123",
            "description": "Socket",
            "unit": "each",
            "unit_price": "4.00",
            "category": "Switches & Sockets",
            "score": 0.9,
        }
    ]

    with patch(
        "ocerp.services.resolver.search_cost_items",
        new=AsyncMock(return_value=domestic),
    ) as mock_search:
        resolver = CatalogueResolver()
        req = BoQRequirement(
            id="sock",
            concept="socket",
            category="Switches & Sockets",
            quantity=Decimal("1"),
        )
        await resolver.resolve_one(req)
        await resolver.resolve_one(req)

    assert mock_search.call_count == 1


@pytest.mark.asyncio
async def test_resolver_selects_smallest_cable_pack_covering_length() -> None:
    """45m of 2.5mm cable should resolve to a 50m drum, not 25m or 100m."""
    domestic = [
        {
            "code": "CABLE-25M",
            "description": "Prysmian 6242Y Twin & Earth Cable 2.5mm² 25m Coil",
            "unit": "m",
            "unit_price": "1.10",
            "category": "Cable",
            "supplier": "screwfix",
            "score": 0.85,
        },
        {
            "code": "CABLE-50M",
            "description": "Prysmian 6242Y Twin & Earth Cable 2.5mm² x 50m Drum",
            "unit": "m",
            "unit_price": "0.72",
            "category": "Cable",
            "supplier": "screwfix",
            "score": 0.84,
        },
        {
            "code": "CABLE-100M",
            "description": "Time 6242Y Twin & Earth Cable 2.5mm² 100m Drum",
            "unit": "m",
            "unit_price": "0.72",
            "category": "Cable",
            "supplier": "screwfix",
            "score": 0.83,
        },
    ]

    with patch(
        "ocerp.services.resolver.search_cost_items",
        new=AsyncMock(return_value=domestic),
    ):
        resolver = CatalogueResolver()
        req = BoQRequirement(
            id="cable-2.5",
            concept="socket_cable_2_5mm",
            category="Cable",
            attributes={"mm": "2.5", "twin": True},
            quantity=Decimal("45"),
        )
        result = await resolver.resolve_one(req)

    assert result is not None
    assert result.cost_item["code"] == "CABLE-50M"
    assert result.requirement.quantity == Decimal("50")
    assert "Pack size 50m" in (result.requirement.notes or "")


@pytest.mark.asyncio
async def test_resolver_falls_back_to_per_metre_cable_when_no_pack_covers() -> None:
    domestic = [
        {
            "code": "CABLE-10M",
            "description": "Prysmian 6242Y Twin & Earth Cable 2.5mm² 10m Coil",
            "unit": "m",
            "unit_price": "1.50",
            "category": "Cable",
            "supplier": "screwfix",
            "score": 0.85,
        },
        {
            "code": "CABLE-M",
            "description": "Prysmian 6242Y Twin & Earth Cable 2.5mm² Per Metre",
            "unit": "m",
            "unit_price": "0.90",
            "category": "Cable",
            "supplier": "screwfix",
            "score": 0.80,
        },
    ]

    with patch(
        "ocerp.services.resolver.search_cost_items",
        new=AsyncMock(return_value=domestic),
    ):
        resolver = CatalogueResolver()
        req = BoQRequirement(
            id="cable-2.5",
            concept="socket_cable_2_5mm",
            category="Cable",
            attributes={"mm": "2.5", "twin": True},
            quantity=Decimal("45"),
        )
        result = await resolver.resolve_one(req)

    assert result is not None
    assert result.cost_item["code"] == "CABLE-M"
    assert result.requirement.quantity == Decimal("45")
