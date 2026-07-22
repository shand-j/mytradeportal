"""Unit tests for the labour estimator."""

from decimal import Decimal

from ocerp.services.boq_models import BoQRequirement, PricingConfig, load_labour_schedule
from ocerp.services.labour import estimate_labour


def test_estimate_labour_for_rewire_uses_schedule() -> None:
    pricing = PricingConfig(daily_labour_rate=Decimal("360.00"))
    schedule = load_labour_schedule()
    lines = estimate_labour(
        description="Full rewire of a 3 bed house",
        property_type="3_bed_house",
        pricing_config=pricing,
        labour_schedule=schedule,
        requirements=[
            BoQRequirement(
                id="r1",
                concept="double_socket",
                category="Switches & Sockets",
                quantity=Decimal("16"),
            ),
            BoQRequirement(
                id="r2",
                concept="ceiling_light",
                category="Lighting",
                quantity=Decimal("8"),
            ),
            BoQRequirement(
                id="r3",
                concept="socket_cable_2_5mm",
                category="Cable",
                quantity=Decimal("180"),
            ),
            BoQRequirement(
                id="r4",
                concept="mcb",
                category="Circuit Protection",
                quantity=Decimal("10"),
            ),
        ],
    )

    codes = {line["code"] for line in lines}
    assert "LABOUR-ELECTRICIAN-DAY" in codes or "LABOUR-ELECTRICIAN-HOUR" in codes
    assert "LABOUR-TESTING-HOUR" in codes
    assert "LABOUR-CERTIFICATION-HOUR" in codes


def test_estimate_labour_no_labour_returns_empty() -> None:
    pricing = PricingConfig()
    schedule = load_labour_schedule()
    lines = estimate_labour(
        description="Materials only list for rewire",
        property_type=None,
        pricing_config=pricing,
        labour_schedule=schedule,
    )
    assert lines == []


def test_estimate_labour_small_job_defaults_to_half_day() -> None:
    pricing = PricingConfig(hourly_labour_rate=Decimal("45.00"))
    schedule = load_labour_schedule()
    lines = estimate_labour(
        description="Add one double socket in the kitchen",
        property_type=None,
        pricing_config=pricing,
        labour_schedule=schedule,
        has_material_items=True,
        requirements=[
            BoQRequirement(
                id="s1",
                concept="double_socket",
                category="Switches & Sockets",
                quantity=Decimal("1"),
            )
        ],
    )

    assert any(line["code"] == "LABOUR-ELECTRICIAN-HOUR" for line in lines)
    hour_line = next(line for line in lines if line["code"] == "LABOUR-ELECTRICIAN-HOUR")
    assert hour_line["quantity"] >= schedule.small_job_default.electrician_hours


def test_estimate_labour_adds_access_allowance_when_scope_mentions_loft() -> None:
    pricing = PricingConfig(hourly_labour_rate=Decimal("45.00"))
    schedule = load_labour_schedule()
    lines = estimate_labour(
        description="Run cable through loft and lift floorboards for socket additions",
        property_type=None,
        pricing_config=pricing,
        labour_schedule=schedule,
        has_material_items=True,
        requirements=[
            BoQRequirement(
                id="c1",
                concept="socket_cable_2_5mm",
                category="Cable",
                quantity=Decimal("60"),
            )
        ],
    )

    access_line = next(line for line in lines if line["code"] == "LABOUR-ACCESS-HOUR")
    assert access_line["quantity"] > 0
