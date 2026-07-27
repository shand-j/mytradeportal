"""Unit tests for email_templates rendering helpers."""

from datetime import datetime
from decimal import Decimal

from app.email_templates import render_invoice_sent_email, render_quote_sent_email


def test_render_quote_sent_email_subject() -> None:
    subject, _ = render_quote_sent_email(
        quote_ref="abc-123",
        tenant_name="Smith Electrical",
        quote_title="Kitchen rewire",
        subtotal=Decimal("250.00"),
        vat_amount=Decimal("50.00"),
        total=Decimal("300.00"),
        vat_rate=Decimal("0.20"),
        valid_until=None,
        customer_name="Alice Jones",
    )
    assert "Smith Electrical" in subject
    assert "Quote" in subject


def test_render_quote_sent_email_contains_key_values() -> None:
    _, html = render_quote_sent_email(
        quote_ref="abc-123",
        tenant_name="Smith Electrical",
        quote_title="Kitchen rewire",
        subtotal=Decimal("250.00"),
        vat_amount=Decimal("50.00"),
        total=Decimal("300.00"),
        vat_rate=Decimal("0.20"),
        valid_until=datetime(2026, 12, 31),
        customer_name="Alice Jones",
    )
    assert "Alice Jones" in html
    assert "abc-123" in html
    assert "Kitchen rewire" in html
    assert "£250.00" in html
    assert "£50.00" in html
    assert "£300.00" in html
    assert "20%" in html
    assert "31 December 2026" in html
    assert "Smith Electrical" in html


def test_render_quote_sent_email_no_valid_until() -> None:
    _, html = render_quote_sent_email(
        quote_ref="xyz",
        tenant_name="Jones Elec",
        quote_title="Sockets",
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
        vat_rate=Decimal("0.20"),
        valid_until=None,
        customer_name="Bob",
    )
    # Should not blow up and should be valid HTML
    assert "<!DOCTYPE html>" in html
    assert "Bob" in html


def test_render_invoice_sent_email_subject() -> None:
    subject, _ = render_invoice_sent_email(
        invoice_number="INV-042",
        tenant_name="Smith Electrical",
        subtotal=Decimal("500.00"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
        vat_rate=Decimal("0.20"),
        issue_date=datetime(2026, 6, 1),
        due_date=datetime(2026, 6, 15),
        customer_name="Charlie Brown",
    )
    assert "INV-042" in subject
    assert "Smith Electrical" in subject


def test_render_invoice_sent_email_contains_key_values() -> None:
    _, html = render_invoice_sent_email(
        invoice_number="INV-007",
        tenant_name="Jones Elec",
        subtotal=Decimal("400.00"),
        vat_amount=Decimal("80.00"),
        total=Decimal("480.00"),
        vat_rate=Decimal("0.20"),
        issue_date=datetime(2026, 1, 15),
        due_date=datetime(2026, 1, 29),
        customer_name="Diana Prince",
    )
    assert "INV-007" in html
    assert "Diana Prince" in html
    assert "£400.00" in html
    assert "£80.00" in html
    assert "£480.00" in html
    assert "15 January 2026" in html
    assert "29 January 2026" in html
    assert "Jones Elec" in html


def test_render_invoice_sent_email_no_due_date() -> None:
    _, html = render_invoice_sent_email(
        invoice_number="INV-001",
        tenant_name="AcmeElec",
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
        vat_rate=Decimal("0.20"),
        issue_date=datetime(2026, 3, 1),
        due_date=None,
        customer_name="Eve",
    )
    assert "<!DOCTYPE html>" in html
    assert "INV-001" in html
