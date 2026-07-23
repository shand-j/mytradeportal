"""Pricing engine for the requirements-driven BoQ.

Converts resolved catalogue items and synthetic labour lines into the final
BoQLineItem model.  All configurable values (rates, VAT, markup, minimum charge)
come from `PricingConfig`, not from inline constants.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from mtp_shared import BoQLineItem, PriceLookupResponse
from sqlalchemy import select

from ocerp.models import CostItem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from ocerp.services.boq_models import PricingConfig, ResolvedCostItem


class PriceFloorViolationError(ValueError):
    """Raised when a priced material line would be sold below its cost floor.

    The BoQ engine catches this and skips the offending line with a warning
    so the customer never receives a quote that is below cost + minimum margin.
    """


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _unit_price_from_cost_item(cost_item: dict[str, Any]) -> Decimal:
    return _to_decimal(cost_item.get("unit_price", 0))


def price_material_item(resolved: ResolvedCostItem, config: PricingConfig) -> BoQLineItem:
    """Price a resolved material item using catalogue price + markup.

    Raises ``PriceFloorViolationErrorError`` if the resulting unit price would be at or
    below the catalogue cost, or below the configured minimum margin.
    """
    cost_item = resolved.cost_item
    quantity = resolved.requirement.quantity
    unit_price_ex_markup = _unit_price_from_cost_item(cost_item)

    if unit_price_ex_markup <= 0:
        raise PriceFloorViolationError(
            f"Cost item {cost_item.get('code')!r} has non-positive catalogue "
            f"price {unit_price_ex_markup}; refusing to price it."
        )

    markup_multiplier = Decimal("1") + (config.markup_percent / Decimal("100"))
    material_cost = (unit_price_ex_markup * markup_multiplier).quantize(Decimal("0.0001"))

    if material_cost < unit_price_ex_markup:
        # Negative markup would mean selling at a loss — always forbidden,
        # even when min_margin_percent is unset.
        raise PriceFloorViolationError(
            f"Cost item {cost_item.get('code')!r} priced at {material_cost} "
            f"is below its catalogue cost {unit_price_ex_markup}."
        )

    min_margin = getattr(config, "min_margin_percent", Decimal("0"))
    if min_margin > 0:
        floor = (unit_price_ex_markup * (Decimal("1") + min_margin / Decimal("100"))).quantize(
            Decimal("0.0001")
        )
        if material_cost < floor:
            raise PriceFloorViolationError(
                f"Cost item {cost_item.get('code')!r} priced at {material_cost} "
                f"is below the {min_margin}% margin floor of {floor} "
                f"(catalogue cost {unit_price_ex_markup})."
            )

    unit_price = material_cost
    total = (unit_price * quantity).quantize(Decimal("0.0001"))

    description = str(cost_item.get("description", resolved.requirement.concept))
    # For dedicated circuit labels, append the requirement note so the
    # description carries context (e.g. "loft circuit") without affecting
    # all line items.
    if resolved.requirement.notes and resolved.requirement.concept in {"loft_rcbo", "garage_rcbo"}:
        description = f"{description} ({resolved.requirement.notes})"

    return BoQLineItem(
        code=str(cost_item.get("code", resolved.requirement.id)),
        description=description,
        unit=str(cost_item.get("unit", "each")),
        quantity=quantity,
        labour_hours=Decimal("0"),
        labour_rate=Decimal("0"),
        labour_total=Decimal("0"),
        material_cost=material_cost,
        material_total=total,
        plant_cost=Decimal("0"),
        plant_total=Decimal("0"),
        unit_price=unit_price,
        total=total,
        category=str(cost_item.get("category")),
        supplier=str(
            cost_item.get("supplier") or cost_item.get("source") or resolved.resolution_source
        ),
        brand=str(cost_item.get("brand")) if cost_item.get("brand") else None,
        sku=str(cost_item.get("sku")) if cost_item.get("sku") else None,
        product_url=str(cost_item.get("product_url")) if cost_item.get("product_url") else None,
        retail_price_incl_vat=_to_decimal(cost_item.get("retail_price_incl_vat"))
        if cost_item.get("retail_price_incl_vat")
        else None,
        notes=resolved.requirement.notes or "",
    )


def price_labour_item(raw: dict[str, Any], config: PricingConfig) -> BoQLineItem:
    """Price a synthetic labour line from tenant rates.

    Raises ``PriceFloorViolationErrorError`` for labour lines that would charge a
    zero (or negative) rate, except for the minimum-charge adjustment which
    is always allowed through.
    """
    code = str(raw.get("code", ""))
    quantity = _to_decimal(raw.get("quantity", "1"))
    labour_rate = _to_decimal(raw.get("labour_rate", "0"))
    labour_hours = _to_decimal(raw.get("labour_hours", "1"))
    notes = str(raw.get("notes", ""))

    if labour_rate <= 0 and code != "LABOUR-MINIMUM-CHARGE-ADJUSTMENT":
        raise PriceFloorViolationError(
            f"Labour line {code!r} has non-positive rate {labour_rate}; "
            "check tenant labour-rate settings."
        )

    unit_price = labour_rate
    labour_total = (labour_rate * quantity).quantize(Decimal("0.0001"))
    total = labour_total

    description = "Labour"
    unit = "hour"
    if code == "LABOUR-ELECTRICIAN-DAY":
        description = "Electrician labour - day rate"
        unit = "day"
    elif code == "LABOUR-ELECTRICIAN-HOUR":
        description = "Electrician labour - hourly rate"
    elif code == "LABOUR-MATE-DAY":
        description = "Electrician's mate - day rate"
        unit = "day"
    elif code == "LABOUR-MATE-HOUR":
        description = "Electrician's mate - hourly rate"
    elif code == "LABOUR-MINIMUM-CHARGE-ADJUSTMENT":
        description = "Minimum charge adjustment"
        unit = "each"

    return BoQLineItem(
        code=code,
        description=description,
        unit=unit,
        quantity=quantity,
        labour_hours=labour_hours,
        labour_rate=labour_rate,
        labour_total=labour_total,
        material_cost=Decimal("0"),
        material_total=Decimal("0"),
        plant_cost=Decimal("0"),
        plant_total=Decimal("0"),
        unit_price=unit_price,
        total=total,
        category="Labour",
        supplier="Tenant rate",
        sku=None,
        notes=notes,
    )


def apply_minimum_charge(
    line_items: list[BoQLineItem],
    config: PricingConfig,
) -> tuple[list[BoQLineItem], list[str]]:
    """Add a minimum-charge adjustment line if the subtotal is below threshold."""
    warnings: list[str] = []
    if config.minimum_charge <= 0:
        return line_items, warnings

    subtotal_exact = sum((li.total for li in line_items), Decimal("0.0000"))
    subtotal = subtotal_exact.quantize(Decimal("0.01"))
    if subtotal >= config.minimum_charge:
        return line_items, warnings

    adjustment = config.minimum_charge - subtotal
    warnings.append(
        f"Subtotal {subtotal} is below the minimum charge {config.minimum_charge}; "
        f"a {adjustment} adjustment has been added."
    )
    line_items.append(
        BoQLineItem(
            code="LABOUR-MINIMUM-CHARGE-ADJUSTMENT",
            description="Minimum charge adjustment",
            unit="each",
            quantity=Decimal("1"),
            labour_hours=Decimal("0"),
            labour_rate=Decimal("0"),
            labour_total=adjustment,
            material_cost=Decimal("0"),
            material_total=Decimal("0"),
            plant_cost=Decimal("0"),
            plant_total=Decimal("0"),
            unit_price=adjustment,
            total=adjustment,
            category="Labour",
            supplier="Tenant rate",
            sku=None,
            notes="Adjustment to meet business minimum charge",
        )
    )
    return line_items, warnings


def build_totals(
    line_items: list[BoQLineItem],
    config: PricingConfig,
) -> tuple[Decimal, Decimal, Decimal, Decimal, list[str]]:
    """Compute subtotal, VAT, total, and minimum-charge warnings."""
    line_items, warnings = apply_minimum_charge(line_items, config)
    subtotal_exact = sum((li.total for li in line_items), Decimal("0.0000"))
    subtotal = subtotal_exact.quantize(Decimal("0.01"))
    vat_amount = (subtotal_exact * config.vat_rate).quantize(Decimal("0.01"))
    total = (subtotal + vat_amount).quantize(Decimal("0.01"))
    return subtotal, config.vat_rate, vat_amount, total, warnings


# ---------------------------------------------------------------------------
# Regional price lookup service (kept here for backwards compatibility)
# ---------------------------------------------------------------------------


async def lookup_price(
    db: AsyncSession,
    code: str,
    region: str = "UK",
) -> PriceLookupResponse:
    """Look up a cost item by code and region."""
    result = await db.execute(
        select(CostItem).where(
            CostItem.code == code,
            CostItem.region == region,
            CostItem.is_active.is_(True),
        )
    )
    item: CostItem | None = result.scalar_one_or_none()
    if item is None:
        return PriceLookupResponse(
            code=code,
            region=region,
            found=False,
        )

    return PriceLookupResponse(
        code=item.code,
        description=item.description,
        unit=item.unit,
        unit_price=item.unit_price,
        currency=item.currency,
        region=item.region,
        found=True,
    )
