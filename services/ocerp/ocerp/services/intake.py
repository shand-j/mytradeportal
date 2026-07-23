"""Structured job intake and missing-data gate for the quoting agent.

This module is the first node in the code-first agent graph.  Its job is to:
1. Parse free-text or form data into a typed ``SiteSurvey``.
2. Decide what additional data must be collected before a BoQ can be produced.
3. Return targeted, electrician-friendly questions so the agent never has to
   guess critical safety/commercial facts.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SiteSurvey(BaseModel):
    """Structured site-survey data captured before estimating.

    Fields mirror ``docs/ai_electrician_quoting_platform_research/job_capture_data_model.json``
    but are narrowed to the inputs that materially change a domestic electrical
    quote.  Unknown/missing fields are ``None``.
    """

    model_config = ConfigDict(extra="allow")

    property_type: (
        Literal[
            "detached",
            "semi-detached",
            "terraced",
            "flat",
            "bungalow",
            "maisonette",
        ]
        | None
    ) = None
    property_age: str | None = None
    bedroom_count: int | None = None
    room_count: int | None = None
    floor_count: int | None = None
    consumer_unit_location: str | None = None
    consumer_unit_age: str | None = None
    earthing_system: Literal["TN-C-S", "TN-S", "TT", "unknown"] | None = None
    parking: str | None = None
    access_notes: str | None = None
    photos: list[str] = Field(default_factory=list)
    special_locations: list[str] = Field(default_factory=list)
    existing_installation_condition: Literal["good", "fair", "poor", "unknown"] | None = None
    preferred_spec: Literal["budget", "mid", "premium"] | None = None
    preferred_brands: list[str] = Field(default_factory=list)
    occupancy: Literal["occupied", "vacant", "unknown"] | None = None
    making_good_required: bool | None = None
    urgency: str | None = None
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_empty_strings_to_none(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Treat empty form values as missing."""
        return {k: (None if v == "" else v) for k, v in values.items()}


def parse_site_survey(raw: dict[str, Any] | None) -> SiteSurvey:
    """Best-effort parse of a site-survey payload."""
    if raw is None:
        return SiteSurvey()
    # Allow either a flat dict or a nested "survey" key.
    payload = raw.get("survey") if isinstance(raw, dict) and "survey" in raw else raw
    if not isinstance(payload, dict):
        return SiteSurvey()
    return SiteSurvey.model_validate(payload)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _extract_bedrooms(description: str) -> int | None:
    text = _norm(description)
    for word, num in {
        "one bed": 1,
        "two bed": 2,
        "three bed": 3,
        "four bed": 4,
        "five bed": 5,
        "six bed": 6,
    }.items():
        if word in text:
            return num
    m = re.search(r"(\d+)\s*bed", text)
    if m:
        return int(m.group(1))
    return None


def _detect_job_type(description: str) -> str:
    """Return a coarse job-type tag used to drive the missing-data gate."""
    text = _norm(description)
    if "ev" in text or "charger" in text or "charge point" in text:
        return "ev_charger"
    if re.search(r"\b(consumer unit|fuse box|fuseboard|distribution board)\b", text) and (
        "new" in text or "upgrade" in text or "replace" in text or "change" in text
    ):
        return "consumer_unit_upgrade"
    if "rewire" in text:
        return "rewire"
    if "extension" in text:
        return "extension"
    if "kitchen" in text:
        return "kitchen"
    if "bathroom" in text or "shower" in text:
        return "bathroom"
    if "garage" in text or "outbuilding" in text or "garden" in text:
        return "outbuilding"
    if "eicr" in text or "condition report" in text:
        return "eicr"
    return "general"


# ---------------------------------------------------------------------------
# Missing-data gate
# ---------------------------------------------------------------------------

_Question = tuple[str, str]  # (field, question text)


_REQUIRED_FIELDS: dict[str, list[_Question]] = {
    "rewire": [
        (
            "property_type",
            "What type of property is this (detached, semi, terraced, flat, bungalow)?",
        ),
        ("bedroom_count", "How many bedrooms are there?"),
        ("consumer_unit_age", "How old is the existing consumer unit / fuse board?"),
        ("earthing_system", "Do you know the earthing system (PME/TN-C-S, TN-S or TT)?"),
        ("preferred_spec", "Do you want budget, mid-range or premium accessories?"),
        ("occupancy", "Will the property be occupied during the work?"),
    ],
    "consumer_unit_upgrade": [
        ("consumer_unit_age", "How old is the existing consumer unit / fuse board?"),
        ("consumer_unit_location", "Where is the consumer unit located?"),
        ("earthing_system", "Do you know the earthing system (PME/TN-C-S, TN-S or TT)?"),
        (
            "preferred_spec",
            "Do you want a dual-RCD board, an RCBO board, or a premium branded board?",
        ),
    ],
    "ev_charger": [
        ("property_type", "What type of property is this?"),
        ("parking", "Where will the vehicle be parked (driveway, garage, on-street)?"),
        (
            "consumer_unit_location",
            "Where is the consumer unit in relation to the parking location?",
        ),
        ("earthing_system", "Do you know the earthing system?"),
    ],
    "extension": [
        ("property_type", "What type of property is being extended?"),
        ("room_count", "How many new rooms / zones are in the extension?"),
        ("special_locations", "Will the extension include a kitchen or bathroom?"),
        ("preferred_spec", "Do you want budget, mid-range or premium accessories?"),
    ],
    "kitchen": [
        ("room_count", "How many kitchen zones / rooms are being worked on?"),
        ("preferred_spec", "Do you want budget, mid-range or premium accessories?"),
    ],
    "bathroom": [
        ("room_count", "How many bathrooms / shower rooms are being worked on?"),
        ("preferred_spec", "Do you want budget, mid-range or premium accessories?"),
    ],
    "outbuilding": [
        ("property_type", "What type of property is the supply coming from?"),
        ("earthing_system", "Do you know the earthing system?"),
    ],
    "eicr": [
        ("property_type", "What type of property is being inspected?"),
        ("consumer_unit_age", "How old is the existing consumer unit?"),
    ],
    "general": [
        ("property_type", "What type of property is this?"),
        ("preferred_spec", "Do you want budget, mid-range or premium fittings?"),
    ],
}


def missing_data_questions(
    description: str,
    survey: SiteSurvey,
) -> list[str]:
    """Return the questions that must be answered before estimating this job.

    The gate is intentionally conservative: for high-stakes work (rewires, CU
    changes, EV chargers) we require enough facts to size cables, choose
    protection and estimate labour safely.  The LLM is never asked to fill these
    gaps with assumptions.
    """
    job_type = _detect_job_type(description)
    required = _REQUIRED_FIELDS.get(job_type, _REQUIRED_FIELDS["general"])
    questions: list[str] = []

    # The description itself can satisfy bedroom_count.
    inferred_bedrooms = _extract_bedrooms(description)

    for field, question in required:
        value = getattr(survey, field, None)
        if field == "bedroom_count" and inferred_bedrooms is not None:
            continue
        if field == "special_locations" and isinstance(value, list) and not value:
            questions.append(question)
            continue
        if value is None or value == "unknown":
            questions.append(question)

    return questions


def build_clarification_response(questions: list[str]) -> dict[str, Any]:
    """A placeholder BoQ response that asks for missing data.

    This keeps the API contract stable: the caller receives a
    ``BoQGenerateResponse`` shape, but with ``clarification_questions`` set so
    the UI can prompt the user instead of showing an empty quote.
    """
    return {
        "line_items": [],
        "subtotal": "0.00",
        "vat_rate": "0.20",
        "vat_amount": "0.00",
        "total": "0.00",
        "confidence": "0.0",
        "warnings": [],
        "notes": (
            "We need a little more information to produce an accurate, "
            "compliant quote. Please answer the questions below."
        ),
        "analysis": None,
        "regulatory_citations": [],
        "compliance_warnings": [],
        "clarification_questions": questions,
    }
