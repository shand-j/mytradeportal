"""Offline scenario harness for the intake-completeness → confidence uplift.

Not a live-LLM eval — this walks the deterministic
:func:`app.routers.quotes._intake_completeness` scorer through four intake
scenarios (bare lead → rich AI chat) and prints how each drives the
Confidence 2.0 formula in
:func:`app.rag.validation.validate_generated_quote`.

Run:
    cd services/api && python -m evals.completeness_scenarios
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.models import QuoteRequest
from app.routers.quotes import _INTAKE_WEIGHTS, _intake_completeness

DESCRIPTION = "Add two double sockets in the living room and one in the bedroom."


@dataclass
class Scenario:
    name: str
    urgency: str | None
    structured_data: dict[str, Any]

    def request(self) -> QuoteRequest:
        return QuoteRequest(
            tenant_id=uuid4(),
            source="web_form",
            raw_text=DESCRIPTION,
            urgency=self.urgency,
            structured_data=self.structured_data,
        )


SCENARIOS: list[Scenario] = [
    Scenario(
        name="Bare lead only",
        urgency=None,
        structured_data={},
    ),
    Scenario(
        name="Lead + form",
        urgency="this_week",
        structured_data={"property": {"type": "semi-detached", "bedrooms": 3}},
    ),
    Scenario(
        name="Lead + form + basic AI chat",
        urgency="this_week",
        structured_data={
            "property": {"type": "semi-detached", "bedrooms": 3},
            "ai_extracted": {
                "consumer_unit_location": "under stairs",
                "parking": "driveway",
            },
        },
    ),
    Scenario(
        name="Lead + form + rich AI chat",
        urgency="this_week",
        structured_data={
            "property": {"type": "semi-detached", "bedrooms": 3},
            "ai_extracted": {
                "consumer_unit_location": "under stairs",
                "parking": "driveway",
                "location": "living room and bedroom",
                "quantity": "3 double sockets",
                "existing_setup": "surface skirting trunking preferred",
                "preference": "brushed brass finish",
            },
        },
    ),
]

# Assumed catalogue grounding for the confidence formula. Chosen to match the
# eval's typical live "grounded=1.0 material line" behaviour on similar jobs.
_ASSUMED_GROUNDED_RATIOS = (0.5, 1.0)


def _confidence(grounded_ratio: float, completeness: float) -> float:
    return round(0.3 + 0.3 * grounded_ratio + 0.4 * completeness, 2)


def run() -> int:
    print("Signal weights:")
    for key, weight in _INTAKE_WEIGHTS.items():
        print(f"  {key:22s} {weight:.2f}")
    print()

    header = f"{'scenario':<32} completeness"
    for gr in _ASSUMED_GROUNDED_RATIOS:
        header += f"   conf(grnd={gr})"
    print(header)
    print("-" * len(header))

    scores: list[tuple[str, float, list[float]]] = []
    for scenario in SCENARIOS:
        completeness = _intake_completeness(DESCRIPTION, quote_request=scenario.request())
        row = f"{scenario.name:<32} {completeness:.2f}       "
        confs = []
        for gr in _ASSUMED_GROUNDED_RATIOS:
            conf = _confidence(gr, completeness)
            confs.append(conf)
            row += f"     {conf:.2f}    "
        print(row)
        scores.append((scenario.name, completeness, confs))

    baseline_completeness = scores[1][1]  # form-only
    rich_completeness = scores[3][1]
    lift = rich_completeness - baseline_completeness
    print()
    print(f"AI chat lift (rich vs form-only): +{lift:.2f} completeness")
    for i, gr in enumerate(_ASSUMED_GROUNDED_RATIOS):
        conf_lift = scores[3][2][i] - scores[1][2][i]
        print(f"  → +{conf_lift:.2f} confidence at grounded_ratio={gr}")

    assert lift >= 0.4, f"Rich AI chat must lift completeness by >= 0.4 (got {lift:.2f})"
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
