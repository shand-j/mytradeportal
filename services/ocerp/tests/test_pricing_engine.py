"""Unit tests for the requirements-driven pricing engine."""

from decimal import Decimal

import pytest
from ocerp.services.boq_models import BoQRequirement, PricingConfig, ResolvedCostItem
from ocerp.services.pricing import (
    PriceFloorViolationError,
    build_totals,
    price_labour_item,
    price_material_item,
)


def _resolved(unit_price: str = "10.00", quantity: str = "1") -> ResolvedCostItem:
    return ResolvedCostItem(
        requirement=BoQRequirement(
            id="s1",
            concept="double_socket",
            category="Switches & Sockets",
            quantity=Decimal(quantity),
        ),
        cost_item={
            "code": "DOM-sf-123",
            "description": "Double socket",
            "unit": "each",
            "unit_price": unit_price,
            "category": "Switches & Sockets",
        },
        resolution_source="domestic_pipeline",
    )


def test_price_material_item_applies_markup() -> None:
    pricing = PricingConfig(markup_percent=Decimal("10"))
    resolved = ResolvedCostItem(
        requirement=BoQRequirement(
            id="s1",
            concept="double_socket",
            category="Switches & Sockets",
            quantity=Decimal("5"),
        ),
        cost_item={
            "code": "DOM-sf-123",
            "description": "Double socket",
            "unit": "each",
            "unit_price": "10.00",
            "category": "Switches & Sockets",
        },
        resolution_source="domestic_pipeline",
    )

    line = price_material_item(resolved, pricing)
    assert line.material_cost == Decimal("11.0000")
    assert line.unit_price == Decimal("11.0000")
    assert line.total == Decimal("55.0000")
    assert line.labour_total == Decimal("0")


def test_price_labour_item_uses_tenant_rate() -> None:
    pricing = PricingConfig(hourly_labour_rate=Decimal("50.00"))
    raw = {
        "code": "LABOUR-ELECTRICIAN-HOUR",
        "quantity": Decimal("4"),
        "labour_hours": Decimal("1"),
        "labour_rate": Decimal("50.00"),
        "notes": "test",
    }

    line = price_labour_item(raw, pricing)
    assert line.unit_price == Decimal("50.00")
    assert line.total == Decimal("200.0000")
    assert line.material_total == Decimal("0")


def test_build_totals_applies_vat_and_minimum_charge() -> None:
    pricing = PricingConfig(
        vat_rate=Decimal("0.20"),
        minimum_charge=Decimal("100.00"),
    )
    resolved = ResolvedCostItem(
        requirement=BoQRequirement(
            id="s1",
            concept="socket",
            category="Switches & Sockets",
            quantity=Decimal("1"),
        ),
        cost_item={
            "code": "DOM-sf-123",
            "description": "Socket",
            "unit": "each",
            "unit_price": "50.00",
            "category": "Switches & Sockets",
        },
        resolution_source="domestic_pipeline",
    )
    line_items = [price_material_item(resolved, pricing)]
    subtotal, vat_rate, vat_amount, total, warnings = build_totals(line_items, pricing)

    assert subtotal == Decimal("100.00")
    assert vat_rate == Decimal("0.20")
    assert vat_amount == Decimal("20.00")
    assert total == Decimal("120.00")
    assert any("minimum charge" in w.lower() for w in warnings)


def test_price_material_item_rejects_zero_catalogue_price() -> None:
    """A corrupted £0 cost item must never be priced and shipped."""
    pricing = PricingConfig(markup_percent=Decimal("20"))
    with pytest.raises(PriceFloorViolationError, match="non-positive"):
        price_material_item(_resolved(unit_price="0.00"), pricing)


def test_price_material_item_rejects_negative_markup() -> None:
    """A negative markup configuration must not let quotes ship below cost."""
    pricing = PricingConfig(markup_percent=Decimal("-10"))
    with pytest.raises(PriceFloorViolationError, match="below its catalogue cost"):
        price_material_item(_resolved(unit_price="10.00"), pricing)


def test_price_material_item_enforces_min_margin_when_configured() -> None:
    """When min_margin_percent is set, lines must clear the floor or be refused."""
    pricing = PricingConfig(
        markup_percent=Decimal("5"),  # 5% markup
        min_margin_percent=Decimal("15"),  # require at least 15% margin
    )
    with pytest.raises(PriceFloorViolationError, match="margin floor"):
        price_material_item(_resolved(unit_price="10.00"), pricing)


def test_price_material_item_allows_zero_markup_when_floor_disabled() -> None:
    """A tenant can opt into zero markup when no minimum margin is enforced."""
    pricing = PricingConfig(markup_percent=Decimal("0"))
    line = price_material_item(_resolved(unit_price="10.00", quantity="3"), pricing)
    assert line.unit_price == Decimal("10.0000")
    assert line.total == Decimal("30.0000")


def test_price_labour_item_rejects_zero_rate() -> None:
    """A misconfigured tenant with £0 labour rate must not generate free labour."""
    pricing = PricingConfig()
    raw = {
        "code": "LABOUR-ELECTRICIAN-HOUR",
        "quantity": Decimal("4"),
        "labour_hours": Decimal("1"),
        "labour_rate": Decimal("0"),
        "notes": "test",
    }
    with pytest.raises(PriceFloorViolationError, match="non-positive rate"):
        price_labour_item(raw, pricing)
