"""Unit tests for the requirement engine."""

from decimal import Decimal

from ocerp.services.requirements import generate_requirements


def test_full_rewire_includes_cu_and_protection() -> None:
    reqs = generate_requirements("Full rewire of a 3 bed semi detached house")
    concepts = {r.concept for r in reqs}

    assert "consumer_unit" in concepts
    cu_req = next(r for r in reqs if r.concept == "consumer_unit")
    assert cu_req.attributes.get("spd") is True
    assert "double_socket" in concepts
    assert "mcb" in concepts or "rcbo" in concepts
    assert "lighting_cable_1_5mm" in concepts
    assert "socket_cable_2_5mm" in concepts


def test_budget_rewire_uses_mcbs_not_rcbos() -> None:
    reqs = generate_requirements("Full rewire of a 3 bed house budget white plastic fittings")
    concepts = {r.concept for r in reqs}
    assert "mcb" in concepts
    assert "rcbo" not in concepts


def test_rcbo_request_keeps_rcbos() -> None:
    reqs = generate_requirements("Full rewire of a 3 bed house with rcbo consumer unit")
    concepts = {r.concept for r in reqs}
    assert "rcbo" in concepts


def test_ev_circuit_adds_dedicated_items() -> None:
    reqs = generate_requirements("Install 7kW EV charger in garage")
    concepts = {r.concept for r in reqs}
    assert "type_a_rcd" in concepts
    assert "swa_cable" in concepts
    assert "earth_rod" in concepts


def test_materials_only_has_no_labour_requirements() -> None:
    reqs = generate_requirements("Materials only for a full rewire of a 2 bed flat")
    assert not any(r.concept.startswith("labour") for r in reqs)


def test_ambiguous_description_adds_defaults() -> None:
    reqs = generate_requirements("Add sockets")
    socket_qty = sum(r.quantity for r in reqs if r.concept in {"double_socket", "single_socket"})
    assert socket_qty >= Decimal("10")
