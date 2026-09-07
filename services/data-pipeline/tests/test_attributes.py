"""Tests for the per-category attribute extractor."""

from data_pipeline.normalizer.attributes import (
    extract_product_attributes,
    extract_query_intent,
    format_attributes_tail,
)
from data_pipeline.normalizer.unified_product import ProductCategory, Supplier, UnifiedProduct


def _p(category: ProductCategory, name: str, description: str = "") -> UnifiedProduct:
    return UnifiedProduct(
        supplier=Supplier.SCREWFIX,
        sku="X",
        name=name,
        description=description,
        category=category,
        current_price=1.0,
    )


def test_alarm_fire_vs_intruder_split() -> None:
    """The smoke-alarm eval regression was rooted in this split."""
    fire = extract_product_attributes(
        _p(ProductCategory.SECURITY_FIRE, "Aico Ei3016 Mains Interlinked Optical Smoke Alarm 240V")
    )
    assert fire["alarm_purpose"] == "fire"
    assert fire["alarm_type"] == "smoke"
    assert fire["alarm_interconnect"] == "interlinked"
    assert fire["alarm_power"] == "mains"

    intruder = extract_product_attributes(
        _p(ProductCategory.SECURITY_FIRE, "Yale HSA Essentials Burglar Alarm Kit")
    )
    assert intruder["alarm_purpose"] == "intruder"
    assert "alarm_type" not in intruder


def test_alarm_heat_and_co_variants() -> None:
    heat = extract_product_attributes(
        _p(ProductCategory.SECURITY_FIRE, "Aico Ei3024 Mains Interlinked Heat Alarm")
    )
    assert heat["alarm_type"] == "heat"

    co = extract_product_attributes(
        _p(ProductCategory.SECURITY_FIRE, "FireAngel CO Alarm Carbon Monoxide Detector")
    )
    assert co["alarm_type"] == "co"


def test_cable_swa_vs_extension_reel_split() -> None:
    """The garden-office eval regression was rooted in this split."""
    swa = extract_product_attributes(
        _p(ProductCategory.CABLE, "Prysmian SWA 3-Core 4mm² Armoured Cable 25m")
    )
    assert swa["cable_type"] == "swa"
    assert swa["cable_csa_mm2"] == 4.0
    assert swa["cable_cores"] == 3

    reel = extract_product_attributes(
        _p(ProductCategory.CABLE, "Masterplug Work Power 13A 4-Gang 30m Extension Cable Reel 240V")
    )
    assert reel["cable_type"] == "extension_reel"


def test_cable_twin_earth_and_csa() -> None:
    te = extract_product_attributes(
        _p(ProductCategory.CABLE, "Prysmian 6242Y Grey 2.5mm² Twin & Earth Cable 100m Drum")
    )
    assert te["cable_type"] == "twin_earth"
    assert te["cable_csa_mm2"] == 2.5


def test_consumer_unit_ways_and_type() -> None:
    cu = extract_product_attributes(
        _p(ProductCategory.CONSUMER_UNITS, "British General 10-Way Dual RCD Consumer Unit IP20")
    )
    assert cu["cu_ways"] == 10
    assert cu["cu_type"] == "dual_rcd"
    assert cu["ip_rating"] == "IP20"


def test_protection_rcbo_rating_and_curve() -> None:
    rcbo = extract_product_attributes(
        _p(ProductCategory.MCB_RCD_RCBO, "British General 32A Type B RCBO 30mA SP")
    )
    assert rcbo["protection_type"] == "rcbo"
    assert rcbo["rating_A"] == 32
    assert rcbo["curve"] == "B"
    assert rcbo["poles"] == 1


def test_lighting_downlight_with_wattage_ip_dimmable() -> None:
    dl = extract_product_attributes(
        _p(
            ProductCategory.LIGHTING,
            "LAP Cosmoseco Fixed Fire Rated LED Downlight Chrome 4W Dimmable IP65 3000K",
        )
    )
    assert dl["light_type"] == "downlight"
    assert dl["wattage_W"] == 4.0
    assert dl["ip_rating"] == "IP65"
    assert dl["dimmable"] is True
    assert dl["colour_temp_K"] == 3000


def test_accessory_socket_gangs_and_weatherproof() -> None:
    outdoor = extract_product_attributes(
        _p(
            ProductCategory.SWITCHES_SOCKETS,
            "British General IP66 13A 2-Gang SP Weatherproof Outdoor Switched Socket",
        )
    )
    assert outdoor["accessory_type"] == "socket"
    assert outdoor["gangs"] == 2
    assert outdoor["weatherproof"] is True


def test_extractor_returns_empty_for_unmatched_category() -> None:
    assert extract_product_attributes(_p(ProductCategory.GENERAL, "Random product")) == {}


def test_format_attributes_tail_sorts_and_flattens() -> None:
    tail = format_attributes_tail(
        {"alarm_purpose": "fire", "alarm_type": "smoke", "dimmable": True, "verbose": False}
    )
    # Sorted keys, booleans as bare keys when true, false booleans omitted.
    assert tail == " alarm_purpose=fire alarm_type=smoke dimmable"


def test_query_intent_alarm_purpose_from_customer_text() -> None:
    fire = extract_query_intent(
        "Fit interlinked mains smoke alarms - hallway, landing and kitchen heat alarm."
    )
    assert fire == {"alarm_purpose": "fire"}

    intruder = extract_query_intent(
        "I want a burglar alarm and a couple of CCTV cameras around the front door."
    )
    assert intruder == {"alarm_purpose": "intruder"}


def test_query_intent_cable_type() -> None:
    swa = extract_query_intent(
        "Need power run to a new garden office - armoured cable buried, small consumer unit."
    )
    assert swa == {"cable_type": "swa"}


def test_query_intent_lighting_type() -> None:
    downlights = extract_query_intent("Swap fluorescent for 6 LED downlights, dimmable.")
    assert downlights == {"light_type": "downlight"}

    floodlight = extract_query_intent(
        "Want 4 outside wall lights and a PIR security light by the garage."
    )
    # security light wins over wall light because the first match dominates
    assert floodlight == {"light_type": "floodlight"}


def test_query_intent_returns_empty_for_ambiguous_job() -> None:
    assert extract_query_intent("Landlord needs an EICR before new tenants move in.") == {}
