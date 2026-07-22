"""Unit tests for quote and invoice VAT calculations."""

from decimal import Decimal

from app.calculations import calculate_invoice_totals, calculate_quote_totals
from app.models import Invoice, InvoiceLineItem, Quote, QuoteLineItem


def test_calculate_quote_totals_with_vat() -> None:
    quote = Quote(vat_rate=Decimal("0.20"))
    quote.line_items = [
        QuoteLineItem(description="Labour", quantity=Decimal("2"), unit_price=Decimal("120.00")),
        QuoteLineItem(description="Materials", quantity=Decimal("1"), unit_price=Decimal("45.50")),
    ]
    calculate_quote_totals(quote)

    assert quote.subtotal == Decimal("285.50")
    assert quote.vat_amount == Decimal("57.10")
    assert quote.total == Decimal("342.60")
    assert quote.line_items[0].total == Decimal("240.00")
    assert quote.line_items[1].total == Decimal("45.50")


def test_calculate_quote_totals_zero_vat() -> None:
    quote = Quote(vat_rate=Decimal("0.00"))
    quote.line_items = [
        QuoteLineItem(description="Call-out", quantity=Decimal("1"), unit_price=Decimal("75.00")),
    ]
    calculate_quote_totals(quote)

    assert quote.subtotal == Decimal("75.00")
    assert quote.vat_amount == Decimal("0.00")
    assert quote.total == Decimal("75.00")


def test_calculate_invoice_totals_with_vat() -> None:
    invoice = Invoice(vat_rate=Decimal("0.20"))
    invoice.line_items = [
        InvoiceLineItem(description="Labour", quantity=Decimal("1"), unit_price=Decimal("500.00")),
        InvoiceLineItem(description="Parts", quantity=Decimal("2"), unit_price=Decimal("30.00")),
    ]
    calculate_invoice_totals(invoice)

    assert invoice.subtotal == Decimal("560.00")
    assert invoice.vat_amount == Decimal("112.00")
    assert invoice.total == Decimal("672.00")
    assert invoice.line_items[0].total == Decimal("500.00")
    assert invoice.line_items[1].total == Decimal("60.00")
