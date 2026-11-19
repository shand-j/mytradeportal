"""Pricing and VAT calculations."""

from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any
from uuid import UUID

from app.models import Invoice, InvoiceLineItem, Quote, Tenant

LINE_PRECISION = Decimal("0.0001")
TOTAL_PRECISION = Decimal("0.01")
DEFAULT_VAT_RATE = Decimal("0.20")

# Tenant setting values (``settings["quote_rounding"]``) that enable rounding.
ROUNDING_INCREMENTS = (Decimal("5"), Decimal("10"))


def tenant_vat_rate(tenant: Tenant) -> Decimal:
    """The VAT rate to apply to new quotes/invoices for this tenant.

    Non-VAT-registered businesses charge 0% — the onboarding Tax step captures
    ``vat_registered`` and this is where it takes effect. Registered businesses
    use their configured rate (settings.vat_rate) or the UK standard 20%.
    """
    if not tenant.vat_registered:
        return Decimal("0")
    raw = (tenant.settings or {}).get("vat_rate")
    if raw is None:
        return DEFAULT_VAT_RATE
    try:
        return Decimal(str(raw))
    except ArithmeticError:
        return DEFAULT_VAT_RATE


def vat_rate_within_tenant_limit(tenant: Tenant, vat_rate: Decimal) -> bool:
    """A per-document VAT override may only lower or remove VAT (issue #110).

    A quote/invoice must never charge MORE VAT than the tenant's registered
    rate via a per-document override; anything up to and including the tenant
    rate is allowed (exactly the tenant rate is a harmless no-op). For a
    non-registered tenant the registered rate is 0%, so any positive override
    is rejected.
    """
    return vat_rate <= tenant_vat_rate(tenant)


def quote_rounding_increment(settings: dict[str, Any] | None) -> Decimal | None:
    """Resolve the tenant's quote-total rounding increment (£5 or £10).

    ``settings["quote_rounding"]`` is 0 (off), 5 or 10. Unrecognised values
    are treated as off so a bad settings write never corrupts totals.
    """
    if not settings:
        return None
    raw = settings.get("quote_rounding")
    try:
        increment = Decimal(str(raw))
    except ArithmeticError:
        return None
    if increment in ROUNDING_INCREMENTS:
        return increment
    return None


def round_up_to_increment(total: Decimal, increment: Decimal) -> Decimal:
    """Round ``total`` UP to the nearest multiple of ``increment`` (£1236.40 → £1240)."""
    return (total / increment).to_integral_value(rounding=ROUND_CEILING) * increment


def apply_quote_rounding(quote: Quote, settings: dict[str, Any] | None) -> None:
    """Apply the tenant's rounding setting to a quote whose totals are fresh.

    Must be called AFTER :func:`calculate_quote_totals` (which always rebuilds
    the VAT-inclusive total from line items, excluding any previous
    adjustment), so re-applying on every totals recompute is idempotent. The
    uplift is stored in ``quote.rounding_adjustment`` so the UI can show a
    visible "rounded up +£3.60" indicator; line items are never touched.
    """
    increment = quote_rounding_increment(settings)
    if increment is None:
        quote.rounding_adjustment = Decimal("0.00")
        return
    rounded = round_up_to_increment(quote.total, increment)
    quote.rounding_adjustment = (rounded - quote.total).quantize(TOTAL_PRECISION)
    quote.total = rounded


def calculate_quote_totals(quote: Quote) -> None:
    """Recalculate subtotal, VAT, and total for a quote.

    Line totals are kept at LINE_PRECISION so that per-unit rounding does not
    drift the final VAT-inclusive total away from the supplier's price. The
    stored subtotal/total are rounded to TOTAL_PRECISION and the VAT amount is
    the residual needed to make them balance.
    """
    subtotal_exact = Decimal("0.0000")
    for item in quote.line_items:
        item.total = (item.quantity * item.unit_price).quantize(LINE_PRECISION)
        subtotal_exact += item.total
    quote.subtotal = subtotal_exact.quantize(TOTAL_PRECISION)
    vat_rate = quote.vat_rate if quote.vat_rate is not None else Decimal("0.20")
    quote.total = (subtotal_exact * (Decimal("1") + vat_rate)).quantize(TOTAL_PRECISION)
    quote.vat_amount = quote.total - quote.subtotal


def calculate_invoice_totals(invoice: Invoice) -> None:
    """Recalculate subtotal, VAT, and total for an invoice."""
    subtotal_exact = Decimal("0.0000")
    for item in invoice.line_items:
        item.total = (item.quantity * item.unit_price).quantize(LINE_PRECISION)
        subtotal_exact += item.total
    invoice.subtotal = subtotal_exact.quantize(TOTAL_PRECISION)
    vat_rate = invoice.vat_rate if invoice.vat_rate is not None else Decimal("0.20")
    invoice.total = (subtotal_exact * (Decimal("1") + vat_rate)).quantize(TOTAL_PRECISION)
    invoice.vat_amount = invoice.total - invoice.subtotal


def apply_invoice_rounding(invoice: Invoice, settings: dict[str, Any] | None) -> None:
    """Apply the tenant's rounding setting to a SCRATCH invoice (no source quote).

    Must be called AFTER :func:`calculate_invoice_totals`, same idempotency
    contract as :func:`apply_quote_rounding`. Invoices created FROM a quote
    never call this — they mirror the quote's stored totals via
    :func:`build_invoice_from_quote`, so a quote created before the setting
    existed invoices unrounded and a rounded quote is never re-rounded.
    """
    increment = quote_rounding_increment(settings)
    if increment is None:
        invoice.rounding_adjustment = Decimal("0.00")
        return
    rounded = round_up_to_increment(invoice.total, increment)
    invoice.rounding_adjustment = (rounded - invoice.total).quantize(TOTAL_PRECISION)
    invoice.total = rounded


def build_invoice_from_quote(
    quote: Quote,
    invoice_number: str,
    due_date: datetime | None = None,
    job_id: UUID | None = None,
) -> Invoice:
    """Create a draft invoice that clones a quote's line items and totals.

    The invoice mirrors the quote exactly — line items, subtotal, VAT, total
    and rounding uplift — and is never re-rounded, so the customer pays the
    total they accepted. ``job_id`` links the invoice back to the job the
    electrician raised it from (quote → job → invoice).
    """
    invoice = Invoice(
        tenant_id=quote.tenant_id,
        contact_id=quote.contact_id,
        job_id=job_id,
        quote_id=quote.id,
        invoice_number=invoice_number,
        due_date=due_date,
        vat_rate=quote.vat_rate,
    )
    for line in quote.line_items:
        invoice.line_items.append(
            InvoiceLineItem(
                tenant_id=quote.tenant_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
        )
    calculate_invoice_totals(invoice)
    # Inherit the quote's rounding uplift so the invoice total matches the
    # total the customer accepted. Zero for quotes created before the setting
    # existed, so those invoices stay unrounded too.
    adjustment = quote.rounding_adjustment or Decimal("0.00")
    invoice.rounding_adjustment = adjustment
    if adjustment:
        invoice.total = invoice.total + adjustment
    return invoice
