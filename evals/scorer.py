"""Rule-based scorer for the domestic electrical golden dataset."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

ROUND_HALF = Decimal("0.01")

# Map dataset categories (snake_case) to the cost-item category strings stored
# in the OCERP/Qdrant payloads.
DATASET_TO_COST_CATEGORIES: dict[str, list[str]] = {
    "switches_sockets": ["Switches & Sockets"],
    "consumer_units": ["Consumer Units"],
    "mcb_rcd_rcbo": ["Circuit Protection"],
    "lighting": ["Lighting"],
    "cable": ["Cable"],
    "security_fire": ["Security & Fire"],
    "wiring_accessories": ["Wiring Accessories"],
    "conduit_trunking": ["Conduit & Trunking"],
    "heating_cooling": ["Heating & Cooling"],
    "tools": ["Tools"],
    "distribution": ["Distribution"],
    "industrial": ["Industrial"],
}

ACCESSORY_CATEGORIES = {
    "Switches & Sockets",
    "Wiring Accessories",
    "Conduit & Trunking",
}


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _norm(text: str | None) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text.lower().strip())


def _is_labour_line(item: dict[str, Any]) -> bool:
    code = str(item.get("code", "")).upper()
    category = str(item.get("category", "")).lower()
    return code.startswith("LABOUR-") or category == "labour"


def _item_total_qty(items: list[dict[str, Any]]) -> Decimal:
    return sum((_to_decimal(it.get("quantity", 0)) for it in items), Decimal("0"))


def _material_total(items: list[dict[str, Any]]) -> Decimal:
    return sum(
        (_to_decimal(it.get("material_total", 0)) for it in items if not _is_labour_line(it)),
        Decimal("0"),
    )


def _labour_hours_total(items: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for it in items:
        if _is_labour_line(it):
            qty = _to_decimal(it.get("quantity", 0))
            hours = _to_decimal(it.get("labour_hours", 0))
            total += qty * hours
    return total


def _labour_cost_total(items: list[dict[str, Any]]) -> Decimal:
    return sum(
        (_to_decimal(it.get("labour_total", 0)) for it in items if _is_labour_line(it)),
        Decimal("0"),
    )


# ---------------------------------------------------------------------------
# Item matchers
# ---------------------------------------------------------------------------

def _matches_category(item: dict[str, Any], dataset_category: str) -> bool:
    cost_cats = DATASET_TO_COST_CATEGORIES.get(dataset_category, [])
    if not cost_cats:
        return False
    return (item.get("category") or "").strip().lower() in {c.lower() for c in cost_cats}


def _desc_contains(item: dict[str, Any], needles: list[str]) -> bool:
    desc = _norm(item.get("description", ""))
    return all(needle in desc for needle in needles)


def _desc_any(item: dict[str, Any], needles: list[str]) -> bool:
    desc = _norm(item.get("description", ""))
    return any(needle in desc for needle in needles)


KNOWN_BRANDS: set[str] = {
    "aico",
    "hager",
    "mk",
    "british general",
    "scolmore click",
    "contactum",
    "lewden",
    "knightsbridge",
    "lap",
    "luceco",
    "philex",
    "yale",
    "bg",
}


def _extract_leading_brand(concept: str) -> tuple[str | None, str]:
    """If concept starts with a known brand, return (brand, rest)."""
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if concept == brand or concept.startswith(f"{brand} "):
            return brand, concept[len(brand):].strip()
    return None, concept


def _match_concept(items: list[dict[str, Any]], concept: str) -> list[dict[str, Any]]:
    """Return line items that match a free-text concept/keyword."""
    concept = _norm(concept)

    # Explicit brand checks
    brand_match = re.search(r"(?:branded?|brand)\s+([a-z0-9\-&\s]+)", concept)
    target_brand = brand_match.group(1).strip() if brand_match else None

    # Handle leading brand names such as "Aico smoke alarms" or "Hager consumer unit"
    if target_brand is None:
        target_brand, concept = _extract_leading_brand(concept)

    predicates: list[Callable[[dict[str, Any]], bool]] = []

    # Category-level concepts
    if concept in {"consumer unit", "fuse box", "fusebox", "distribution board", "cu"}:
        predicates.append(lambda it: _matches_category(it, "consumer_units") or _desc_any(it, ["consumer unit", "fuse box", "fusebox", "distribution board"]))
    elif concept in {"garage consumer unit", "garage cu"}:
        predicates.append(lambda it: (_matches_category(it, "consumer_units") and _desc_contains(it, ["garage"])))
    elif concept in {"house consumer unit", "main consumer unit"}:
        predicates.append(lambda it: (_matches_category(it, "consumer_units") and not _desc_contains(it, ["garage"])))
    elif "socket" in concept and "usb" in concept:
        predicates.append(lambda it: (_matches_category(it, "switches_sockets") and _desc_contains(it, ["usb"])))
    elif "socket" in concept:
        predicates.append(lambda it: _matches_category(it, "switches_sockets") and _desc_any(it, ["socket", "switched"]))
    elif "double socket" in concept or "2-gang socket" in concept:
        predicates.append(lambda it: (_matches_category(it, "switches_sockets") and _desc_any(it, ["2-gang", "2 gang", "double socket"])))
    elif "cooker switch" in concept or "cooker circuit" in concept:
        predicates.append(lambda it: (_matches_category(it, "switches_sockets") and _desc_any(it, ["cooker", "45a"])) or (_matches_category(it, "mcb_rcd_rcbo") and _desc_contains(it, ["cooker"])))
    elif "light point" in concept or "lighting point" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and not _desc_contains(it, ["driver", "led lamp", "gu10"]))
    elif "downlight" in concept or "spotlight" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and _desc_any(it, ["downlight", "spotlight", "down light", "spot light"]))
    elif "batten" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and _desc_contains(it, ["batten"]))
    elif concept in {"light", "lights"}:
        predicates.append(
            lambda it: _matches_category(it, "lighting")
            and not _desc_contains(it, ["driver", "led lamp", "gu10"])
        )
    elif "smoke/heat detector" in concept or "smoke heat detector" in concept:
        predicates.append(lambda it: _matches_category(it, "security_fire") and _desc_any(it, ["smoke", "heat", "detector", "alarm"]))
    elif "/" in concept and ("detector" in concept or "alarm" in concept):
        # Slash-OR concepts such as "smoke/heat/co alarms"
        tokens = [t.strip() for t in concept.split("/") if t.strip()]

        def _slash_or_match(it: dict[str, Any], tokens: list[str] = tokens) -> bool:
            return _matches_category(it, "security_fire") and _desc_any(it, tokens)

        predicates.append(_slash_or_match)
    elif "smoke alarm" in concept or "smoke detector" in concept:
        predicates.append(lambda it: _matches_category(it, "security_fire") and _desc_contains(it, ["smoke"]))
    elif "heat detector" in concept or "heat alarm" in concept:
        predicates.append(lambda it: _matches_category(it, "security_fire") and _desc_contains(it, ["heat"]))
    elif "co alarm" in concept or "carbon monoxide" in concept:
        predicates.append(lambda it: _matches_category(it, "security_fire") and _desc_any(it, ["carbon monoxide", "co alarm"]))
    elif "emergency lighting" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and _desc_any(it, ["emergency", "bulkhead"]))
    elif "rcbo" in concept or "rcbos" in concept:
        predicates.append(lambda it: _matches_category(it, "mcb_rcd_rcbo") and _desc_contains(it, ["rcbo"]))
    elif "afdd" in concept:
        predicates.append(lambda it: _matches_category(it, "mcb_rcd_rcbo") and _desc_contains(it, ["afdd"]))
    elif "type a rcd" in concept or "type-a rcd" in concept:
        predicates.append(
            lambda it: _matches_category(it, "mcb_rcd_rcbo")
            and _desc_any(it, ["type a", "type-a"])
            and _desc_contains(it, ["rcd"])
        )
    elif "spd" in concept or "surge" in concept:
        predicates.append(lambda it: _desc_any(it, ["spd", "surge"]))
    elif concept in {"mcb", "mcbs", "standard mcb", "miniature circuit breaker", "miniature circuit breakers"}:
        predicates.append(
            lambda it: _matches_category(it, "mcb_rcd_rcbo")
            and _desc_contains(it, ["mcb"])
            and not _desc_any(it, ["rcbo", "afdd", "rcd"])
        )
    elif "32a mcb" in concept or "32a breaker" in concept:
        predicates.append(lambda it: _matches_category(it, "mcb_rcd_rcbo") and _desc_contains(it, ["32a"]) and _desc_contains(it, ["mcb"]))
    elif "swa cable" in concept or "armoured cable" in concept:
        predicates.append(lambda it: _matches_category(it, "cable") and _desc_any(it, ["swa", "armoured"]))
    elif re.match(r"^(\d+)mm\s*cable$", concept):
        mm = re.match(r"^(\d+)mm\s*cable$", concept).group(1)  # type: ignore[union-attr]
        predicates.append(lambda it, mm=mm: _matches_category(it, "cable") and _desc_contains(it, [f"{mm}mm"]))  # type: ignore[misc]
    elif "earth rod" in concept:
        predicates.append(lambda it: _desc_contains(it, ["earth rod"]))
    elif "bonding clamp" in concept or "main equipotential" in concept:
        predicates.append(lambda it: _desc_any(it, ["bonding clamp", "equipotential", "main bonding"]))
    elif "supplementary bonding" in concept:
        predicates.append(lambda it: _desc_contains(it, ["supplementary bonding"]))
    elif "weatherproof isolator" in concept:
        predicates.append(lambda it: _desc_any(it, ["weatherproof isolator", "isolator"]))
    elif "outdoor socket" in concept:
        predicates.append(lambda it: _matches_category(it, "switches_sockets") and _desc_any(it, ["weatherproof", "outdoor", "ip66"]))
    elif "outdoor wall light" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and _desc_any(it, ["outdoor", "wall light", "ip44"]))
    elif "underfloor heating mat" in concept:
        predicates.append(lambda it: _matches_category(it, "heating_cooling") and _desc_contains(it, ["underfloor heating mat"]))
    elif "underfloor heating thermostat" in concept or "ufh thermostat" in concept:
        predicates.append(lambda it: _matches_category(it, "heating_cooling") and _desc_contains(it, ["thermostat"]))
    elif "dedicated mcb" in concept and "ufh" in concept:
        predicates.append(
            lambda it: _matches_category(it, "mcb_rcd_rcbo")
            and _desc_contains(it, ["mcb"])
            and not _desc_any(it, ["rcbo", "afdd", "rcd"])
        )
    elif "led driver" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and _desc_contains(it, ["driver"]))
    elif "under cabinet" in concept or "under-cabinet" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and _desc_any(it, ["under cabinet", "under-cabinet"]))
    elif "dimmer switch" in concept or "dimmer" in concept:
        predicates.append(lambda it: _matches_category(it, "switches_sockets") and _desc_contains(it, ["dimmer"]))
    elif "dimmable downlight" in concept:
        predicates.append(lambda it: _matches_category(it, "lighting") and _desc_contains(it, ["dimmable", "downlight"]))
    elif "brushed chrome" in concept or "brushed steel" in concept:
        predicates.append(lambda it: _desc_any(it, ["chrome", "brushed"]))
    elif "trunking" in concept:
        predicates.append(lambda it: _matches_category(it, "conduit_trunking") or _desc_contains(it, ["trunking"]))
    elif ("cable" in concept and "metre" in concept) or "cable" in concept:
        predicates.append(lambda it: _matches_category(it, "cable"))
    else:
        # Fallback: substring search on description/category/brand/SKU
        def _fallback_match(it: dict[str, Any], concept: str = concept) -> bool:
            return (
                concept in _norm(it.get("description", ""))
                or concept in _norm(it.get("category", ""))
                or concept in _norm(it.get("brand", ""))
            )

        predicates.append(_fallback_match)

    matched = [it for it in items if any(p(it) for p in predicates)]

    if target_brand:
        matched = [it for it in matched if target_brand in _norm(it.get("brand", ""))]

    # Generic brand-only searches such as "Aico detectors" - no specific item
    # type was given, so match any item of that brand in the relevant category.
    if not matched and target_brand and concept in {"detectors", "detector", "alarms", "alarm", "devices", "device"}:
        matched = [
            it
            for it in items
            if target_brand in _norm(it.get("brand", ""))
            and _matches_category(it, "security_fire")
        ]

    return matched


# ---------------------------------------------------------------------------
# Criterion evaluation helpers
# ---------------------------------------------------------------------------

@dataclass
class CriterionResult:
    criterion: str
    passed: bool | None
    detail: str = ""
    soft: bool = False  # True for subjective / textual checks


@dataclass
class CaseReport:
    case_id: str
    category: str
    difficulty: str
    passed: bool
    criteria_results: list[CriterionResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _response_text(response: dict[str, Any]) -> str:
    parts = [
        response.get("notes", ""),
        " ".join(response.get("warnings", [])),
    ]
    analysis = response.get("analysis") or {}
    if isinstance(analysis, dict):
        parts.append(analysis.get("job_summary", ""))
    return _norm(" ".join(str(p) for p in parts if p))


def _extract_quoted_strings(text: str) -> list[str]:
    return re.findall(r"['\"]([^'\"]+)['\"]", text)


def _extract_range(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Extract a numeric range such as 'between GBP 500 and GBP 800' or '6-12 hours'."""
    text = text.lower()
    m = re.search(r"between\s+gbp?\s*(\d[\d,]*(?:\.\d+)?)\s+and\s+gbp?\s*(\d[\d,]*(?:\.\d+)?)", text)
    if m:
        return Decimal(m.group(1).replace(",", "")), Decimal(m.group(2).replace(",", ""))
    m = re.search(r"between\s+(\d[\d,]*(?:\.\d+)?)\s+and\s+(\d[\d,]*(?:\.\d+)?)", text)
    if m:
        return Decimal(m.group(1).replace(",", "")), Decimal(m.group(2).replace(",", ""))
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*-\s*(\d[\d,]*(?:\.\d+)?)", text)
    if m:
        return Decimal(m.group(1).replace(",", "")), Decimal(m.group(2).replace(",", ""))
    return None, None


def _extract_number_and_item(text: str) -> tuple[Decimal | None, str | None]:
    """Parse 'at least 10 double sockets' or 'exactly 4 sockets'."""
    text = _norm(text)
    m = re.search(r"(?:at least|minimum|min)\s+(\d+)\s+(.+)", text)
    if m:
        return Decimal(m.group(1)), m.group(2).strip()
    m = re.search(r"exactly\s+(\d+)\s+(.+)", text)
    if m:
        return Decimal(m.group(1)), m.group(2).strip()
    m = re.search(r"(\d+)(?:-way|-way minimum)?\s+(.+)", text)
    if m:
        return Decimal(m.group(1)), m.group(2).strip()
    return None, None


def _extract_quantity_constraint(text: str) -> tuple[str | None, Decimal | None]:
    """Look for '(quantity >= 1)' style constraints."""
    text = text.replace("=", "==")
    m = re.search(r"quantity\s*([><=!]+)\s*(\d+)", text)
    if m:
        return m.group(1), Decimal(m.group(2))
    return None, None


def _compare_qty(operator: str, actual: Decimal, target: Decimal) -> bool:
    if ">=" in operator:
        return actual >= target
    if "<=" in operator:
        return actual <= target
    if ">" in operator:
        return actual > target
    if "<" in operator:
        return actual < target
    return actual == target


def _split_conjunctions(phrase: str) -> list[str]:
    """Split a phrase like 'cooker switch and 6mm cable' into subphrases."""
    parts = re.split(r"\s+(?:and|with)\s+", phrase)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Individual criterion handlers
# ---------------------------------------------------------------------------

def _check_spec_level(criterion: str, response: dict[str, Any]) -> CriterionResult:
    quoted = _extract_quoted_strings(criterion)
    allowed = {q.lower().replace(" ", "_") for q in quoted}
    actual = ((response.get("analysis") or {}).get("spec_level") or "").lower().replace(" ", "_")
    if actual in allowed:
        return CriterionResult(criterion, True, f"spec_level={actual} in {allowed}")
    if not allowed:
        return CriterionResult(criterion, None, "could not parse allowed spec levels")
    return CriterionResult(criterion, False, f"spec_level={actual!r}, expected one of {allowed}")


def _check_room_count(criterion: str, response: dict[str, Any]) -> CriterionResult:
    m = re.search(r"(\d+)", criterion)
    if not m:
        return CriterionResult(criterion, None, "could not parse target room count")
    target = int(m.group(1))
    actual = (response.get("analysis") or {}).get("room_count")
    if actual is None:
        return CriterionResult(criterion, False, "analysis.room_count is null")
    if actual == target:
        return CriterionResult(criterion, True, f"room_count={actual}")
    return CriterionResult(criterion, False, f"room_count={actual}, expected {target}")


def _check_material_cost_range(criterion: str, response: dict[str, Any]) -> CriterionResult:
    lo, hi = _extract_range(criterion)
    if lo is None or hi is None:
        return CriterionResult(criterion, None, "could not parse material cost range")
    items = response.get("line_items", [])
    material = _material_total(items)
    passed = lo <= material <= hi
    return CriterionResult(
        criterion,
        passed,
        f"material cost ex-VAT = £{material:.2f}, expected £{lo:.2f}-£{hi:.2f}",
    )


def _check_labour_hours_range(criterion: str, response: dict[str, Any]) -> CriterionResult:
    lo, hi = _extract_range(criterion)
    if lo is None or hi is None:
        return CriterionResult(criterion, None, "could not parse labour hours range")
    items = response.get("line_items", [])
    hours = _labour_hours_total(items)
    passed = lo <= hours <= hi
    return CriterionResult(
        criterion,
        passed,
        f"labour hours = {hours:.2f}, expected {lo:.2f}-{hi:.2f}",
    )


def _check_quote_equals_material(criterion: str, response: dict[str, Any]) -> CriterionResult:
    items = response.get("line_items", [])
    material = _material_total(items)
    subtotal = _to_decimal(response.get("subtotal", 0))
    labour_cost = _labour_cost_total(items)
    passed = labour_cost == 0 and abs(subtotal - material) < Decimal("1")
    return CriterionResult(
        criterion,
        passed,
        f"subtotal=£{subtotal:.2f}, material=£{material:.2f}, labour cost=£{labour_cost:.2f}",
    )


def _check_no_labour(criterion: str, response: dict[str, Any]) -> CriterionResult:
    items = response.get("line_items", [])
    labour_items = [it for it in items if _is_labour_line(it)]
    passed = len(labour_items) == 0 and _labour_hours_total(items) == 0
    return CriterionResult(
        criterion,
        passed,
        f"{len(labour_items)} labour line(s), {float(_labour_hours_total(items)):.2f} labour hours",
    )


def _check_all_accessories_brand(criterion: str, response: dict[str, Any]) -> CriterionResult:
    quoted = _extract_quoted_strings(criterion)
    brand = quoted[0] if quoted else None
    if not brand:
        return CriterionResult(criterion, None, "could not parse brand")
    items = response.get("line_items", [])
    accessory_items = [it for it in items if (it.get("category") or "") in ACCESSORY_CATEGORIES]
    mismatches = [
        it for it in accessory_items if brand.lower() not in _norm(it.get("brand", ""))
    ]
    passed = len(accessory_items) > 0 and len(mismatches) == 0
    detail = f"{len(accessory_items)} accessory line(s), {len(mismatches)} not {brand}"
    return CriterionResult(criterion, passed, detail, soft=True)


def _check_flag_in_output(criterion: str, response: dict[str, Any]) -> CriterionResult:
    quoted = _extract_quoted_strings(criterion)
    target = quoted[0].lower() if quoted else None
    if not target:
        return CriterionResult(criterion, None, "could not parse flag text")
    analysis = response.get("analysis") or {}
    flags = {f.lower() for f in (analysis.get("regulatory_flags") or [])}
    text = _response_text(response)
    passed = target in text or target.replace("_", " ") in text or target in flags
    return CriterionResult(
        criterion,
        passed,
        f"searched for {target!r} in analysis/notes/warnings",
        soft=True,
    )


def _check_clarifying_questions(criterion: str, response: dict[str, Any]) -> CriterionResult:
    text = _response_text(response)
    passed = "?" in text
    return CriterionResult(
        criterion,
        passed,
        "notes/warnings contain a question mark" if passed else "no question mark found",
        soft=True,
    )


def _check_item_presence(criterion: str, response: dict[str, Any]) -> CriterionResult:
    items = response.get("line_items", [])
    text = criterion.lower()

    # Extract the phrase after "must contain"
    m = re.search(r"must contain\s+(.+?)(?:\s*\(|$)", text)
    if not m:
        return CriterionResult(criterion, None, "could not parse item presence criterion")
    phrase = m.group(1).strip()

    # Pull out any parenthetical quantity constraint
    op, qty_target = _extract_quantity_constraint(criterion)

    # Strip leading quantity words from the phrase so matching is against the
    # item concept, not the full "at least 5 ..." string.
    clean_phrase = re.sub(r"^(at least|minimum|min|exactly)\s+\d+\s+", "", phrase, flags=re.I)
    clean_phrase = re.sub(r"^\d+\s+", "", clean_phrase)

    # Handle "X or Y" presence
    if " or " in clean_phrase and " or flag " not in clean_phrase:
        sub_phrases = [p.strip() for p in clean_phrase.split(" or ")]
        matched_any = False
        details: list[str] = []
        for sub in sub_phrases:
            matched = _match_concept(items, sub)
            total = _item_total_qty(matched)
            details.append(f"{sub}: qty={total}")
            if total > 0:
                matched_any = True
        return CriterionResult(
            criterion,
            matched_any,
            "; ".join(details),
        )

    # Handle "flag X" alternative: "SPD or flag spd_required"
    if " or flag " in clean_phrase:
        item_part, flag_part = clean_phrase.split(" or flag ", 1)
        matched = _match_concept(items, item_part)
        item_qty = _item_total_qty(matched)
        analysis = response.get("analysis") or {}
        flags = {f.lower() for f in (analysis.get("regulatory_flags") or [])}
        flag_present = flag_part.strip().lower().replace("'", "").replace('"', "") in flags
        passed = item_qty > 0 or flag_present
        return CriterionResult(
            criterion,
            passed,
            f"{item_part}: qty={item_qty}; flag {flag_part!r}: present={flag_present}",
        )

    # Conjunctions: split by "and"/"with" and require all subphrases
    sub_phrases = _split_conjunctions(clean_phrase)
    if len(sub_phrases) > 1:
        all_passed = True
        details = []
        for sub in sub_phrases:
            sub = re.sub(r"^\d+\s+", "", sub.strip())
            matched = _match_concept(items, sub)
            total = _item_total_qty(matched)
            details.append(f"{sub}: qty={total}")
            if total <= 0:
                all_passed = False
        return CriterionResult(
            criterion,
            all_passed,
            "; ".join(details),
        )

    # Single concept with optional quantity threshold
    matched = _match_concept(items, clean_phrase)
    total = _item_total_qty(matched)

    # Auto-detect threshold words in the phrase if no explicit constraint
    if op is None:
        num, item_text = _extract_number_and_item(criterion)
        if num is not None and item_text is not None and any(
            tok in phrase for tok in item_text.split()
        ):
            if "exactly" in text:
                op, qty_target = "==", num
            elif "at least" in text or "minimum" in text:
                op, qty_target = ">=", num
            else:
                op, qty_target = ">=", num

    if op and qty_target is not None:
        passed = _compare_qty(op, total, qty_target)
        detail = f"{phrase}: qty={total}, required {op} {qty_target}"
    else:
        passed = total > 0
        detail = f"{phrase}: qty={total}"

    return CriterionResult(criterion, passed, detail)


def _check_item_absence(criterion: str, response: dict[str, Any]) -> CriterionResult:
    items = response.get("line_items", [])
    text = criterion.lower()

    # Special cases
    if "labour" in text:
        return _check_no_labour(criterion, response)

    # Try to extract phrase after "must not contain"
    m = re.search(r"must not\s+(?:contain|include)\s+(.+?)(?:\s*\(|$)", text)
    if not m:
        return CriterionResult(criterion, None, "could not parse absence criterion")
    phrase = m.group(1).strip()

    # Handle comma / or lists: "sockets, switches, or extensive cable"
    sub_phrases = re.split(r",\s*|\s+or\s+", phrase)
    sub_phrases = [p.strip() for p in sub_phrases if p.strip()]

    any_found = False
    details: list[str] = []
    for sub in sub_phrases:
        # Ignore filler words
        if sub in {"or", "and", "extensive"}:
            continue
        matched = _match_concept(items, sub)
        total = _item_total_qty(matched)
        details.append(f"{sub}: qty={total}")
        if total > 0:
            any_found = True

    passed = not any_found
    return CriterionResult(criterion, passed, "; ".join(details))


# ---------------------------------------------------------------------------
# Criterion dispatcher
# ---------------------------------------------------------------------------

def evaluate_criterion(criterion: str, response: dict[str, Any]) -> CriterionResult:
    text = criterion.lower()

    if "must not" in text:
        return _check_item_absence(criterion, response)

    if text.startswith("spec_level") or "spec_level" in text:
        return _check_spec_level(criterion, response)

    if "room_count" in text or "room count" in text:
        return _check_room_count(criterion, response)

    if "total material cost" in text:
        return _check_material_cost_range(criterion, response)

    if "labour estimate" in text or ("labour hours" in text and "between" in text):
        return _check_labour_hours_range(criterion, response)

    if "quote total should equal material cost" in text:
        return _check_quote_equals_material(criterion, response)

    if "all accessories must be" in text or "branded accessories" in text:
        result = _check_all_accessories_brand(criterion, response)
        if result.passed is None:
            return CriterionResult(criterion, None, result.detail, soft=True)
        return CriterionResult(
            criterion, result.passed, result.detail, soft=True
        )

    if "agent should flag" in text:
        return _check_flag_in_output(criterion, response)

    if "agent should ask clarifying questions" in text:
        return _check_clarifying_questions(criterion, response)

    if "bom must contain" in text:
        return _check_item_presence(criterion, response)

    if "bom should be minimal" in text or "bom should be conservative" in text:
        # Soft check: ensure socket/light counts are within a small default band.
        return _check_item_presence(
            criterion.replace("should be minimal/conservative", "must contain"),
            response,
        )

    return CriterionResult(criterion, None, "unrecognised criterion (manual review)", soft=True)


def _expected_material_range(case: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    """Pull the material-cost range straight from the case's pass criteria.

    The criterion text is the authoritative source the scorer uses for the
    hard pass/fail check, so we re-parse it here rather than reading the
    case's ``estimated_material_cost_ex_vat`` block (which sometimes drifts).
    """
    for criterion in case.get("pass_criteria", []):
        if "material cost must be between" in criterion.lower():
            return _extract_range(criterion)
    return None, None


def _cost_attribution(items: list[dict[str, Any]], top_n: int = 8) -> list[dict[str, Any]]:
    """Return the top N material lines ranked by contribution to total cost.

    Materialises into JSON-friendly dicts so the eval report can include it
    without depending on the live response shape.
    """
    materials = [it for it in items if not _is_labour_line(it)]
    materials.sort(key=lambda it: float(it.get("material_total", 0) or 0), reverse=True)
    total = sum((_to_decimal(it.get("material_total", 0)) for it in materials), Decimal("0"))
    out: list[dict[str, Any]] = []
    for it in materials[:top_n]:
        mt = _to_decimal(it.get("material_total", 0)).quantize(ROUND_HALF)
        pct = float((mt / total * 100).quantize(Decimal("0.1"))) if total > 0 else 0.0
        out.append(
            {
                "code": it.get("code"),
                "description": (it.get("description") or "")[:80],
                "category": it.get("category"),
                "quantity": float(_to_decimal(it.get("quantity", 0))),
                "unit_price": float(_to_decimal(it.get("unit_price", 0)).quantize(Decimal("0.0001"))),
                "material_total": float(mt),
                "pct_of_material_total": pct,
            }
        )
    return out


def score_case(case: dict[str, Any], response: dict[str, Any]) -> CaseReport:
    """Score a single golden case against an OCERP response."""
    results: list[CriterionResult] = []
    for criterion in case.get("pass_criteria", []):
        results.append(evaluate_criterion(criterion, response))

    # A case passes if every scored criterion passed. Soft/subjective failures
    # are allowed (we only fail on hard objective checks).
    hard_failures = [r for r in results if r.passed is False and not r.soft]
    passed = len(hard_failures) == 0

    items = response.get("line_items", [])
    material_total = _material_total(items).quantize(ROUND_HALF)
    expected_lo, expected_hi = _expected_material_range(case)
    cost_delta: float | None = None
    cost_pct_over: float | None = None
    if expected_lo is not None and expected_hi is not None:
        if material_total < expected_lo:
            cost_delta = float(material_total - expected_lo)
            cost_pct_over = float(
                ((material_total - expected_lo) / expected_lo * 100).quantize(Decimal("0.1"))
            )
        elif material_total > expected_hi:
            cost_delta = float(material_total - expected_hi)
            cost_pct_over = float(
                ((material_total - expected_hi) / expected_hi * 100).quantize(Decimal("0.1"))
            )
        else:
            cost_delta = 0.0
            cost_pct_over = 0.0

    summary = {
        "line_item_count": len(items),
        "material_total": float(material_total),
        "labour_hours_total": float(_labour_hours_total(items).quantize(ROUND_HALF)),
        "subtotal": float(_to_decimal(response.get("subtotal", 0)).quantize(ROUND_HALF)),
        "total": float(_to_decimal(response.get("total", 0)).quantize(ROUND_HALF)),
        "confidence": str(response.get("confidence", "n/a")),
        "analysis": response.get("analysis") or {},
        # Self-diagnostic cost attribution: lets future regressions answer
        # "WHY is the material total out of range?" without re-running by hand.
        "expected_material_range": (
            {"min": float(expected_lo), "max": float(expected_hi)}
            if expected_lo is not None and expected_hi is not None
            else None
        ),
        "material_cost_delta": cost_delta,
        "material_cost_delta_pct": cost_pct_over,
        "top_material_items": _cost_attribution(items),
    }

    return CaseReport(
        case_id=case["id"],
        category=case["category"],
        difficulty=case["difficulty"],
        passed=passed,
        criteria_results=results,
        summary=summary,
    )
