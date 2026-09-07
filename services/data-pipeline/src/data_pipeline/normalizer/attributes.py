"""Attribute extraction for cost items and job queries.

The embedder can't distinguish semantic siblings that are functionally
opposite (smoke alarm vs burglar alarm, SWA vs extension reel). Extracting
structured attributes from product names and appending them to both the
Qdrant payload and the embedded description gives retrieval a way to filter
by intent, and lets the LLM see disambiguating tags in the prompt.

Extractors are deliberately conservative: when in doubt, return an empty dict
rather than a wrong tag. A missing attribute is safer than a lying one because
retrieval only filters when the query intent carries the same attribute.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from data_pipeline.normalizer.unified_product import ProductCategory, UnifiedProduct


def _norm(text: str | None) -> str:
    """Lowercase + collapse whitespace so keyword matches are order-agnostic."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _extract_alarm(text: str) -> dict[str, Any]:
    """Fire vs intruder disambiguation is the highest-impact split.

    A CCTV camera and a smoke alarm both live under Screwfix's "Security &
    Fire" category and cluster together in embedding space; the ``purpose``
    tag alone fixes most smoke-alarm retrieval failures.
    """
    attrs: dict[str, Any] = {}

    fire_hits = any(
        kw in text
        for kw in (
            "smoke alarm",
            "heat alarm",
            "smoke detector",
            "heat detector",
            "co alarm",
            "co detector",
            "carbon monoxide",
            "fire alarm",
            "aico",
            "kidde",
        )
    )
    intruder_hits = any(
        kw in text
        for kw in (
            "burglar",
            "intruder",
            "cctv",
            "pir",
            "motion sensor",
            "door contact",
            "keypad",
            "siren",
            "camera",
            "doorbell camera",
        )
    )
    co_hits = "carbon monoxide" in text or " co " in f" {text} " or "co alarm" in text
    smoke_hits = "smoke" in text
    heat_hits = "heat alarm" in text or "heat detector" in text

    if fire_hits and not intruder_hits:
        attrs["alarm_purpose"] = "fire"
    elif intruder_hits and not fire_hits:
        attrs["alarm_purpose"] = "intruder"

    if attrs.get("alarm_purpose") == "fire":
        if co_hits:
            attrs["alarm_type"] = "co"
        elif heat_hits and not smoke_hits:
            attrs["alarm_type"] = "heat"
        elif smoke_hits and heat_hits:
            attrs["alarm_type"] = "combined"
        elif smoke_hits:
            attrs["alarm_type"] = "smoke"
        if "interlink" in text or "radiolink" in text or "mesh" in text:
            attrs["alarm_interconnect"] = "interlinked"
        if "mains" in text or "230v" in text or "240v" in text:
            attrs["alarm_power"] = "mains"
        elif "battery" in text:
            attrs["alarm_power"] = "battery"

    return attrs


def _extract_cable(text: str) -> dict[str, Any]:
    """SWA vs extension reel is the second diagnosed failure mode."""
    attrs: dict[str, Any] = {}

    swa_hit = bool(re.search(r"\bswa\b|steel wire armour|armoured", text))
    if swa_hit:
        attrs["cable_type"] = "swa"
    elif (
        "6242y" in text
        or "twin & earth" in text
        or "twin and earth" in text
        or re.search(r"\bt&e\b", text)
    ):
        attrs["cable_type"] = "twin_earth"
    elif "6491x" in text or ("singles" in text and "cable" in text):
        attrs["cable_type"] = "singles"
    elif "hi-tuff" in text or "hi tuff" in text or "3183y" in text:
        attrs["cable_type"] = "hi_tuff"
    elif "flex" in text and "cable" in text:
        attrs["cable_type"] = "flex"
    elif "extension" in text and ("reel" in text or "lead" in text):
        attrs["cable_type"] = "extension_reel"
    elif "cat5" in text or "cat6" in text or "cat7" in text or "network cable" in text:
        attrs["cable_type"] = "data"
    elif "alarm cable" in text or "signal cable" in text:
        attrs["cable_type"] = "alarm_signal"

    csa_match = re.search(r"(\d+(?:\.\d+)?)\s*mm²|(\d+(?:\.\d+)?)\s*mm2", text)
    if csa_match:
        with contextlib.suppress(ValueError):
            attrs["cable_csa_mm2"] = float(csa_match.group(1) or csa_match.group(2))

    cores_match = re.search(r"(\d)\s*-?\s*core", text)
    if cores_match:
        attrs["cable_cores"] = int(cores_match.group(1))

    return attrs


def _extract_consumer_unit(text: str) -> dict[str, Any]:
    """Ways + type — the LLM cares about capacity and RCD arrangement."""
    attrs: dict[str, Any] = {}

    ways_match = re.search(r"(\d+)\s*[-]?\s*way", text)
    if ways_match:
        attrs["cu_ways"] = int(ways_match.group(1))

    if "dual rcd" in text or "dual-rcd" in text:
        attrs["cu_type"] = "dual_rcd"
    elif "high integrity" in text or "high-integrity" in text:
        attrs["cu_type"] = "high_integrity"
    elif "main switch" in text or "main-switch" in text:
        attrs["cu_type"] = "main_switch"
    elif "surge" in text and ("consumer unit" in text or "distribution" in text):
        attrs["cu_type"] = "surge_protected"

    ip_match = re.search(r"ip\s*(\d{2})", text)
    if ip_match:
        attrs["ip_rating"] = f"IP{ip_match.group(1)}"

    return attrs


_PROTECTION_KEYWORDS = {
    "rcbo": "rcbo",
    "rcd": "rcd",
    "mcb": "mcb",
    "spd": "spd",
    "surge protection device": "spd",
    "surge protector": "spd",
    "isolator": "isolator",
}


def _extract_protection(text: str) -> dict[str, Any]:
    """MCB/RCBO/RCD — rating + curve are the LLM's picking criteria."""
    attrs: dict[str, Any] = {}

    for keyword, tag in _PROTECTION_KEYWORDS.items():
        if keyword in text:
            attrs["protection_type"] = tag
            break

    rating_match = re.search(r"(\d+)\s*a\b", text)
    if rating_match:
        rating = int(rating_match.group(1))
        # Sanity: domestic MCBs are 6-100A. Anything outside that is likely a
        # cable csa or product code, not a current rating.
        if 6 <= rating <= 100:
            attrs["rating_A"] = rating

    curve_match = re.search(r"type\s*([bcd])\b|curve\s*([bcd])\b", text)
    if curve_match:
        attrs["curve"] = (curve_match.group(1) or curve_match.group(2)).upper()

    poles_match = re.search(r"(\d)\s*[-]?\s*pole|\bsp\b|\bdp\b|\btp\b|\b4p\b", text)
    if poles_match:
        m = poles_match.group(0)
        if "sp" in m:
            attrs["poles"] = 1
        elif "dp" in m:
            attrs["poles"] = 2
        elif "tp" in m:
            attrs["poles"] = 3
        elif "4p" in m:
            attrs["poles"] = 4
        elif poles_match.group(1):
            attrs["poles"] = int(poles_match.group(1))

    return attrs


def _extract_lighting(text: str) -> dict[str, Any]:
    """Downlight vs batten vs floodlight matters when Kimi picks materials."""
    attrs: dict[str, Any] = {}

    if "downlight" in text:
        attrs["light_type"] = "downlight"
    elif "batten" in text:
        attrs["light_type"] = "batten"
    elif "panel" in text and ("led" in text or "light" in text):
        attrs["light_type"] = "panel"
    elif "floodlight" in text or "flood light" in text:
        attrs["light_type"] = "floodlight"
    elif "strip" in text and "led" in text:
        attrs["light_type"] = "led_strip"
    elif "gu10" in text:
        attrs["light_type"] = "gu10_lamp"
    elif "e27" in text or "b22" in text or "e14" in text:
        attrs["light_type"] = "lamp"
    elif "chandelier" in text or "pendant" in text:
        attrs["light_type"] = "pendant"
    elif "wall light" in text or "wall-light" in text:
        attrs["light_type"] = "wall_light"

    wattage_match = re.search(r"(\d+(?:\.\d+)?)\s*w\b", text)
    if wattage_match:
        with contextlib.suppress(ValueError):
            wattage = float(wattage_match.group(1))
            # Domestic lighting sanity: 3-100W. Screwfix strings often contain
            # things like "230W consumer unit" — avoid grabbing those.
            if 1 <= wattage <= 300:
                attrs["wattage_W"] = wattage

    ip_match = re.search(r"ip\s*(\d{2})", text)
    if ip_match:
        attrs["ip_rating"] = f"IP{ip_match.group(1)}"

    if "dimmable" in text:
        attrs["dimmable"] = True

    if "3000k" in text or "warm white" in text:
        attrs["colour_temp_K"] = 3000
    elif "4000k" in text or "cool white" in text:
        attrs["colour_temp_K"] = 4000
    elif "6000k" in text or "6500k" in text or "daylight" in text:
        attrs["colour_temp_K"] = 6000

    return attrs


def _extract_accessory(text: str) -> dict[str, Any]:
    """Sockets/switches/spurs — gangs + weatherproof + USB are the deciders."""
    attrs: dict[str, Any] = {}

    if "socket" in text and "outlet" not in text:
        attrs["accessory_type"] = "socket"
    elif "cooker outlet" in text or "cooker connection" in text:
        attrs["accessory_type"] = "cooker_outlet"
    elif "isolator" in text:
        attrs["accessory_type"] = "isolator"
    elif "spur" in text and "fused" in text:
        attrs["accessory_type"] = "fused_spur"
    elif "spur" in text:
        attrs["accessory_type"] = "spur"
    elif "dimmer" in text:
        attrs["accessory_type"] = "dimmer_switch"
    elif "switch" in text and "consumer" not in text:
        attrs["accessory_type"] = "switch"

    gang_match = re.search(r"(\d)\s*[-]?\s*gang", text)
    if gang_match:
        attrs["gangs"] = int(gang_match.group(1))

    if "usb" in text:
        attrs["has_usb"] = True

    if "weatherproof" in text or "outdoor" in text or "ip6" in text or "ip5" in text:
        attrs["weatherproof"] = True

    return attrs


_CATEGORY_EXTRACTORS = {
    ProductCategory.SECURITY_FIRE: _extract_alarm,
    ProductCategory.CABLE: _extract_cable,
    ProductCategory.CONSUMER_UNITS: _extract_consumer_unit,
    ProductCategory.MCB_RCD_RCBO: _extract_protection,
    ProductCategory.LIGHTING: _extract_lighting,
    ProductCategory.SWITCHES_SOCKETS: _extract_accessory,
}


def extract_product_attributes(product: UnifiedProduct) -> dict[str, Any]:
    """Return typed structured attributes for a normalized product.

    Returns an empty dict when the product's category has no extractor or when
    no keywords match — retrieval treats missing attributes as "unknown" and
    does not filter on them.
    """
    extractor = _CATEGORY_EXTRACTORS.get(product.category)
    if extractor is None:
        return {}
    text = _norm(f"{product.name} {product.description or ''}")
    return extractor(text)


def format_attributes_tail(attrs: dict[str, Any]) -> str:
    """Render attributes as a compact ``key=value`` tail for description text.

    Attributes are appended to the searchable description so that both the
    embedder and the LLM prompt gain disambiguating tokens ("purpose=fire",
    "cable_type=swa") — without them, "alarm" and "cable" cluster with the
    wrong siblings.
    """
    if not attrs:
        return ""
    parts = []
    for key, value in sorted(attrs.items()):
        if isinstance(value, bool):
            if value:
                parts.append(key)
        else:
            parts.append(f"{key}={value}")
    return " " + " ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Query-side intent extraction — same rules, but applied to the customer's
# free text so retrieval can filter Qdrant to items with matching attributes.
# ---------------------------------------------------------------------------


def _query_alarm_intent(text: str) -> dict[str, Any]:
    intent: dict[str, Any] = {}
    fire_hits = any(kw in text for kw in ("smoke alarm", "heat alarm", "fire alarm", "co alarm"))
    intruder_hits = any(
        kw in text for kw in ("burglar", "intruder", "cctv", "security camera", "keypad")
    )
    if fire_hits and not intruder_hits:
        intent["alarm_purpose"] = "fire"
    elif intruder_hits and not fire_hits:
        intent["alarm_purpose"] = "intruder"
    return intent


def _query_cable_intent(text: str) -> dict[str, Any]:
    intent: dict[str, Any] = {}
    swa_hit = bool(re.search(r"\bswa\b|armoured cable|steel wire|buried cable", text))
    if swa_hit:
        intent["cable_type"] = "swa"
    elif "twin & earth" in text or "twin and earth" in text or "6242y" in text:
        intent["cable_type"] = "twin_earth"
    return intent


def _query_lighting_intent(text: str) -> dict[str, Any]:
    intent: dict[str, Any] = {}
    if "downlight" in text:
        intent["light_type"] = "downlight"
    elif "floodlight" in text or "flood light" in text or "security light" in text:
        intent["light_type"] = "floodlight"
    elif "batten" in text:
        intent["light_type"] = "batten"
    elif "wall light" in text or "wall-light" in text:
        intent["light_type"] = "wall_light"
    return intent


def extract_query_intent(job_description: str) -> dict[str, Any]:
    """Extract intent attributes from a customer's free-text job description.

    Only tags we can enforce as retrieval filters are returned — a subset of
    the product-side extractors focused on the disambiguating attributes
    (alarm purpose, cable type, light type). Ambiguous queries return an
    empty dict, in which case retrieval falls back to vector-only.
    """
    text = _norm(job_description)
    intent: dict[str, Any] = {}
    intent.update(_query_alarm_intent(text))
    intent.update(_query_cable_intent(text))
    intent.update(_query_lighting_intent(text))
    return intent
