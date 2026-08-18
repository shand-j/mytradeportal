"""Validation and confidence scoring for AI-generated quote drafts."""

from decimal import Decimal
from typing import Any

from app.calculations import calculate_quote_totals
from app.models import Quote, QuoteLineItem


def validate_generated_quote(
    generated: dict[str, Any],
    retrieved_items: list[dict[str, Any]],
    tenant_settings: dict[str, Any],
) -> dict[str, Any]:
    """Assemble editable guide-priced line items from the LLM output.

    Every line item the model returns is kept — the electrician reviews and
    edits the draft. When a line references a catalogue ``code`` we ground its
    unit price against the retrieved supplier price; otherwise the model's own
    guide price is used. Nothing is silently dropped.

    Returns a dict with:
        - line_items: list of dicts ready for QuoteLineItem creation
        - confidence: float 0-1 (0.5 baseline for a usable guide, rising with
          how much of the quote is catalogue-grounded)
        - warnings: list of human-readable warnings
        - assumptions: list of assumptions the model recorded
        - notes: LLM notes
    """
    retrieved_by_code = {item["code"]: item for item in retrieved_items if item.get("code")}
    validated: list[dict[str, Any]] = []
    warnings: list[str] = []
    grounded = 0

    minimum_charge = Decimal(str(tenant_settings.get("minimum_charge", "0") or "0"))

    for raw in generated.get("line_items", []):
        quantity = Decimal(str(raw.get("quantity", "1") or "1"))
        code = raw.get("code")

        if code and code in retrieved_by_code:
            item = retrieved_by_code[code]
            description = item["description"]
            unit_price = Decimal(str(item.get("unit_price", "0") or "0"))
            grounded += 1
        else:
            # Guide-priced line from the model's own knowledge.
            description = str(raw.get("description") or "Line item")
            unit_price = Decimal(str(raw.get("unit_price", "0") or "0"))
            if code:
                warnings.append(
                    f"Guide price used for '{description}' (code {code} not in catalogue)"
                )

        validated.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "code": code if code in retrieved_by_code else None,
                "reason": raw.get("reason", ""),
            }
        )

    subtotal = sum((line["quantity"] * line["unit_price"] for line in validated), Decimal("0"))
    if minimum_charge and subtotal < minimum_charge and validated:
        warnings.append(
            f"Subtotal {subtotal} below minimum charge {minimum_charge}; "
            "consider adding a minimum-charge line item."
        )

    total = len(validated)
    confidence = round(0.5 + 0.5 * (grounded / total), 2) if total else 0.0

    return {
        "line_items": validated,
        "confidence": confidence,
        "warnings": warnings,
        "assumptions": generated.get("assumptions", []) or [],
        "notes": generated.get("notes", ""),
    }


def build_quote_from_validation(
    quote: Quote,
    validation_result: dict[str, Any],
) -> None:
    """Populate an existing Quote object with validated line items and totals."""
    for line in validation_result["line_items"]:
        quote.line_items.append(
            QuoteLineItem(
                tenant_id=quote.tenant_id,
                description=line["description"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                ai_generated=True,
            )
        )
    calculate_quote_totals(quote)
    if quote.extra_data is None:
        quote.extra_data = {}
    quote.extra_data["rag"] = {
        "confidence": validation_result["confidence"],
        "warnings": validation_result["warnings"],
        "assumptions": validation_result.get("assumptions", []),
        "notes": validation_result["notes"],
    }
