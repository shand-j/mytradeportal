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
    """Map generated line items to cost items, apply rules, and score confidence.

    Returns a dict with:
        - line_items: list of dicts ready for QuoteLineItem creation
        - confidence: float 0-1
        - warnings: list of human-readable warnings
        - notes: LLM notes
    """
    retrieved_by_code = {item["code"]: item for item in retrieved_items if item.get("code")}
    validated: list[dict[str, Any]] = []
    warnings: list[str] = []
    matched = 0

    minimum_charge = Decimal(str(tenant_settings.get("minimum_charge", "0") or "0"))

    for raw in generated.get("line_items", []):
        code = raw.get("code")
        quantity = Decimal(str(raw.get("quantity", "1")))
        if not code or code not in retrieved_by_code:
            warnings.append(f"Skipping unrecognized item code: {code}")
            continue

        item = retrieved_by_code[code]
        unit_price = Decimal(str(item.get("unit_price", "0")))
        validated.append(
            {
                "description": item["description"],
                "quantity": quantity,
                "unit_price": unit_price,
                "code": code,
                "reason": raw.get("reason", ""),
            }
        )
        matched += 1

    subtotal = sum(line["quantity"] * line["unit_price"] for line in validated)
    if minimum_charge and subtotal < minimum_charge and validated:
        warnings.append(
            f"Subtotal {subtotal} below minimum charge {minimum_charge}; consider adding a minimum-charge line item."
        )

    total_generated = len(generated.get("line_items", []))
    confidence = matched / total_generated if total_generated else 0.0
    if not validated:
        confidence = 0.0

    return {
        "line_items": validated,
        "confidence": round(confidence, 2),
        "warnings": warnings,
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
            )
        )
    calculate_quote_totals(quote)
    if quote.extra_data is None:
        quote.extra_data = {}
    quote.extra_data["rag"] = {
        "confidence": validation_result["confidence"],
        "warnings": validation_result["warnings"],
        "notes": validation_result["notes"],
    }
