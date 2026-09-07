"""Query-side intent extraction for RAG retrieval.

Mirrors the disambiguating attributes emitted by the data pipeline's
``normalizer.attributes.extract_product_attributes``. Kept as a separate
lightweight module in the API to avoid a runtime dependency on the pipeline
package; the two extractors share their taxonomy and must be updated together.

When the query carries an intent tag (e.g. ``alarm_purpose=fire``) we filter
Qdrant to items with the matching ``attr_alarm_purpose`` field so semantic
siblings — burglar alarms for smoke queries, extension reels for SWA — are
excluded before the vector similarity ranks the survivors.
"""

from __future__ import annotations

import re
from typing import Any


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _query_alarm_intent(text: str) -> dict[str, Any]:
    intent: dict[str, Any] = {}
    fire_hits = any(
        kw in text
        for kw in ("smoke alarm", "heat alarm", "fire alarm", "co alarm", "smoke detector")
    )
    intruder_hits = any(
        kw in text
        for kw in ("burglar", "intruder", "cctv", "security camera", "keypad", "motion sensor")
    )
    if fire_hits and not intruder_hits:
        intent["alarm_purpose"] = "fire"
    elif intruder_hits and not fire_hits:
        intent["alarm_purpose"] = "intruder"
    return intent


def _query_cable_intent(text: str) -> dict[str, Any]:
    intent: dict[str, Any] = {}
    if re.search(r"\bswa\b|armoured cable|steel wire|buried cable", text):
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
    elif "wall light" in text or "outside wall light" in text:
        intent["light_type"] = "wall_light"
    return intent


def extract_query_intent(job_description: str) -> dict[str, Any]:
    """Return filter-able intent tags from a job description."""
    text = _norm(job_description)
    intent: dict[str, Any] = {}
    intent.update(_query_alarm_intent(text))
    intent.update(_query_cable_intent(text))
    intent.update(_query_lighting_intent(text))
    return intent
