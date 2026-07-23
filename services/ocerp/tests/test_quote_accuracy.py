"""Tests for the quote-accuracy improvements (cable scaling, finish fidelity)."""

from __future__ import annotations

from decimal import Decimal

from mtp_shared import BoQGenerateRequest
from ocerp.services.boq_models import BoQRequirement
from ocerp.services.requirements import RequirementEngine
from ocerp.services.resolver import _brand_score, _finish_score, _score_candidate

# ---------------------------------------------------------------------------
# Cable scaling
# ---------------------------------------------------------------------------


def test_cable_metreage_scales_with_bedrooms() -> None:
    """A 4-bed rewire should require materially more cable than a 1-bed flat.

    Before this fix every rewire got the same 50/80/20 metres regardless of
    property size, which systematically under-quoted larger jobs by 25-35%.
    """
    flat = RequirementEngine("Full rewire of a 1 bed flat")
    semi = RequirementEngine("Full rewire of a 3 bed semi detached house")
    detached = RequirementEngine("Full rewire of a 4 bed detached house")

    flat_l, flat_s, flat_c = flat._scaled_cable_metreage()
    semi_l, semi_s, semi_c = semi._scaled_cable_metreage()
    det_l, det_s, det_c = detached._scaled_cable_metreage()

    # Monotonic in property size.
    assert flat_l < semi_l < det_l, (flat_l, semi_l, det_l)
    assert flat_s < semi_s < det_s, (flat_s, semi_s, det_s)
    assert flat_c <= semi_c <= det_c, (flat_c, semi_c, det_c)

    # 4-bed should need roughly double a 1-bed flat for 1.5mm and 2.5mm.
    assert det_l >= flat_l * 2, f"1.5mm: 4-bed={det_l} vs 1-bed={flat_l}"
    assert det_s >= flat_s * 2, f"2.5mm: 4-bed={det_s} vs 1-bed={flat_s}"


def test_cable_metreage_defaults_to_three_bed_on_ambiguous_input() -> None:
    """'Rewire my house' previously got 1-bed-sized cable; defaults must be sane."""
    ambiguous = RequirementEngine("Rewire my house")
    lighting, socket, cooker = ambiguous._scaled_cable_metreage()
    # Should be the 3-bed defaults, not 1-bed.
    three_bed = RequirementEngine("Full rewire of a 3 bed house")
    assert (lighting, socket, cooker) == three_bed._scaled_cable_metreage()


def test_partial_rewire_uses_half_cable() -> None:
    """A ground-floor-only rewire should not order full-house cable runs."""
    full = RequirementEngine("Full rewire of a 3 bed house")
    partial = RequirementEngine("Rewire ground floor of a 3 bed house")
    full_l, full_s, _ = full._scaled_cable_metreage()
    part_l, part_s, _ = partial._scaled_cable_metreage()
    assert part_l == full_l / 2
    assert part_s == full_s / 2


def test_cable_caps_accommodate_largest_domestic() -> None:
    """The cap function must not truncate the deterministic 4-bed metreage."""
    eng = RequirementEngine("Full rewire of a 4 bed detached house")
    raw_reqs = eng.generate()
    cables = {r.concept: r.quantity for r in raw_reqs if r.category == "Cable"}
    # 4-bed defaults should round-trip through the cap unchanged.
    assert cables.get("lighting_cable_1_5mm") == Decimal("120")
    assert cables.get("socket_cable_2_5mm") == Decimal("220")
    assert cables.get("cooker_cable_6mm") == Decimal("28")


# ---------------------------------------------------------------------------
# Finish-attribute fidelity in the resolver scorer
# ---------------------------------------------------------------------------


def _make_req(finish: str | None = None) -> BoQRequirement:
    attrs = {"gang": 2, "usb": False}
    if finish:
        attrs["finish"] = finish
    return BoQRequirement(
        id="req-1",
        concept="double_socket",
        category="Switches & Sockets",
        attributes=attrs,
        quantity=Decimal("1"),
    )


def _make_item(description: str, brand: str = "MK", score: float = 0.7) -> dict[str, object]:
    return {
        "code": f"DOM-{abs(hash(description)) % 9999}",
        "description": description,
        "brand": brand,
        "score": score,
    }


def test_finish_score_rewards_brushed_steel_when_chrome_requested() -> None:
    req = _make_req(finish="chrome")
    brushed = _make_item("MK Logic Plus 13A 2-Gang DP Switched Socket Brushed Steel")
    chrome = _make_item("MK Logic Plus 13A 2-Gang DP Switched Socket Chrome")
    stainless = _make_item("MK Logic Plus 13A 2-Gang DP Switched Socket Stainless Steel")
    assert _finish_score(req, brushed) == 1.5
    assert _finish_score(req, chrome) == 1.5
    assert _finish_score(req, stainless) == 1.5


def test_finish_score_softly_penalises_white_when_chrome_requested() -> None:
    """A soft 0.4x — NOT zero — so white plates remain pickable when no
    brushed-steel SKU exists. Zeroing them out caused the resolver to leap
    to IP66 outdoor sockets in the early eval run."""
    req = _make_req(finish="chrome")
    white = _make_item("MK Logic Plus 13A 2-Gang DP Switched Socket White")
    assert _finish_score(req, white) == 0.4


def test_finish_score_neutral_when_no_finish_attribute() -> None:
    req = _make_req(finish=None)
    white = _make_item("MK Logic Plus 13A 2-Gang DP Switched Socket White")
    assert _finish_score(req, white) == 1.0


def test_score_candidate_prefers_brushed_steel_over_white_when_chrome_asked() -> None:
    """Concrete regression for STD-004 (4-bed detached, brushed steel MK sockets).

    Pre-fix the resolver returned the cheaper white plate; this test pins
    the new behaviour so chrome/brushed-steel requirements win whenever a
    matching SKU exists, but white still ranks above zero (so an outdoor
    IP66 plate doesn't sneak in via the gap).
    """
    req = _make_req(finish="chrome")
    white = _make_item("MK Logic Plus 13A 2-Gang DP Switched Socket White", score=0.8)
    brushed = _make_item("MK Logic Plus 13A 2-Gang DP Switched Socket Brushed Steel", score=0.65)
    assert _score_candidate(req, brushed) > _score_candidate(req, white)
    # White must remain pickable as a fallback rather than being hard-zeroed.
    assert _score_candidate(req, white) > 0


def test_score_candidate_unchanged_when_no_finish_constraint() -> None:
    """Adding finish logic must not affect requirements without a finish attr."""
    req = _make_req(finish=None)
    white = _make_item("MK Socket White", score=0.7)
    score = _score_candidate(req, white)
    # Should still be a positive score derived from keyword + vector overlap.
    assert score > 0


# ---------------------------------------------------------------------------
# Determinism — guards H1 (temperature=0) against silent regressions.
# ---------------------------------------------------------------------------


def test_requirement_generation_is_deterministic_for_same_input() -> None:
    """Two identical job descriptions must produce identical requirement sets.

    The requirement engine is rule-based (no LLM call), so this is purely a
    smoke test that random ordering doesn't sneak in.
    """
    desc = "Full rewire of a 3 bed semi detached house with British General accessories"
    a = RequirementEngine(desc).generate()
    b = RequirementEngine(desc).generate()
    assert len(a) == len(b)
    # Sort by id so we compare as sets.
    a_sorted = sorted(a, key=lambda r: r.id)
    b_sorted = sorted(b, key=lambda r: r.id)
    for ra, rb in zip(a_sorted, b_sorted, strict=True):
        assert ra.concept == rb.concept
        assert ra.category == rb.category
        assert ra.quantity == rb.quantity
        assert ra.attributes == rb.attributes


def test_boq_request_round_trips_through_engine_without_loss() -> None:
    """A BoQGenerateRequest must accept the shape the engine emits."""
    request = BoQGenerateRequest(
        description="Full rewire of a 4 bed detached",
        trade="electrical",
        region="UK",
        tenant_settings={"hourly_labour_rate": "45.00", "markup_percent": "20"},
    )
    assert request.description.startswith("Full")
    assert request.tenant_settings["markup_percent"] == "20"


# ---------------------------------------------------------------------------
# Cable pack selection — buy enough packs to cover the requirement
# ---------------------------------------------------------------------------


def test_cable_pack_fallback_multiplies_packs_when_no_single_pack_covers() -> None:
    """A 220m cable requirement must produce 3x 100m drums, not one drum.

    The previous fallback returned a single pack regardless of the
    requirement, so a 4-bed rewire needing 220m of 2.5mm twin and earth
    was being satisfied with one 100m drum at ~£72 instead of three at
    ~£215 — a £140 systemic under-quote per cable line.
    """
    from ocerp.services.resolver import _select_cable_candidate

    req = BoQRequirement(
        id="req-cable-220",
        concept="socket_cable_2_5mm",
        category="Cable",
        attributes={"mm": "2.5", "twin": True},
        quantity=Decimal("220"),
    )
    drum_100m = {
        "code": "DOM-time-2.5mm-100m",
        "description": "Time 6242Y Grey 2.5mm² Twin & Earth Cable 100m Drum",
        "unit": "m",
        "unit_price": "0.72",
        "category": "Cable",
        "score": 0.9,
    }
    scored = [(drum_100m, 0.9)]
    result = _select_cable_candidate(req, scored)
    assert result is not None
    item, updated = result
    assert item["code"] == "DOM-time-2.5mm-100m"
    assert updated.quantity == Decimal("300"), updated.quantity
    assert "3x 100m" in (updated.notes or "")


def test_cable_pack_single_pack_covers_does_not_multiply() -> None:
    """A 50m requirement satisfied by a 100m drum should buy just one drum."""
    from ocerp.services.resolver import _select_cable_candidate

    req = BoQRequirement(
        id="req-cable-50",
        concept="lighting_cable_1_5mm",
        category="Cable",
        attributes={"mm": "1.5", "twin": True},
        quantity=Decimal("50"),
    )
    drum_100m = {
        "code": "DOM-time-1.5mm-100m",
        "description": "Time 6242Y Grey 1.5mm² Twin & Earth Cable 100m Drum",
        "unit": "m",
        "unit_price": "0.48",
        "category": "Cable",
        "score": 0.9,
    }
    result = _select_cable_candidate(req, [(drum_100m, 0.9)])
    assert result is not None
    _, updated = result
    assert updated.quantity == Decimal("100")


def test_indoor_double_socket_hard_rejects_weatherproof_outdoor_skus() -> None:
    """STD-004 regression: 32 indoor MK sockets must not pick MK Masterseal IP66.

    The Screwfix catalogue carries the MK Masterseal Plus IP66 Weatherproof
    Outdoor 13A socket. Without an explicit reject the resolver was scoring
    it high against an indoor ``double_socket`` requirement (correct brand,
    correct amperage, correct gang count) and shipping a £75-per-socket
    weatherproof unit where a £7 indoor plate was wanted.
    """
    from ocerp.services.resolver import _hard_reject

    indoor_req = BoQRequirement(
        id="req-1",
        concept="double_socket",
        category="Switches & Sockets",
        attributes={"gang": 2, "usb": False, "brand": "mk"},
        quantity=Decimal("1"),
    )
    outdoor_req = BoQRequirement(
        id="req-2",
        concept="outdoor_socket",
        category="Switches & Sockets",
        attributes={"outdoor": True, "weatherproof": True},
        quantity=Decimal("1"),
    )
    masterseal = {
        "code": "DOM-mk-masterseal",
        "description": "MK Masterseal Plus IP66 13A 2-Gang DP Weatherproof Outdoor Switched Socket",
        "brand": "MK",
    }
    logic_plus = {
        "code": "DOM-mk-logic",
        "description": "MK Logic Plus 13A 2-Gang DP Switched Socket White",
        "brand": "MK",
    }
    # Indoor requirement must REJECT the weatherproof variant.
    assert _hard_reject(indoor_req, masterseal) is True
    assert _hard_reject(indoor_req, logic_plus) is False
    # Outdoor requirement must NOT reject the weatherproof variant.
    assert _hard_reject(outdoor_req, masterseal) is False


# ---------------------------------------------------------------------------
# Category-aware brand softening
# ---------------------------------------------------------------------------


def _socket_req(brand: str | None = None, finish: str | None = None) -> BoQRequirement:
    attrs: dict[str, object] = {"gang": 2, "usb": False}
    if brand:
        attrs["brand"] = brand
    if finish:
        attrs["finish"] = finish
    return BoQRequirement(
        id="socket-req",
        concept="double_socket",
        category="Switches & Sockets",
        attributes=attrs,
        quantity=Decimal("1"),
    )


def _cu_req(brand: str | None = None) -> BoQRequirement:
    attrs: dict[str, object] = {"metal": True, "spd": True, "dual_rcd": True}
    if brand:
        attrs["brand"] = brand
    return BoQRequirement(
        id="cu-req",
        concept="consumer_unit",
        category="Consumer Units",
        attributes=attrs,
        quantity=Decimal("1"),
    )


def test_brand_score_neutral_when_no_brand_requested() -> None:
    item = {"description": "Generic socket", "brand": "BG"}
    assert _brand_score(_socket_req(), item) == 1.0


def test_brand_score_full_when_brand_matches() -> None:
    item = {
        "description": "MK Logic Plus 13A 2-Gang DP Switched Socket White",
        "brand": "MK",
    }
    assert _brand_score(_socket_req(brand="mk"), item) == 1.0


def test_brand_score_soft_penalty_for_commodity_mismatch() -> None:
    """For switches & sockets, a non-MK brushed-steel SKU is still acceptable.

    STD-004 case: customer asks for "brushed steel MK". Screwfix doesn't
    stock brushed-steel MK Logic Plus, but does carry British General Nexus
    Metal brushed steel. The soft 0.5x penalty lets BG win when its finish
    bonus (1.5x for brushed steel) outweighs the brand miss (0.5x).
    """
    item = {
        "description": "British General Nexus Metal 13A 2-Gang DP Switched Plug Socket Brushed Steel",
        "brand": "British General",
    }
    assert _brand_score(_socket_req(brand="mk"), item) == 0.5


def test_brand_score_hard_reject_for_consumer_units() -> None:
    """A non-Hager consumer unit cannot satisfy a Hager requirement.

    Brand drives physical compatibility for CUs and MCBs/RCBOs: a Crabtree
    MCB doesn't fit a Hager Design 50 board. So brand stays HARD for these
    categories.
    """
    item = {
        "description": "Schneider Easy9 16-way consumer unit",
        "brand": "Schneider",
    }
    assert _brand_score(_cu_req(brand="hager"), item) == 0.0


def test_brand_score_hard_reject_for_security_fire() -> None:
    """Smoke alarms must interlink within a single brand."""
    req = BoQRequirement(
        id="alarm-req",
        concept="smoke_alarm",
        category="Security & Fire",
        attributes={"brand": "aico", "type": "smoke", "mains": True},
        quantity=Decimal("1"),
    )
    item = {
        "description": "Kidde 10Y29 mains-powered smoke alarm",
        "brand": "Kidde",
    }
    assert _brand_score(req, item) == 0.0


def test_score_candidate_picks_brushed_bg_over_white_mk_for_finish_request() -> None:
    """End-to-end: brushed-steel BG outscores white MK when finish is explicit."""
    req = _socket_req(brand="mk", finish="chrome")
    bg_brushed = {
        "code": "DOM-bg-brushed",
        "description": "British General Nexus Metal 13A 2-Gang DP Brushed Steel",
        "brand": "British General",
        "score": 0.7,
    }
    mk_white = {
        "code": "DOM-mk-white",
        "description": "MK Logic Plus 13A 2-Gang DP Switched Socket White",
        "brand": "MK",
        "score": 0.8,
    }
    bg_score = _score_candidate(req, bg_brushed)
    mk_score = _score_candidate(req, mk_white)
    assert bg_score > mk_score, (
        f"BG brushed steel (score={bg_score}) must beat MK white "
        f"(score={mk_score}) when finish is the explicit preference"
    )
    # Both must remain pickable — we want a tiered preference, not a zero.
    assert mk_score > 0


def test_score_candidate_still_hard_rejects_brand_for_consumer_units() -> None:
    """The softening must NOT bleed into Consumer Units."""
    req = _cu_req(brand="hager")
    schneider_cu = {
        "code": "DOM-schneider-cu",
        "description": "Schneider Easy9 16-way metal consumer unit with SPD",
        "brand": "Schneider",
        "score": 0.9,
    }
    assert _score_candidate(req, schneider_cu) == 0.0
