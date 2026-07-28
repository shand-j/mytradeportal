"""Catalogue resolution: map generic BoQ requirements to real supplier items.

The resolver is connector-based so that future supplier integrations can be
plugged in without changing the engine.  For the MVP we implement a
Screwfix-first connector backed by the `domestic_pipeline` source.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from ocerp.retrieval import search_cost_items
from ocerp.services.boq_models import BoQRequirement, ResolvedCostItem


def _norm(text: str | None) -> str:
    """Normalise text for matching: lowercase, collapse whitespace, drop superscripts."""
    text = (text or "").lower().strip().replace("²", "").replace("³", "")
    return re.sub(r"\s+", " ", text)


def _tokenize(text: str) -> list[str]:
    """Return meaningful tokens from a requirement or description."""
    normalized = _norm(text)
    # Split on non-alphanumeric, but keep decimal cable sizes like "1.5mm".
    tokens = re.findall(r"[0-9]+(?:\.[0-9]+)?[a-z]+|[a-z0-9]+", normalized)
    return [t for t in tokens if len(t) > 1 or t.isdigit()]


def _build_query(requirement: BoQRequirement) -> str:
    """Build a human/vector search query from a requirement."""
    parts = [requirement.concept.replace("_", " ")]
    for key, value in requirement.attributes.items():
        if value is None or value is False:
            continue
        if value is True:
            parts.append(key.replace("_", " "))
        else:
            parts.append(str(value))
    return " ".join(parts)


def _requirement_tokens(requirement: BoQRequirement) -> set[str]:
    """Return the keyword tokens we expect a match to contain."""
    query = _build_query(requirement)
    tokens = set(_tokenize(query))
    # Add bare attribute values that may have been missed (e.g. "usb").
    for value in requirement.attributes.values():
        if isinstance(value, str):
            tokens.update(_tokenize(value))
        elif isinstance(value, int | float | Decimal):
            tokens.add(str(value))
    return tokens


def _keyword_overlap_score(requirement: BoQRequirement, item: dict[str, Any]) -> float:
    """Return the fraction of requirement tokens present in the item description."""
    req_tokens = _requirement_tokens(requirement)
    if not req_tokens:
        return 1.0
    desc = _norm(item.get("description", ""))
    item_tokens = set(_tokenize(desc))
    if not item_tokens:
        return 0.0
    overlap = len(req_tokens & item_tokens)
    return overlap / len(req_tokens)


def _brand_match(requirement: BoQRequirement, item: dict[str, Any]) -> bool:
    """True if the item brand satisfies an explicit brand attribute.

    The brand is checked against the structured ``brand`` field first, then
    against the item description using word boundaries.  This lets us enforce
    requests like "MK" or "Scolmore" even when supplier data only carries the
    brand in the description.
    """
    brand = requirement.attributes.get("brand")
    if not brand:
        return True
    brand_norm = brand.lower()
    item_brand = _norm(item.get("brand"))
    if brand_norm in item_brand:
        return True
    desc = _norm(item.get("description", ""))
    return bool(re.search(rf"\b{re.escape(brand_norm)}\b", desc))


# Categories where the brand drives physical/electrical compatibility (a
# non-Hager MCB does not fit a Hager consumer unit; an Aico smoke alarm
# must be interlinked with same-brand units). For these we keep brand as a
# hard reject in scoring.
_BRAND_CRITICAL_CATEGORIES: frozenset[str] = frozenset(
    {"Consumer Units", "Circuit Protection", "Security & Fire"}
)


def _brand_score(requirement: BoQRequirement, item: dict[str, Any]) -> float:
    """Return a multiplier that combines brand strictness with category sensitivity.

    * No brand requested → 1.0 (neutral).
    * Brand matches → 1.0.
    * Brand mismatches AND category is compatibility-critical → 0.0 (reject).
    * Brand mismatches in a commodity category → 0.5 (soft penalty).

    This lets a "brushed steel MK" socket request resolve to a British General
    Nexus Metal brushed steel SKU when MK genuinely doesn't make a
    brushed-steel Logic Plus — finish wins (1.5x) x brand miss (0.5x) = 0.75,
    which beats MK Logic Plus White at brand match (1.0x) x finish miss
    (0.4x) = 0.4.
    """
    if not requirement.attributes.get("brand"):
        return 1.0
    if _brand_match(requirement, item):
        return 1.0
    category = (requirement.category or "").strip()
    if category in _BRAND_CRITICAL_CATEGORIES:
        return 0.0
    return 0.5


# Finish synonyms — many catalogue descriptions use "brushed steel" or
# "stainless steel" interchangeably, so any of these tokens satisfies a
# ``finish=chrome`` requirement.
_FINISH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "chrome": ("chrome", "brushed steel", "brushed chrome", "stainless steel", "satin chrome"),
    "black": ("black",),
    "white": ("white",),
    "brass": ("brass",),
    "nickel": ("nickel",),
}


def _finish_score(requirement: BoQRequirement, item: dict[str, Any]) -> float:
    """Return a multiplier that rewards finish matches and softly penalises clashes.

    When the requirement carries no ``finish`` attribute this is a neutral 1.0.
    For a chrome/brushed-steel ask we boost matching items by 50% so they
    decisively outrank generic white plates of the same brand, and softly
    penalise (0.4x) items whose description explicitly states a different
    finish. The soft penalty matters: zeroing them out would force the
    resolver to fall back to wildly inappropriate alternatives (e.g. an IP66
    outdoor socket) when the Screwfix catalogue has no brushed-steel SKU.
    """
    finish = requirement.attributes.get("finish")
    if not finish:
        return 1.0
    finish = str(finish).lower()
    synonyms = _FINISH_SYNONYMS.get(finish, (finish,))
    desc = _norm(item.get("description", ""))
    if any(syn in desc for syn in synonyms):
        return 1.5
    # Soft penalty for explicit-but-different finishes. Word-boundary match so
    # "white" doesn't accidentally fire on "switched".
    opposites = {"white", "black", "brass", "nickel"} - {finish}
    tokens = set(re.findall(r"[a-z]+", desc))
    if opposites & tokens:
        return 0.4
    # No finish mentioned in description → neutral (matches the keyword/vector
    # scoring on the rest of the description).
    return 1.0


# For a handful of safety-critical or easily-confused concepts we require at
# least one keyword from each group to be present in the description.  This
# prevents a generic vector match from returning the wrong item (e.g. an HDMI
# cable for an SWA-cable requirement).
_ESSENTIAL_GROUPS: dict[str, list[list[str]]] = {
    "type_a_rcd": [["type a", "type-a"], ["rcd"]],
    "swa_cable": [["swa", "armoured"]],
    "weatherproof_isolator": [["isolator"]],
    "earth_rod": [["earth rod"]],
    "bonding_clamp": [["bonding clamp", "equipotential", "main bonding"]],
    "supplementary_bonding_cable": [["supplementary bonding", "bonding"]],
    "smoke_alarm": [["smoke"]],
    "heat_detector": [["heat"]],
    "carbon_monoxide_alarm": [["carbon monoxide", "co alarm"]],
    "emergency_light": [["emergency", "bulkhead"]],
    "mcb": [["mcb", "miniature circuit breaker"]],
    "rcbo": [["rcbo"]],
    "loft_rcbo": [["rcbo"]],
    "garage_rcbo": [["rcbo"]],
    "afdd": [["afdd"]],
    "consumer_unit": [["consumer unit", "fuse box", "fusebox", "distribution board"]],
    "main_switch": [["main switch", "fused switch"]],
    "spd_module": [["spd", "surge"]],
    "garage_consumer_unit": [["garage"]],
    "double_socket": [["socket"], ["2-gang", "2 gang", "double"]],
    "single_socket": [["socket"], ["1-gang", "1 gang", "single"]],
    "usb_socket": [["usb"]],
    "dimmer_switch": [["dimmer"]],
    "cooker_switch": [["cooker", "45a"]],
    "downlight": [["downlight", "spotlight", "down light", "spot light"]],
    "ceiling_light": [["ceiling", "pendant", "rose"]],
    "batten_light": [["batten"]],
    "under_cabinet_lighting": [["under cabinet", "under-cabinet"]],
    "metal_back_box_1gang": [["back box", "backbox", "pattress"]],
    "metal_back_box_2gang": [["back box", "backbox", "pattress"]],
    "led_driver": [["driver"]],
    "underfloor_heating_mat": [["underfloor heating"]],
    "thermostat": [["thermostat"]],
    "outdoor_socket": [
        ["outdoor", "weatherproof", "ip66", "ip55", "ip54", "masterseal"],
        ["socket", "switched"],
    ],
    "lighting_cable_1_5mm": [["1.5mm"], ["twin"]],
    "socket_cable_2_5mm": [["2.5mm"], ["twin"]],
    "cooker_cable_6mm": [["6mm"], ["twin"]],
    "ufh_cable_4mm": [["4mm"], ["twin"]],
}


def _essential_groups(requirement: BoQRequirement) -> list[list[str]] | None:
    """Return hard keyword groups for a requirement, if any are defined."""
    return _ESSENTIAL_GROUPS.get(requirement.concept)


def _keyword_present(desc: str, keyword: str) -> bool:
    """Check for a keyword, using word boundaries for single tokens."""
    if " " in keyword or "-" in keyword:
        # Multi-word or hyphenated phrases are matched as literal substrings.
        return keyword in desc
    return bool(re.search(rf"\b{re.escape(keyword)}\b", desc))


def _meets_hard_requirements(requirement: BoQRequirement, item: dict[str, Any]) -> bool:
    """Return True when the item satisfies concept-level keyword requirements."""
    groups = _essential_groups(requirement)
    if not groups:
        return True
    desc = _norm(item.get("description", ""))
    return all(any(_keyword_present(desc, keyword) for keyword in group) for group in groups)


def _hard_reject(requirement: BoQRequirement, item: dict[str, Any]) -> bool:
    """Reject obviously wrong catalogue matches for a given concept."""
    desc = _norm(item.get("description", ""))
    concept = requirement.concept

    if concept == "consumer_unit" and any(bad in desc for bad in ("blank", "blank plate")):
        return True

    if concept == "swa_cable" and any(
        bad in desc
        for bad in (
            "hdmi",
            "ethernet",
            "cat 5",
            "cat5",
            "cctv",
            "extension lead",
            "extension cable",
        )
    ):
        return True

    if concept in {"bonding_clamp", "main_equipotential_bonding"} and "crimp" in desc:
        return True

    if concept in {"double_socket", "single_socket", "socket_outlet"}:
        if any(
            bad in desc
            for bad in ("rj45", "ethernet", "cat 5", "cat5", "cat 6", "cat6", "data", "usb")
        ):
            return True
        # Indoor sockets must not resolve to a weatherproof / outdoor SKU.
        # We have a separate `outdoor_socket` requirement when the
        # description asks for outdoor coverage.
        if requirement.attributes.get("outdoor") is not True and any(
            bad in desc
            for bad in (
                "weatherproof",
                "ip66",
                "ip55",
                "ip54",
                "ip65",
                "masterseal",
                "outdoor",
            )
        ):
            return True

    # Mirror image: an "indoor"-only switch must not pick a weatherproof box.
    if (
        concept in {"dimmer_switch", "light_switch", "cooker_switch"}
        and requirement.attributes.get("outdoor") is not True
        and any(
            bad in desc
            for bad in ("weatherproof", "ip66", "ip55", "ip54", "ip65", "masterseal", "outdoor")
        )
    ):
        return True

    if concept == "under_cabinet_lighting" and (" pack" in desc or "pack of" in desc):
        # Multi-packs make quantity accounting wrong (a "4 pack" is one SKU).
        return True

    if concept in {"metal_back_box_1gang", "metal_back_box_2gang", "back_box", "pattress"} and (
        "junction" in desc or " adaptable" in desc or "inline" in desc
    ):
        return True

    return any(
        term in desc
        for term in ("chocbox", "choc box", "connector box", "connector block", "terminal block")
    )


def _score_candidate(requirement: BoQRequirement, item: dict[str, Any]) -> float:
    """Score a catalogue candidate for a requirement.

    Combines keyword overlap (dominant) with the vector similarity score that
    Qdrant returned.  Brand mismatches are heavily penalised; finish
    mismatches downweight or eliminate the candidate via
    :func:`_finish_score` so a "brushed steel" request never resolves to a
    plain white plate when a real brushed-steel option exists.
    """
    keyword_score = _keyword_overlap_score(requirement, item)
    vector_score = float(item.get("score") or 0.0)
    brand_multiplier = _brand_score(requirement, item)
    if brand_multiplier == 0.0:
        return 0.0
    finish_multiplier = _finish_score(requirement, item)
    if finish_multiplier == 0.0:
        return 0.0
    # Normalise vector score roughly into [0, 1] (cosine from Qdrant is already
    # in that range, but smaller embeddings can return modest absolute values).
    normalised_vector = min(max(vector_score, 0.0), 1.0)
    base = (keyword_score * 0.7) + (normalised_vector * 0.3)
    return base * brand_multiplier * finish_multiplier


def _extract_pack_length_m(description: str) -> int | None:
    """Return the cable pack length in metres, if the description specifies one."""
    desc = _norm(description)
    matches = re.findall(r"\b(\d+)\s*(?:m|metre)\b", desc)
    if not matches:
        return None
    return max(int(m) for m in matches)


def _select_cable_candidate(
    requirement: BoQRequirement,
    scored_items: list[tuple[dict[str, Any], float]],
) -> tuple[dict[str, Any], BoQRequirement] | None:
    """Pick the smallest cable pack that covers the required length.

    If no pack is long enough, fall back to a per-metre item.  The requirement
    quantity is updated to the actual pack length (or total length when multiple
    packs are needed).
    """
    req_qty = float(requirement.quantity)
    packs: list[tuple[dict[str, Any], float, int]] = []
    per_metre: list[tuple[dict[str, Any], float]] = []

    for item, score in scored_items:
        length = _extract_pack_length_m(item.get("description", ""))
        if length:
            packs.append((item, score, length))
        else:
            per_metre.append((item, score))

    # Prefer the smallest pack that is >= required length.
    suitable = [(item, score, length) for item, score, length in packs if length >= req_qty]
    if suitable:
        suitable.sort(key=lambda x: (x[2], -x[1]))
        item, _score, length = suitable[0]
        packs_needed = math.ceil(req_qty / length)
        total_length = packs_needed * length
        updated_notes = f"{requirement.notes or ''} Pack size {length}m.".strip()
        updated = requirement.model_copy(
            update={"quantity": Decimal(str(total_length)), "notes": updated_notes}
        )
        return item, updated

    # No pack is long enough: prefer a plain per-metre cable.
    if per_metre:
        per_metre.sort(key=lambda x: x[1], reverse=True)
        return per_metre[0][0], requirement

    # Fallback to the longest available pack — and BUY ENOUGH of them.
    # Previously this returned a single pack regardless of the requirement,
    # so a 220m run for a 4-bed rewire was being satisfied with one 100m
    # drum, massively under-quoting the materials. We now multiply by the
    # number of packs needed to fully cover the metreage.
    if packs:
        packs.sort(key=lambda x: (x[2], x[1]), reverse=True)
        item, _score, length = packs[0]
        packs_needed = max(1, math.ceil(req_qty / length))
        total_length = packs_needed * length
        updated_notes = (
            f"{requirement.notes or ''} {packs_needed}x {length}m pack (largest available)."
        ).strip()
        updated = requirement.model_copy(
            update={"quantity": Decimal(str(total_length)), "notes": updated_notes}
        )
        return item, updated

    return None


class SupplierConnector(ABC):
    """Abstract connector for searching a supplier/source catalogue."""

    name: str

    @abstractmethod
    async def search(
        self,
        requirement: BoQRequirement,
        trade: str,
        region: str,
    ) -> list[dict[str, Any]]:
        """Return candidate cost items for the requirement."""
        ...


class SourceConnector(SupplierConnector):
    """Generic connector backed by a single `source` value in Qdrant."""

    def __init__(self, source: str, top_k: int = 20):
        self.name = source
        self.source = source
        self.top_k = top_k

    async def search(
        self,
        requirement: BoQRequirement,
        trade: str,
        region: str,
    ) -> list[dict[str, Any]]:
        query = _build_query(requirement)
        return await search_cost_items(
            query=query,
            trade=trade,
            region=region,
            sources=[self.source],
            category=requirement.category,
            top_k=self.top_k,
        )


class CatalogueResolver:
    """Resolve a list of BoQRequirements to real catalogue items.

    Resolution order:
        1. Primary supplier connector (Screwfix / domestic_pipeline).
        2. Unresolved requirements emit a warning.
    """

    def __init__(
        self,
        primary: SupplierConnector | None = None,
        min_score: float = 0.15,
        trade: str = "electrical",
        region: str = "UK",
    ):
        self.primary = primary or SourceConnector("domestic_pipeline")
        self.min_score = min_score
        self.trade = trade
        self.region = region
        self._cache: dict[str, ResolvedCostItem | None] = {}
        self._warnings: list[str] = []

    def _any_brand_match(
        self, requirement: BoQRequirement, candidates: list[dict[str, Any]]
    ) -> bool:
        """Return True if at least one candidate satisfies the brand constraint."""
        return any(
            _brand_match(requirement, item)
            and _meets_hard_requirements(requirement, item)
            and not _hard_reject(requirement, item)
            for item in candidates
        )

    async def resolve_one(self, requirement: BoQRequirement) -> ResolvedCostItem | None:
        """Resolve a single requirement, using the in-request cache."""
        if requirement.id in self._cache:
            return self._cache[requirement.id]

        result = await self._resolve(requirement)
        self._cache[requirement.id] = result
        return result

    async def _resolve(self, requirement: BoQRequirement) -> ResolvedCostItem | None:
        requested_brand = requirement.attributes.get("brand")
        if requested_brand:
            primary_candidates = await self.primary.search(requirement, self.trade, self.region)
            if not self._any_brand_match(requirement, primary_candidates):
                self._warnings.append(
                    f"Brand {requested_brand!r} unavailable for {requirement.concept}; "
                    "falling back to generic alternatives."
                )
                requirement = requirement.model_copy(
                    update={
                        "attributes": {
                            **requirement.attributes,
                            "brand": None,
                        },
                        "notes": (
                            f"{requirement.notes or ''} Brand {requested_brand!r} unavailable; "
                            "generic alternative used."
                        ).strip(),
                    }
                )

        primary_candidates = await self.primary.search(requirement, self.trade, self.region)
        primary_choice = self._pick_best(requirement, primary_candidates)
        if primary_choice is not None:
            item, updated_requirement = primary_choice
            return ResolvedCostItem(
                requirement=updated_requirement,
                cost_item=item,
                resolution_source=self.primary.name,
                score=_score_candidate(updated_requirement, item),
            )

        return None

    def _pick_best(
        self,
        requirement: BoQRequirement,
        candidates: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], BoQRequirement] | None:
        if not candidates:
            return None
        scored = [
            (item, _score_candidate(requirement, item))
            for item in candidates
            if _meets_hard_requirements(requirement, item)
            and not _hard_reject(requirement, item)
            and _score_candidate(requirement, item) > 0
        ]
        if not scored:
            return None

        if requirement.category == "Cable":
            cable_choice = _select_cable_candidate(requirement, scored)
            if cable_choice is not None:
                item, updated_requirement = cable_choice
                if _score_candidate(updated_requirement, item) >= self.min_score:
                    return item, updated_requirement

        scored.sort(key=lambda x: x[1], reverse=True)
        best, score = scored[0]
        if score < self.min_score:
            return None
        return best, requirement

    async def resolve(
        self,
        requirements: list[BoQRequirement],
    ) -> tuple[list[ResolvedCostItem], list[str]]:
        """Resolve many requirements and return resolved items plus warnings."""
        self._warnings = []
        resolved: list[ResolvedCostItem] = []
        warnings: list[str] = []
        for requirement in requirements:
            item = await self.resolve_one(requirement)
            if item is None:
                warnings.append(
                    f"Could not resolve requirement {requirement.id!r} "
                    f"({requirement.concept}) to any catalogue item."
                )
                continue
            resolved.append(item)
        return resolved, self._warnings + warnings
