"""Generic requirement generation for the BoQ engine.

This module emits brandless `BoQRequirement` objects that are later resolved
to real catalogue items by the `CatalogueResolver`.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any, ClassVar

from ocerp.services.boq_models import BoQRequirement


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _extract_bedrooms(description: str) -> Decimal:
    text = description.lower()
    word_map = {
        "one bed": 1,
        "two bed": 2,
        "three bed": 3,
        "four bed": 4,
        "five bed": 5,
        "six bed": 6,
    }
    found: list[int] = []
    for word, num in word_map.items():
        if word in text:
            found.append(num)
    found.extend(int(m.group(1)) for m in re.finditer(r"(\d+)\s*bed", text))
    return Decimal(max(found)) if found else Decimal("0")


def _extract_rooms(description: str, bedrooms: Decimal) -> Decimal:
    text = description.lower()
    m = re.search(r"(\d+)\s*(?:room|rooms)", text)
    if m:
        return Decimal(m.group(1))
    if bedrooms > 0:
        return bedrooms + Decimal("3")
    return Decimal("0")


def _has_cu_upgrade_intent(description: str) -> bool:
    """Return True when the description clearly asks for a CU replacement."""
    text = description.lower()
    if "consumer unit upgrade" in text:
        return True
    # Look for an action verb near a CU/fusebox term, but skip phrases like
    # "new circuit from consumer unit" where the work is on a circuit, not the CU.
    verbs = ["replace", "replaced", "upgrade", "upgrading", "changing", "change", "new"]
    for verb in verbs:
        pattern = rf"\b{re.escape(verb)}\b(?:\s+(?!circuit|wire)\S+){{0,4}}\s+(consumer unit|fuse box|fusebox|distribution board)\b"
        if re.search(pattern, text):
            return True
    return False


def _extract_count_near(
    description: str,
    keyword: str,
    alt: str | None = None,
    default: Decimal = Decimal("0"),
) -> Decimal:
    # Normalise hyphens so "under-cabinet" is treated the same as "under cabinet".
    text = _norm(description).replace("-", " ")
    # Allow up to two intervening words (e.g. "6 double sockets" or "4 under cabinet lights").
    pattern = rf"(\d+)\s*(?:x\s*)?(?:[a-z0-9]+\s+){{0,2}}{re.escape(keyword)}"
    m = re.search(pattern, text)
    if m:
        return Decimal(m.group(1))
    if alt:
        return _extract_count_near(description, alt, default=default)
    return default


def _preferred_accessory_brand(
    prefers_bg: bool, prefers_mk: bool, prefers_hager: bool, prefers_scolmore: bool
) -> str | None:
    if prefers_mk:
        return "mk"
    if prefers_scolmore:
        return "scolmore click"
    if prefers_bg:
        return "british general"
    if prefers_hager:
        return "hager"
    return None


def _make_id(concept: str, category: str, attributes: dict[str, Any]) -> str:
    """Stable ID for de-duplicating equivalent requirements."""
    payload = json.dumps(
        {"concept": concept, "category": category, "attributes": attributes},
        sort_keys=True,
        default=str,
    )
    return f"{concept}-{hashlib.md5(payload.encode()).hexdigest()[:8]}"


def _req(
    concept: str,
    category: str,
    quantity: Decimal,
    attributes: dict[str, Any] | None = None,
    scope_tag: str = "general",
    source: str = "mandatory",
    notes: str | None = None,
) -> BoQRequirement:
    return BoQRequirement(
        id=_make_id(concept, category, attributes or {}),
        concept=concept,
        category=category,
        attributes=attributes or {},
        quantity=quantity,
        scope_tag=scope_tag,
        source=source,
        notes=notes,
    )


def _quantity_of(
    requirements: list[BoQRequirement],
    concept: str | None = None,
    category: str | None = None,
    predicate: Any = None,
) -> Decimal:
    total = Decimal("0")
    for req in requirements:
        if concept and req.concept != concept:
            continue
        if category and req.category.lower() != category.lower():
            continue
        if predicate and not predicate(req):
            continue
        total += req.quantity
    return total


def _has_concept(requirements: list[BoQRequirement], concept: str) -> bool:
    return any(req.concept == concept for req in requirements)


def _has_category(requirements: list[BoQRequirement], category: str) -> bool:
    return any(req.category.lower() == category.lower() for req in requirements)


class RequirementEngine:
    """Generate brandless BoQ requirements from a job description."""

    def __init__(self, description: str, property_type: str | None = None):
        self.description = description
        self.property_type = property_type
        self.desc = _norm(description)
        self.bedrooms = _extract_bedrooms(description)
        self.rooms = _extract_rooms(description, self.bedrooms)

        self.is_rewire = bool(re.search(r"\brewire\b|\brewiring\b", self.desc))
        self.is_cu_upgrade = _has_cu_upgrade_intent(self.description)
        self.is_partial_rewire = self.is_rewire and (
            "ground floor" in self.desc
            or "first floor" in self.desc
            or "upstairs" in self.desc
            or "downstairs" in self.desc
            or "extension" in self.desc
        )
        if self.is_partial_rewire and self.rooms > self.bedrooms + Decimal("1"):
            self.rooms = max(self.bedrooms + Decimal("1"), Decimal("3"))
        if self.is_rewire and self.bedrooms == 0 and self.rooms == 0:
            self.bedrooms = Decimal("3")
            self.rooms = Decimal("6")

        self.is_kitchen = "kitchen" in self.desc
        self.is_garage = "garage" in self.desc
        self.is_ev = "ev" in self.desc or "charger" in self.desc or "charge point" in self.desc
        self.is_extension = "extension" in self.desc
        self.is_hmo = "hmo" in self.desc
        self.wants_afdd = "afdd" in self.desc
        self.is_ufh = "underfloor" in self.desc or "ufh" in self.desc
        self.is_ambiguous = len(self.desc.split()) <= 5
        self.no_labour = (
            "no labour" in self.desc
            or "materials only" in self.desc
            or "material list" in self.desc
        )
        self.prefers_bg = "british general" in self.desc
        self.prefers_mk = " mk" in self.desc or "mk " in self.desc or self.desc.startswith("mk ")
        self.prefers_hager = "hager" in self.desc
        self.prefers_scolmore = (
            "scolmore click" in self.desc
            or "scolmore" in self.desc
            or "click accessories" in self.desc
        )
        self.prefers_aico = "aico" in self.desc
        self.prefers_chrome = (
            "brushed chrome" in self.desc
            or "brushed steel" in self.desc
            or "stainless steel" in self.desc
        )
        self.is_premium = (
            "premium" in self.desc
            or "hager" in self.desc
            or "mk " in self.desc
            or " mk" in self.desc
            or "brushed chrome" in self.desc
            or "brushed steel" in self.desc
        )
        self.is_mid_range = "mid" in self.desc or "mid-range" in self.desc
        self.is_budget = (
            "budget" in self.desc
            or "standard white" in self.desc
            or "white plastic" in self.desc
            or "cheap" in self.desc
            or "basic" in self.desc
        )

    # Concepts for which the deterministic rules are authoritative.  Any LLM
    # suggestion of the same concept is dropped so quantities stay aligned with
    # the scope-derived targets.
    _DETERMINISTIC_CONCEPTS: ClassVar[set[str]] = {
        "consumer_unit",
        "consumer_unit_with_spd",
        "fuse_box",
        "fusebox",
        "distribution_board",
        "spd_module",
        "mcb",
        "rcbo",
        "afdd",
        "type_a_rcd",
        "loft_rcbo",
        "garage_rcbo",
        "main_switch",
        "double_socket",
        "single_socket",
        "usb_socket",
        "dimmer_switch",
        "ceiling_light",
        "downlight",
        "spotlight",
        "spot",
        "recessed_light",
        "ceiling_spotlight",
        "batten_light",
        "smoke_alarm",
        "heat_detector",
        "carbon_monoxide_alarm",
        "emergency_light",
        "cooker_switch",
        "lighting_cable_1_5mm",
        "socket_cable_2_5mm",
        "cooker_cable_6mm",
        "ufh_cable_4mm",
        "swa_cable",
        "weatherproof_isolator",
        "earth_rod",
        "bonding_clamp",
        "supplementary_bonding_cable",
        "garage_consumer_unit",
        "underfloor_heating_mat",
        "thermostat",
        "under_cabinet_lighting",
        "led_driver",
        "cable",
        "lighting_cable",
        "socket_cable",
        "twin_and_earth_cable",
        "earth_cable",
    }

    # LLM suggestions that describe labour, process, or customer-supplied items
    # should never become material lines.
    _LLM_BLOCKLIST: ClassVar[set[str]] = {
        "testing",
        "test",
        "certification",
        "certificate",
        "cert",
        "inspection",
        "inspect",
        "ev_charger",
        "ev_charger_unit",
        "ev_charge_point",
        "charger",
        "wall_charger",
        "tethered_charger",
        "untethered_charger",
        "installation",
        "install",
        "labour",
        "labor",
    }

    # Substrings that almost always indicate an LLM hallucination or a poor
    # catalogue match that should not become a material line.
    _LLM_BAD_SUBSTRINGS: ClassVar[set[str]] = {
        "connector block",
        "terminal block",
        "crimp terminal",
        "crimp",
        "terminal",
        "connector",
        "chocbox",
        "choc box",
        "connector box",
        "junction box",
        "ethernet",
        "smart switch",
        "smart light",
        "cctv",
        "camera",
        "extension lead",
        "cable reel",
        "cable tidy",
        "hdmi",
        "usb charger",
        "tower",
        "adaptor",
        "adapter",
        "ceiling light",
        "pendant light",
        "recessed light",
        "chandelier",
    }

    # Concepts the LLM is allowed to add even when the same category is already
    # covered by deterministic rules.
    _LLM_COMPLEMENTARY: ClassVar[set[str]] = {
        "lamp",
        "led_lamp",
        "gu10_lamp",
        "bulb",
        "grommet",
        "trunking",
        "conduit",
        "screw",
        "cable_clip",
        "cable_gland",
        "gland",
        "swa_gland",
    }

    # Normalised concept roots that the deterministic engine already handles.
    # Any LLM requirement matching one of these is treated as a duplicate.
    _CONTROLLED_CONCEPT_ROOTS: ClassVar[set[str]] = {
        "consumer unit",
        "fuse box",
        "fusebox",
        "distribution board",
        "main switch",
        "mcb",
        "rcbo",
        "afdd",
        "rcd",
        "spd",
        "downlight",
        "spotlight",
        "spot light",
        "ceiling light",
        "pendant light",
        "recessed light",
        "batten light",
        "under cabinet",
        "undercabinet",
        "cabinet light",
        "cabinet striplight",
        "led strip",
        "double socket",
        "single socket",
        "usb socket",
        "dimmer",
        "cooker switch",
        "light switch",
        "smoke alarm",
        "heat detector",
        "carbon monoxide",
        "co alarm",
        "swa cable",
        "armoured cable",
        "earth rod",
        "bonding clamp",
        "supplementary bonding",
        "lighting cable",
        "socket cable",
        "cooker cable",
        "twin and earth",
        "back box",
        "back_box",
        "pattress",
        "chocbox",
        "choc box",
        "connector box",
        "junction box",
        "terminal block",
        "data point",
        "data socket",
        "network socket",
        "cat5",
        "cat6",
        "cat 5",
        "cat 6",
        "rj45",
        "earth bonding",
        "main earth bonding",
        "equipotential bonding",
        "earthing",
    }

    def generate(self, generated: dict[str, Any] | None = None) -> list[BoQRequirement]:
        """Return the full list of requirements for the job."""
        llm_reqs: list[BoQRequirement] = []
        if generated:
            llm_reqs = self._parse_llm_requirements(generated)
            llm_reqs = self._filter_llm_requirements(llm_reqs)

        mandatory_reqs = self._add_mandatory([])
        reqs = self._merge_with_deterministic(llm_reqs, mandatory_reqs)
        reqs = self._cap_cable_quantities(reqs)
        reqs = self._dedupe(reqs)
        return reqs

    def _filter_llm_requirements(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        """Drop labour-only LLM suggestions and anything the engine controls."""

        def _is_blocked(concept: str) -> bool:
            concept_norm = concept.lower().replace("_", " ").replace("-", " ")
            if concept in self._LLM_BLOCKLIST:
                return True
            if any(concept.startswith(prefix) for prefix in self._LLM_BLOCKLIST):
                return True
            if any(blocked in concept_norm for blocked in self._LLM_BLOCKLIST):
                return True
            if any(bad in concept_norm for bad in self._LLM_BAD_SUBSTRINGS):
                return True
            if any(comp in concept_norm for comp in self._LLM_COMPLEMENTARY):
                return False
            return any(root in concept_norm for root in self._CONTROLLED_CONCEPT_ROOTS)

        return [
            r
            for r in reqs
            if r.category != "Labour"
            and not r.concept.startswith("labour")
            and r.concept not in self._DETERMINISTIC_CONCEPTS
            and not _is_blocked(r.concept)
        ]

    def _merge_with_deterministic(
        self,
        llm_reqs: list[BoQRequirement],
        mandatory_reqs: list[BoQRequirement],
    ) -> list[BoQRequirement]:
        """Combine LLM and deterministic requirements.

        Deterministic mandatory items always win; the LLM is allowed to add
        complementary items (e.g. back boxes, lamps, trunking).
        """
        controlled_categories = {
            "Consumer Units",
            "Cable",
            "Circuit Protection",
            "Security & Fire",
            "Heating & Cooling",
        }
        # Categories where deterministic rules already decide the BOM.
        mandatory_categories = {r.category for r in mandatory_reqs}

        def _is_complementary(req: BoQRequirement) -> bool:
            concept_norm = req.concept.lower().replace("_", " ").replace("-", " ")
            return any(comp in concept_norm for comp in self._LLM_COMPLEMENTARY)

        filtered_llm = [
            r
            for r in llm_reqs
            if r.category not in mandatory_categories
            or r.category not in controlled_categories
            or _is_complementary(r)
        ]
        return filtered_llm + mandatory_reqs

    def _cap_cable_quantities(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        """Cap cable metreages to realistic domestic quantities.

        Caps are sized for the largest typical domestic job (5-bed) plus a
        safety margin so the deterministic scaling in :meth:`_cables` is not
        truncated. The LLM is still capped to prevent runaway metreage on
        hallucinated quantities.
        """
        out: list[BoQRequirement] = []
        for r in reqs:
            if r.category != "Cable":
                out.append(r)
                continue
            desc = _norm(r.concept)
            qty = r.quantity
            cap: Decimal | None = None
            if "1.5mm" in desc and qty > 200:
                cap = Decimal("200")
            elif "2.5mm" in desc and qty > 300:
                cap = Decimal("300")
            elif "6mm" in desc and qty > 40:
                cap = Decimal("40")
            elif "4mm" in desc and qty > 60:
                cap = Decimal("60")
            elif r.concept == "swa_cable" and qty > 50:
                cap = Decimal("50")
            if cap is not None:
                out.append(r.model_copy(update={"quantity": cap}))
            else:
                out.append(r)
        return out

    # ------------------------------------------------------------------
    # LLM parsing
    # ------------------------------------------------------------------

    def _parse_llm_requirements(self, generated: dict[str, Any]) -> list[BoQRequirement]:
        """Convert LLM requirements (if present) into BoQRequirements."""
        raw_reqs = generated.get("requirements") or generated.get("line_items") or []
        parsed: list[BoQRequirement] = []
        for raw in raw_reqs:
            if not isinstance(raw, dict):
                continue
            concept = raw.get("concept") or raw.get("code") or "item"
            category = raw.get("category") or "General"
            attributes = raw.get("attributes") or {}
            quantity = _to_decimal(raw.get("quantity", "1"))
            notes = raw.get("notes") or raw.get("description")
            parsed.append(
                _req(
                    concept=concept,
                    category=category,
                    quantity=quantity,
                    attributes=attributes,
                    scope_tag="llm",
                    source="llm",
                    notes=notes,
                )
            )
        return parsed

    # ------------------------------------------------------------------
    # Mandatory requirement injection
    # ------------------------------------------------------------------

    def _add_mandatory(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        reqs = self._scope_corrections(reqs)
        reqs = self._consumer_unit(reqs)
        reqs = self._circuit_protection(reqs)
        reqs = self._sockets_and_lights(reqs)
        reqs = self._cooker_switch(reqs)
        reqs = self._cables(reqs)
        reqs = self._back_boxes(reqs)
        reqs = self._fire_and_co(reqs)
        reqs = self._ev_circuit(reqs)
        reqs = self._garage(reqs)
        reqs = self._outdoor_sockets(reqs)
        reqs = self._tt_earthing(reqs)
        reqs = self._ufh(reqs)
        reqs = self._under_cabinet(reqs)
        reqs = self._ambiguous_defaults(reqs)
        return reqs

    def _scope_corrections(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        # Extensions / kitchen-only should not get a whole-house CU unless asked.
        if (
            (self.is_extension or self.is_kitchen)
            and "new consumer unit" not in self.desc
            and "consumer unit upgrade" not in self.desc
        ):
            reqs = [r for r in reqs if r.concept != "consumer_unit"]
        return reqs

    def _consumer_unit(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if self.is_cu_upgrade and not self.is_rewire:
            cu_count = _quantity_of(reqs, concept="consumer_unit")
            if cu_count > 1:
                # Keep exactly one CU.
                kept = False
                new_reqs: list[BoQRequirement] = []
                for r in reqs:
                    if r.concept == "consumer_unit":
                        if not kept:
                            new_reqs.append(r.model_copy(update={"quantity": Decimal("1")}))
                            kept = True
                    else:
                        new_reqs.append(r)
                reqs = new_reqs
            if cu_count == 0:
                brand = "hager" if self.prefers_hager else None
                attrs: dict[str, Any] = {"metal": True, "spd": True, "dual_rcd": True}
                if brand:
                    attrs["brand"] = brand
                reqs.append(
                    _req(
                        "consumer_unit",
                        "Consumer Units",
                        Decimal("1"),
                        attrs,
                        scope_tag="cu_upgrade",
                        notes="Mandatory consumer unit upgrade",
                    )
                )

        if self.is_rewire and not _has_concept(reqs, "consumer_unit"):
            brand = "hager" if self.prefers_hager else None
            attrs = {"metal": True, "spd": True, "dual_rcd": True}
            if brand:
                attrs["brand"] = brand
            reqs.append(
                _req(
                    "consumer_unit",
                    "Consumer Units",
                    Decimal("1"),
                    attrs,
                    scope_tag="rewire",
                    notes="Mandatory consumer unit for rewire",
                )
            )

        # A separate main switch is expected for full rewires.
        if self.is_rewire and not _has_concept(reqs, "main_switch"):
            reqs.append(
                _req(
                    "main_switch",
                    "Switches & Sockets",
                    Decimal("1"),
                    {"amperage": "100"},
                    scope_tag="rewire",
                    notes="Mandatory main switch",
                )
            )

        # Consumer unit upgrades are not full rewires, so we add a small amount
        # of accessories (not cable) to reflect the likely final material cost.
        if self.is_cu_upgrade and not self.is_rewire:
            smoke_attrs: dict[str, Any] = {"type": "smoke", "mains": True}
            heat_attrs: dict[str, Any] = {"type": "heat"}
            if self.prefers_aico:
                smoke_attrs["brand"] = "aico"
                heat_attrs["brand"] = "aico"
            if not _has_concept(reqs, "smoke_alarm"):
                reqs.append(
                    _req(
                        "smoke_alarm",
                        "Security & Fire",
                        Decimal("1"),
                        smoke_attrs,
                        scope_tag="cu_upgrade",
                        notes="Smoke alarm check with consumer unit upgrade",
                    )
                )
            if not _has_concept(reqs, "heat_detector"):
                reqs.append(
                    _req(
                        "heat_detector",
                        "Security & Fire",
                        Decimal("1"),
                        heat_attrs,
                        scope_tag="cu_upgrade",
                        notes="Heat detector with consumer unit upgrade",
                    )
                )
            if not _has_concept(reqs, "metal_back_box_1gang"):
                reqs.append(
                    _req(
                        "metal_back_box_1gang",
                        "Wiring Accessories",
                        Decimal("10"),
                        {"size": "1gang"},
                        scope_tag="cu_upgrade",
                        notes="Back boxes for consumer unit upgrade",
                    )
                )
            if not _has_concept(reqs, "metal_back_box_2gang"):
                reqs.append(
                    _req(
                        "metal_back_box_2gang",
                        "Wiring Accessories",
                        Decimal("5"),
                        {"size": "2gang"},
                        scope_tag="cu_upgrade",
                        notes="Back boxes for consumer unit upgrade",
                    )
                )

        return reqs

    def _circuit_protection(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        target = Decimal("0")
        if self.is_cu_upgrade and not self.is_rewire:
            target = Decimal("5")
        elif self.is_rewire:
            if "rcbo" in self.desc:
                target = max(Decimal("6"), self.bedrooms + Decimal("3"))
            else:
                target = max(Decimal("4"), self.bedrooms + Decimal("1"))
        elif self.is_extension:
            # A typical extension needs cooker + sockets + lighting circuits.
            target = Decimal("3")
        elif self.is_garage:
            target = Decimal("2")

        if target <= 0:
            return reqs

        current = _quantity_of(reqs, category="Circuit Protection")
        if current >= target:
            return reqs

        if self.wants_afdd or self.is_hmo:
            reqs.append(
                _req(
                    "afdd",
                    "Circuit Protection",
                    target - current,
                    {"type": "afdd"},
                    scope_tag="rewire",
                    notes="Mandatory AFDD protection",
                )
            )
        elif "rcbo" in self.desc:
            reqs.append(
                _req(
                    "rcbo",
                    "Circuit Protection",
                    target - current,
                    {"type": "rcbo"},
                    scope_tag="rewire",
                    notes="Mandatory RCBO protection",
                )
            )
        else:
            reqs.append(
                _req(
                    "mcb",
                    "Circuit Protection",
                    target - current,
                    {"type": "mcb"},
                    scope_tag="rewire",
                    notes="Mandatory circuit protection",
                )
            )

        # Add dedicated RCBOs for explicitly named additional circuits.
        if "loft" in self.desc and not _has_concept(reqs, "loft_rcbo"):
            reqs.append(
                _req(
                    "loft_rcbo",
                    "Circuit Protection",
                    Decimal("1"),
                    {"type": "rcbo", "loft": True},
                    scope_tag="extra_circuit",
                    notes="Additional RCBO for loft circuit",
                )
            )
        if "garage" in self.desc and not _has_concept(reqs, "garage_rcbo"):
            reqs.append(
                _req(
                    "garage_rcbo",
                    "Circuit Protection",
                    Decimal("1"),
                    {"type": "rcbo", "garage": True},
                    scope_tag="extra_circuit",
                    notes="Additional RCBO for garage circuit",
                )
            )

        # Budget jobs: downgrade RCBOs to plain MCBs unless explicitly requested.
        if (
            (self.is_budget or self.is_mid_range)
            and "rcbo" not in self.desc
            and not self.wants_afdd
        ):
            rcbo_qty = _quantity_of(
                reqs,
                category="Circuit Protection",
                predicate=lambda r: r.concept == "rcbo",
            )
            if rcbo_qty > 0:
                reqs = [r for r in reqs if r.concept != "rcbo"]
                reqs.append(
                    _req(
                        "mcb",
                        "Circuit Protection",
                        rcbo_qty,
                        {"type": "mcb"},
                        scope_tag="rewire",
                        notes="Budget MCB replacement for RCBOs",
                    )
                )

        return reqs

    def _sockets_and_lights(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        brand = _preferred_accessory_brand(
            self.prefers_bg, self.prefers_mk, self.prefers_hager, self.prefers_scolmore
        )

        if self.is_rewire:
            if self.is_partial_rewire:
                target_sockets = max(Decimal("10"), self.bedrooms * Decimal("4"))
            elif self.bedrooms <= 1:
                target_sockets = Decimal("10")
            elif self.bedrooms <= 2:
                target_sockets = Decimal("16")
            elif self.bedrooms <= 3:
                target_sockets = (
                    Decimal("26")
                    if self.is_mid_range or self.is_premium or self.prefers_scolmore
                    else Decimal("24")
                )
            else:
                target_sockets = Decimal("32")

            current_sockets = _quantity_of(reqs, concept="double_socket") + _quantity_of(
                reqs, concept="single_socket"
            )
            if current_sockets < target_sockets:
                attrs: dict[str, Any] = {"gang": 2, "usb": False}
                if self.prefers_chrome:
                    attrs["finish"] = "chrome"
                if brand:
                    attrs["brand"] = brand
                reqs.append(
                    _req(
                        "double_socket",
                        "Switches & Sockets",
                        target_sockets - current_sockets,
                        attrs,
                        scope_tag="rewire",
                        notes="Mandatory sockets for rewire",
                    )
                )

            target_lights = max(Decimal("8"), self.rooms * Decimal("2") + Decimal("4"))
            current_lights = _quantity_of(
                reqs,
                category="Lighting",
                predicate=lambda r: r.concept in {"ceiling_light", "downlight", "batten_light"},
            )
            if current_lights < target_lights:
                use_downlights = (
                    self.prefers_chrome
                    or "downlight" in self.desc
                    or (self.bedrooms >= 3 and (self.is_mid_range or self.is_premium))
                )
                if use_downlights:
                    concept = "downlight"
                    attrs = {"type": "downlight"}
                    if "dimmable" in self.desc or "dimmer" in self.desc:
                        attrs["dimmable"] = True
                else:
                    concept = "ceiling_light"
                    attrs = {"type": "ceiling"}
                reqs.append(
                    _req(
                        concept,
                        "Lighting",
                        target_lights - current_lights,
                        attrs,
                        scope_tag="rewire",
                        notes="Mandatory light points",
                    )
                )

            target_usb = Decimal("0")
            if "usb" in self.desc:
                target_usb = _extract_count_near(self.desc, "usb socket", default=Decimal("4"))
            elif self.bedrooms >= 4 and (
                self.prefers_chrome or self.is_mid_range or self.is_premium
            ):
                target_usb = Decimal("6")
            elif self.bedrooms >= 3 and (
                self.prefers_chrome or self.is_mid_range or self.is_premium
            ):
                target_usb = Decimal("4")
            current_usb = _quantity_of(reqs, concept="usb_socket")
            if current_usb < target_usb:
                attrs = {"usb": True}
                if brand:
                    attrs["brand"] = brand
                reqs.append(
                    _req(
                        "usb_socket",
                        "Switches & Sockets",
                        target_usb - current_usb,
                        attrs,
                        scope_tag="rewire",
                        notes="Mandatory USB sockets",
                    )
                )

            target_dimmers = Decimal("0")
            if "dimmer" in self.desc or "dimmable" in self.desc:
                target_dimmers = _extract_count_near(self.desc, "dimmer", default=Decimal("3"))
            elif self.bedrooms >= 3 and (
                self.is_mid_range or self.is_premium or "downlight" in self.desc
            ):
                target_dimmers = Decimal("3")
            current_dimmers = _quantity_of(reqs, concept="dimmer_switch")
            if current_dimmers < target_dimmers:
                attrs = {}
                if brand:
                    attrs["brand"] = brand
                reqs.append(
                    _req(
                        "dimmer_switch",
                        "Switches & Sockets",
                        target_dimmers - current_dimmers,
                        attrs,
                        scope_tag="rewire",
                        notes="Mandatory dimmer switches",
                    )
                )

        # Explicit socket/downlight counts for any non-rewire job (e.g.
        # "add 5 double sockets"). For full rewires the room-based targets
        # above take precedence.
        if not self.is_rewire:
            reqs = self._explicit_counts(reqs, brand)

        return reqs

    def _explicit_counts(
        self, reqs: list[BoQRequirement], brand: str | None
    ) -> list[BoQRequirement]:
        specified_sockets = _extract_count_near(self.desc, "socket")
        current_sockets = _quantity_of(reqs, concept="double_socket") + _quantity_of(
            reqs, concept="single_socket"
        )
        if specified_sockets > 0 and current_sockets != specified_sockets:
            reqs = [r for r in reqs if r.concept not in {"double_socket", "single_socket"}]
            attrs: dict[str, Any] = {"gang": 2, "usb": False}
            if self.prefers_chrome:
                attrs["finish"] = "chrome"
            if brand:
                attrs["brand"] = brand
            reqs.append(
                _req(
                    "double_socket",
                    "Switches & Sockets",
                    specified_sockets,
                    attrs,
                    scope_tag="explicit_count",
                    notes="Mandatory socket count",
                )
            )

        specified_downlights = max(
            _extract_count_near(self.desc, "downlight"),
            _extract_count_near(self.desc, "spotlight"),
            _extract_count_near(self.desc, "spot"),
        )
        if specified_downlights > 0:
            reqs = [r for r in reqs if r.concept != "downlight"]
            attrs = {"type": "downlight"}
            if "dimmable" in self.desc or "dimmer" in self.desc:
                attrs["dimmable"] = True
            reqs.append(
                _req(
                    "downlight",
                    "Lighting",
                    specified_downlights,
                    attrs,
                    scope_tag="explicit_count",
                    notes="Mandatory downlight count",
                )
            )

        if self.is_extension or self.is_garage:
            specified_batten = _extract_count_near(self.desc, "batten")
            if specified_batten > 0:
                reqs = [r for r in reqs if r.concept != "batten_light"]
                reqs.append(
                    _req(
                        "batten_light",
                        "Lighting",
                        specified_batten,
                        {"type": "batten"},
                        scope_tag="explicit_count",
                        notes="Mandatory batten count",
                    )
                )

        return reqs

    def _cooker_switch(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if (self.is_rewire or self.is_kitchen or self.is_extension) and not _has_concept(
            reqs, "cooker_switch"
        ):
            attrs: dict[str, Any] = {}
            if self.prefers_chrome:
                attrs["finish"] = "chrome"
            reqs.append(
                _req(
                    "cooker_switch",
                    "Switches & Sockets",
                    Decimal("1"),
                    attrs,
                    scope_tag="kitchen",
                    notes="Mandatory cooker switch",
                )
            )
        return reqs

    # Bed-count-driven cable metreage. Tuned against TradeCalcs 2025
    # benchmarks and the BS 7671 / NICEIC sample BoMs in the golden dataset.
    # Tuple is (1.5mm lighting metres, 2.5mm socket metres, 6mm cooker metres).
    _CABLE_METREAGE_BY_BEDS: ClassVar[dict[int, tuple[Decimal, Decimal, Decimal]]] = {
        1: (Decimal("50"), Decimal("80"), Decimal("15")),
        2: (Decimal("65"), Decimal("110"), Decimal("18")),
        3: (Decimal("90"), Decimal("150"), Decimal("22")),
        4: (Decimal("120"), Decimal("220"), Decimal("28")),
        5: (Decimal("140"), Decimal("250"), Decimal("30")),
    }

    def _scaled_cable_metreage(self) -> tuple[Decimal, Decimal, Decimal]:
        """Return (1.5mm, 2.5mm, 6mm) metres for the current property size.

        Falls back to the 3-bed default when bedrooms are unknown, which is
        the most common UK domestic case and avoids systematic under-quoting
        on vague descriptions like "rewire my house".
        """
        beds = int(self.bedrooms) if self.bedrooms else 3
        # Clamp into the table range.
        beds = max(1, min(beds, 5))
        if self.is_partial_rewire:
            # Partial rewires consume roughly half the cable of a full rewire.
            full = self._CABLE_METREAGE_BY_BEDS[beds]
            return (full[0] / 2, full[1] / 2, full[2])
        return self._CABLE_METREAGE_BY_BEDS[beds]

    def _cables(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if self.is_rewire or self.is_extension:
            lighting_m, socket_m, _ = self._scaled_cable_metreage()
            if not _has_concept(reqs, "lighting_cable_1_5mm"):
                reqs.append(
                    _req(
                        "lighting_cable_1_5mm",
                        "Cable",
                        lighting_m,
                        {"mm": "1.5", "twin": True},
                        scope_tag="rewire",
                        notes=(
                            f"Mandatory lighting cable for {int(self.bedrooms)}-bed property"
                            if self.bedrooms
                            else "Mandatory lighting cable (assumed 3-bed)"
                        ),
                    )
                )
            if not _has_concept(reqs, "socket_cable_2_5mm"):
                reqs.append(
                    _req(
                        "socket_cable_2_5mm",
                        "Cable",
                        socket_m,
                        {"mm": "2.5", "twin": True},
                        scope_tag="rewire",
                        notes=(
                            f"Mandatory socket cable for {int(self.bedrooms)}-bed property"
                            if self.bedrooms
                            else "Mandatory socket cable (assumed 3-bed)"
                        ),
                    )
                )

        if (
            self.is_rewire or self.is_kitchen or self.is_extension or self.is_garage
        ) and not _has_concept(reqs, "cooker_cable_6mm"):
            # Kitchen-only jobs typically need a shorter cooker run than full rewires.
            if self.is_kitchen and not self.is_rewire:
                cooker_qty = Decimal("15")
            elif self.is_rewire:
                _, _, cooker_qty = self._scaled_cable_metreage()
            else:
                cooker_qty = Decimal("20")
            reqs.append(
                _req(
                    "cooker_cable_6mm",
                    "Cable",
                    cooker_qty,
                    {"mm": "6", "twin": True},
                    scope_tag="power_circuit",
                    notes="Mandatory cooker/EV cable",
                )
            )

        # Non-rewire socket additions need a run of 2.5mm cable.
        socket_count = _quantity_of(reqs, concept="double_socket") + _quantity_of(
            reqs, concept="single_socket"
        )
        if (
            socket_count
            and not self.is_rewire
            and not self.is_extension
            and not _has_concept(reqs, "socket_cable_2_5mm")
        ):
            cable_qty = max(Decimal("20"), socket_count * Decimal("12"))
            if self.rooms:
                cable_qty = max(cable_qty, self.rooms * Decimal("20"))
            reqs.append(
                _req(
                    "socket_cable_2_5mm",
                    "Cable",
                    cable_qty,
                    {"mm": "2.5", "twin": True},
                    scope_tag="addition",
                    notes="Cable for new socket outlets",
                )
            )
        return reqs

    def _back_boxes(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        double_qty = _quantity_of(reqs, concept="double_socket")
        single_qty = _quantity_of(reqs, concept="single_socket")
        switch_qty = _quantity_of(
            reqs,
            concept="light_switch",
        ) + _quantity_of(reqs, concept="dimmer_switch")

        if self.is_rewire:
            if not _has_concept(reqs, "metal_back_box_1gang"):
                qty = max(Decimal("10"), self.rooms * Decimal("3") + self.bedrooms)
                reqs.append(
                    _req(
                        "metal_back_box_1gang",
                        "Wiring Accessories",
                        qty,
                        {"size": "1gang"},
                        scope_tag="rewire",
                        notes="Metal back boxes for rewire",
                    )
                )
            if not _has_concept(reqs, "metal_back_box_2gang"):
                qty = max(Decimal("5"), double_qty / Decimal("2"))
                reqs.append(
                    _req(
                        "metal_back_box_2gang",
                        "Wiring Accessories",
                        qty,
                        {"size": "2gang"},
                        scope_tag="rewire",
                        notes="Metal back boxes for rewire",
                    )
                )
            return reqs

        # Non-rewire additions: one back box per outlet/switch, rounded up.
        if double_qty and not _has_concept(reqs, "metal_back_box_2gang"):
            reqs.append(
                _req(
                    "metal_back_box_2gang",
                    "Wiring Accessories",
                    double_qty,
                    {"size": "2gang"},
                    scope_tag="addition",
                    notes="Back boxes for new double sockets",
                )
            )
        single_switch_qty = single_qty + switch_qty
        if single_switch_qty and not _has_concept(reqs, "metal_back_box_1gang"):
            reqs.append(
                _req(
                    "metal_back_box_1gang",
                    "Wiring Accessories",
                    single_switch_qty,
                    {"size": "1gang"},
                    scope_tag="addition",
                    notes="Back boxes for new single sockets/switches",
                )
            )
        return reqs

    def _fire_and_co(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if (
            not self.is_rewire
            and (self.is_kitchen or (self.is_extension and "kitchen" in self.desc))
            and not _has_concept(reqs, "heat_detector")
        ):
            reqs.append(
                _req(
                    "heat_detector",
                    "Security & Fire",
                    Decimal("1"),
                    {"type": "heat"},
                    scope_tag="kitchen",
                    notes="Mandatory kitchen heat detector",
                )
            )
            return reqs

        if not self.is_rewire:
            return reqs

        if self.is_partial_rewire:
            target_smoke = Decimal("1")
        else:
            target_smoke = max(Decimal("2"), self.bedrooms + Decimal("1"))
        if self.is_hmo:
            target_smoke = Decimal("6")
        current_smoke = _quantity_of(
            reqs,
            category="Security & Fire",
            predicate=lambda r: r.concept == "smoke_alarm",
        )
        if current_smoke < target_smoke:
            smoke_attrs: dict[str, Any] = {"type": "smoke", "mains": True}
            if self.prefers_aico:
                smoke_attrs["brand"] = "aico"
            reqs.append(
                _req(
                    "smoke_alarm",
                    "Security & Fire",
                    target_smoke - current_smoke,
                    smoke_attrs,
                    scope_tag="rewire",
                    notes="Mandatory smoke alarm",
                )
            )

        target_heat = Decimal("1") if self.bedrooms <= 2 else Decimal("2")
        current_heat = _quantity_of(
            reqs,
            category="Security & Fire",
            predicate=lambda r: r.concept == "heat_detector",
        )
        if current_heat < target_heat:
            heat_attrs: dict[str, Any] = {"type": "heat"}
            if self.prefers_aico:
                heat_attrs["brand"] = "aico"
            reqs.append(
                _req(
                    "heat_detector",
                    "Security & Fire",
                    target_heat - current_heat,
                    heat_attrs,
                    scope_tag="rewire",
                    notes="Mandatory heat detector",
                )
            )

        wants_co = (
            self.is_hmo
            or "carbon monoxide" in self.desc
            or "co alarm" in self.desc
            or (
                self.bedrooms >= 3
                and (self.is_mid_range or self.is_premium)
                and not self.is_partial_rewire
            )
        )
        if wants_co:
            co_target = Decimal("2") if self.is_hmo else Decimal("1")
            current_co = _quantity_of(
                reqs,
                category="Security & Fire",
                predicate=lambda r: r.concept == "carbon_monoxide_alarm",
            )
            if current_co < co_target:
                co_attrs: dict[str, Any] = {"type": "co"}
                if self.prefers_aico:
                    co_attrs["brand"] = "aico"
                reqs.append(
                    _req(
                        "carbon_monoxide_alarm",
                        "Security & Fire",
                        co_target - current_co,
                        co_attrs,
                        scope_tag="rewire",
                        notes="Mandatory CO alarm",
                    )
                )

        if self.is_hmo:
            current_emergency = _quantity_of(
                reqs,
                category="Lighting",
                predicate=lambda r: r.concept == "emergency_light",
            )
            if current_emergency < 3:
                reqs.append(
                    _req(
                        "emergency_light",
                        "Lighting",
                        Decimal("3") - current_emergency,
                        {"type": "emergency"},
                        scope_tag="hmo",
                        notes="Mandatory emergency lighting",
                    )
                )

        return reqs

    def _ev_circuit(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if not self.is_ev:
            return reqs

        if not _has_concept(reqs, "type_a_rcd"):
            reqs.append(
                _req(
                    "type_a_rcd",
                    "Circuit Protection",
                    Decimal("1"),
                    {"type_a": True, "rcd": True},
                    scope_tag="ev",
                    notes="Mandatory Type A RCD for EV",
                )
            )
        if not _has_concept(reqs, "mcb"):
            reqs.append(
                _req(
                    "mcb",
                    "Circuit Protection",
                    Decimal("1"),
                    {"type": "mcb", "amperage": "32"},
                    scope_tag="ev",
                    notes="Dedicated 32A MCB for EV circuit",
                )
            )
        if not _has_concept(reqs, "swa_cable"):
            reqs.append(
                _req(
                    "swa_cable",
                    "Cable",
                    Decimal("20"),
                    {"swa": True, "mm": "6"},
                    scope_tag="ev",
                    notes="Mandatory SWA for EV",
                )
            )
        if not _has_concept(reqs, "weatherproof_isolator"):
            reqs.append(
                _req(
                    "weatherproof_isolator",
                    "Switches & Sockets",
                    Decimal("1"),
                    {"outdoor": True, "isolator": True},
                    scope_tag="ev",
                    notes="Mandatory isolator for EV",
                )
            )
        if not _has_concept(reqs, "earth_rod"):
            reqs.append(
                _req(
                    "earth_rod",
                    "Wiring Accessories",
                    Decimal("1"),
                    {"earth_rod": True},
                    scope_tag="ev",
                    notes="Mandatory earth rod for EV",
                )
            )
        if not _has_concept(reqs, "swa_gland"):
            reqs.append(
                _req(
                    "swa_gland",
                    "Wiring Accessories",
                    Decimal("2"),
                    {"swa": True, "gland": True},
                    scope_tag="ev",
                    notes="Mandatory SWA gland pack for EV",
                )
            )
        return reqs

    def _garage(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if not self.is_garage:
            return reqs

        if not _has_concept(reqs, "garage_consumer_unit"):
            reqs.append(
                _req(
                    "garage_consumer_unit",
                    "Consumer Units",
                    Decimal("1"),
                    {"garage": True},
                    scope_tag="garage",
                    notes="Mandatory garage CU",
                )
            )
        if not _has_concept(reqs, "swa_cable"):
            reqs.append(
                _req(
                    "swa_cable",
                    "Cable",
                    Decimal("20"),
                    {"swa": True},
                    scope_tag="garage",
                    notes="Mandatory SWA for garage",
                )
            )
        if not _has_concept(reqs, "weatherproof_isolator"):
            reqs.append(
                _req(
                    "weatherproof_isolator",
                    "Switches & Sockets",
                    Decimal("1"),
                    {"outdoor": True, "isolator": True},
                    scope_tag="garage",
                    notes="Mandatory isolator for garage",
                )
            )
        return reqs

    def _outdoor_sockets(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        wants_outdoor = (
            "outdoor socket" in self.desc
            or "outside socket" in self.desc
            or "garden" in self.desc
            or ("front" in self.desc and "back" in self.desc and "socket" in self.desc)
        )
        if not wants_outdoor:
            return reqs

        current_outdoor = _quantity_of(
            reqs,
            concept="outdoor_socket",
        )
        target_outdoor = Decimal("2")
        if current_outdoor < target_outdoor:
            reqs.append(
                _req(
                    "outdoor_socket",
                    "Switches & Sockets",
                    target_outdoor - current_outdoor,
                    {"outdoor": True, "weatherproof": True},
                    scope_tag="outdoor",
                    notes="Mandatory weatherproof outdoor socket",
                )
            )
        if not _has_concept(reqs, "swa_cable"):
            reqs.append(
                _req(
                    "swa_cable",
                    "Cable",
                    Decimal("25"),
                    {"swa": True},
                    scope_tag="outdoor",
                    notes="Mandatory SWA for outdoor circuit",
                )
            )
        return reqs

    def _tt_earthing(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if not (re.search(r"\btt\b", self.desc) or "victorian" in self.desc):
            return reqs

        if not _has_concept(reqs, "earth_rod"):
            reqs.append(
                _req(
                    "earth_rod",
                    "Wiring Accessories",
                    Decimal("1"),
                    {"earth_rod": True},
                    scope_tag="tt",
                    notes="Mandatory earth rod for TT",
                )
            )
        if not _has_concept(reqs, "bonding_clamp"):
            reqs.append(
                _req(
                    "bonding_clamp",
                    "Wiring Accessories",
                    Decimal("2"),
                    {"bonding": True},
                    scope_tag="tt",
                    notes="Mandatory bonding clamps",
                )
            )
        if not _has_concept(reqs, "supplementary_bonding_cable"):
            reqs.append(
                _req(
                    "supplementary_bonding_cable",
                    "Cable",
                    Decimal("10"),
                    {"bonding": True},
                    scope_tag="tt",
                    notes="Mandatory supplementary bonding",
                )
            )
        return reqs

    def _ufh(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if not self.is_ufh:
            return reqs

        if not _has_concept(reqs, "underfloor_heating_mat"):
            reqs.append(
                _req(
                    "underfloor_heating_mat",
                    "Heating & Cooling",
                    Decimal("2"),
                    {"ufh": True},
                    scope_tag="ufh",
                    notes="Mandatory UFH mat",
                )
            )
        if not _has_concept(reqs, "thermostat"):
            reqs.append(
                _req(
                    "thermostat",
                    "Heating & Cooling",
                    Decimal("2"),
                    {"ufh": True},
                    scope_tag="ufh",
                    notes="Mandatory UFH thermostat",
                )
            )
        if not _quantity_of(reqs, category="Circuit Protection"):
            reqs.append(
                _req(
                    "mcb",
                    "Circuit Protection",
                    Decimal("2"),
                    {"type": "mcb"},
                    scope_tag="ufh",
                    notes="Mandatory UFH circuit protection",
                )
            )
        if not _has_concept(reqs, "ufh_cable_4mm"):
            reqs.append(
                _req(
                    "ufh_cable_4mm",
                    "Cable",
                    Decimal("25"),
                    {"mm": "4", "twin": True},
                    scope_tag="ufh",
                    notes="Mandatory 4mm UFH cable",
                )
            )
        return reqs

    def _under_cabinet(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if not (
            "under cabinet" in self.desc
            or "under-cabinet" in self.desc
            or "under cupboard" in self.desc
        ):
            return reqs

        if not _has_concept(reqs, "under_cabinet_lighting"):
            qty = _extract_count_near(self.desc, "under cabinet", default=Decimal("3"))
            reqs.append(
                _req(
                    "under_cabinet_lighting",
                    "Lighting",
                    qty,
                    {"under_cabinet": True},
                    scope_tag="kitchen",
                    notes="Mandatory under-cabinet lighting",
                )
            )
        if not _has_concept(reqs, "led_driver"):
            reqs.append(
                _req(
                    "led_driver",
                    "Lighting",
                    Decimal("1"),
                    {"driver": True},
                    scope_tag="kitchen",
                    notes="Mandatory LED driver",
                )
            )
        return reqs

    def _ambiguous_defaults(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        if not self.is_ambiguous or self.is_rewire:
            return reqs

        current_sockets = _quantity_of(reqs, concept="double_socket") + _quantity_of(
            reqs, concept="single_socket"
        )
        if current_sockets < 10:
            reqs.append(
                _req(
                    "double_socket",
                    "Switches & Sockets",
                    Decimal("10") - current_sockets,
                    {"gang": 2},
                    scope_tag="ambiguous",
                    notes="Default sockets for ambiguous scope",
                )
            )

        current_lights = _quantity_of(
            reqs,
            category="Lighting",
            predicate=lambda r: r.concept in {"ceiling_light", "downlight", "batten_light"},
        )
        if current_lights < 6:
            reqs.append(
                _req(
                    "ceiling_light",
                    "Lighting",
                    Decimal("6") - current_lights,
                    {"type": "ceiling"},
                    scope_tag="ambiguous",
                    notes="Default lights for ambiguous scope",
                )
            )
        return reqs

    def _dedupe(self, reqs: list[BoQRequirement]) -> list[BoQRequirement]:
        """Merge duplicate requirements by id, summing quantities."""
        merged: dict[str, BoQRequirement] = {}
        for req in reqs:
            if req.id in merged:
                existing = merged[req.id]
                merged[req.id] = existing.model_copy(
                    update={"quantity": existing.quantity + req.quantity}
                )
            else:
                merged[req.id] = req

        # Prune zero/negative quantities.
        return [r for r in merged.values() if r.quantity > 0]


def generate_requirements(
    description: str,
    property_type: str | None = None,
    generated: dict[str, Any] | None = None,
    design: dict[str, Any] | None = None,
) -> list[BoQRequirement]:
    """Convenience entry point used by the engine."""
    design_payload = design if design is not None else generated
    return RequirementEngine(description, property_type).generate(design_payload)
