"""Pricing and VAT calculations."""

from datetime import datetime
from decimal import Decimal

from app.models import Invoice, InvoiceLineItem, Quote

LINE_PRECISION = Decimal("0.0001")
TOTAL_PRECISION = Decimal("0.01")


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


def build_invoice_from_quote(
    quote: Quote,
    invoice_number: str,
    due_date: datetime | None = None,
) -> Invoice:
    """Create a draft invoice that clones a quote's line items and totals."""
    invoice = Invoice(
        tenant_id=quote.tenant_id,
        contact_id=quote.contact_id,
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
    return invoice
