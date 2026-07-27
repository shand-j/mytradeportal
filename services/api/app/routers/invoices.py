"""Invoice endpoints."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import Actions, write_audit_log
from app.calculations import build_invoice_from_quote, calculate_invoice_totals
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.email import send_email
from app.email_templates import render_invoice_sent_email
from app.models import Contact, Invoice, InvoiceLineItem, Job, Quote
from app.rls import set_tenant_in_session
from app.schemas import InvoiceCreate, InvoiceRead, InvoiceUpdate

router = APIRouter(prefix="/invoices", tags=["Invoices"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Invoice PDF helpers (pure-sync, safe to run in a worker thread)
# ---------------------------------------------------------------------------


def _invoice_pdf_snapshot(invoice: Invoice, tenant_name: str) -> dict[str, Any]:
    """Pre-materialise everything the PDF renderer needs as plain primitives.

    Called on the asyncio thread while the AsyncSession is still open, so ORM
    relationships can be accessed safely here before handing off to the thread.
    """
    return {
        "invoice_number": invoice.invoice_number,
        "tenant_name": tenant_name,
        "status": invoice.status,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "subtotal": float(invoice.subtotal),
        "vat_rate": float(invoice.vat_rate),
        "vat_amount": float(invoice.vat_amount),
        "total": float(invoice.total),
        "notes": invoice.notes or "",
        "contact": {
            "name": invoice.contact.name if invoice.contact else "",
            "email": invoice.contact.email if invoice.contact else None,
        },
        "line_items": [
            {
                "description": li.description,
                "quantity": float(li.quantity),
                "unit_price": float(li.unit_price),
                "total": float(li.total),
            }
            for li in invoice.line_items
        ],
    }


def _render_invoice_pdf(snapshot: dict[str, Any]) -> bytes:
    """Render an invoice PDF from a pre-materialised snapshot.

    Pure-sync, no ORM, safe to call from a worker thread.
    """
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, snapshot["tenant_name"], ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, "Invoice", ln=True)  # type: ignore[arg-type]
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Invoice metadata
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Invoice Details", ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Invoice Number: {snapshot['invoice_number']}", ln=True)  # type: ignore[arg-type]
    pdf.cell(0, 6, f"Issue Date: {snapshot['issue_date'].strftime('%d/%m/%Y')}", ln=True)  # type: ignore[arg-type]
    if snapshot["due_date"]:
        pdf.cell(0, 6, f"Due Date: {snapshot['due_date'].strftime('%d/%m/%Y')}", ln=True)  # type: ignore[arg-type]
    pdf.ln(5)

    # Customer details
    contact = snapshot["contact"]
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Customer", ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, contact["name"], ln=True)  # type: ignore[arg-type]
    if contact["email"]:
        pdf.cell(0, 6, contact["email"], ln=True)  # type: ignore[arg-type]
    pdf.ln(5)

    # Line items table
    pdf.set_fill_color(245, 244, 240)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 8, "Item", 1, 0, "L", True)  # type: ignore[arg-type]
    pdf.cell(25, 8, "Qty", 1, 0, "C", True)  # type: ignore[arg-type]
    pdf.cell(30, 8, "Unit Price", 1, 0, "R", True)  # type: ignore[arg-type]
    pdf.cell(30, 8, "Total", 1, 1, "R", True)  # type: ignore[arg-type]

    pdf.set_font("Helvetica", "", 10)
    for item in snapshot["line_items"]:
        start_y = pdf.get_y()
        pdf.multi_cell(100, 8, item["description"], border=1, align="L")
        row_h = pdf.get_y() - start_y
        pdf.set_xy(110, start_y)
        pdf.cell(25, row_h, str(item["quantity"]), 1, 0, "C")  # type: ignore[arg-type]
        pdf.set_xy(135, start_y)
        pdf.cell(30, row_h, f"£{item['unit_price']:,.2f}", 1, 0, "R")  # type: ignore[arg-type]
        pdf.set_xy(165, start_y)
        pdf.cell(30, row_h, f"£{item['total']:,.2f}", 1, 1, "R")  # type: ignore[arg-type]

    pdf.ln(5)

    # Totals
    pdf.set_font("Helvetica", "B", 11)
    vat_label = f"VAT ({snapshot['vat_rate'] * 100:.0f}%): £{snapshot['vat_amount']:,.2f}"
    pdf.cell(0, 8, f"Subtotal: £{snapshot['subtotal']:,.2f}", ln=True, align="R")  # type: ignore[arg-type]
    pdf.cell(0, 8, vat_label, ln=True, align="R")  # type: ignore[arg-type]
    pdf.cell(0, 8, f"Total: £{snapshot['total']:,.2f}", ln=True, align="R")  # type: ignore[arg-type]

    if snapshot["notes"]:
        pdf.ln(8)
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 6, snapshot["notes"], align="L")

    output = pdf.output(dest="S")  # type: ignore[call-overload]
    # fpdf2 returns bytearray; older fpdf returns str. Normalise to bytes.
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)


async def generate_invoice_number(db: AsyncSession, tenant_id: UUID) -> str:
    """Return the next sequential invoice number for a tenant (INV-NNN)."""
    await set_tenant_in_session(db, tenant_id)
    result = await db.execute(
        select(Invoice.invoice_number).where(
            Invoice.tenant_id == tenant_id,
            Invoice.invoice_number.startswith("INV-"),
        )
    )
    max_number = 0
    prefix_len = len("INV-")
    for row in result.scalars().all():
        suffix = row[prefix_len:]
        if suffix.isdigit():
            max_number = max(max_number, int(suffix))
    return f"INV-{max_number + 1:03d}"


async def _get_invoice(db: AsyncSession, tenant_id: UUID, invoice_id: UUID) -> Invoice:
    await set_tenant_in_session(db, tenant_id)
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.payments),
            selectinload(Invoice.contact),
        )
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.get("")
async def list_invoices(tenant: TenantDep, db: DbDep) -> list[InvoiceRead]:
    """List invoices for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items), selectinload(Invoice.contact))
        .where(Invoice.tenant_id == tenant.id)
        .order_by(Invoice.issue_date.desc())
    )
    return [InvoiceRead.model_validate(i) for i in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    data: InvoiceCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Create an invoice with line items."""
    await set_tenant_in_session(db, tenant.id)

    contact = await db.get(Contact, data.contact_id)
    if contact is None or contact.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    if data.job_id:
        job = await db.get(Job, data.job_id)
        if job is None or job.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job")

    quote: Quote | None = None
    if data.quote_id:
        quote_result = await db.execute(
            select(Quote)
            .options(selectinload(Quote.line_items))
            .where(Quote.id == data.quote_id, Quote.tenant_id == tenant.id)
        )
        quote = quote_result.scalar_one_or_none()
        if quote is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quote")

    invoice_number = data.invoice_number or await generate_invoice_number(db, tenant.id)
    due_date = data.due_date or (datetime.utcnow() + timedelta(days=14))

    if quote is not None and not data.line_items:
        invoice = build_invoice_from_quote(quote, invoice_number, due_date)
    else:
        invoice = Invoice(
            tenant_id=tenant.id,
            contact_id=data.contact_id,
            job_id=data.job_id,
            quote_id=data.quote_id,
            invoice_number=invoice_number,
            due_date=due_date,
            vat_rate=data.vat_rate,
        )
        invoice.line_items = [
            InvoiceLineItem(tenant_id=tenant.id, **item.model_dump()) for item in data.line_items
        ]
        calculate_invoice_totals(invoice)

    db.add(invoice)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.INVOICE_CREATED,
        entity_type="invoice",
        entity_id=invoice.id,
        payload={
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
            "contact_id": str(invoice.contact_id),
        },
    )
    await db.commit()
    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: UUID, tenant: TenantDep, db: DbDep) -> InvoiceRead:
    """Get a single invoice."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    return InvoiceRead.model_validate(invoice)


@router.patch("/{invoice_id}")
async def update_invoice(
    invoice_id: UUID,
    data: InvoiceUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Update an invoice's due date, notes, or status."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    changed = data.model_dump(exclude_unset=True)
    for key, value in changed.items():
        setattr(invoice, key, value)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.INVOICE_UPDATED,
        entity_type="invoice",
        entity_id=invoice.id,
        payload={"changed_fields": sorted(changed.keys())},
    )
    await db.commit()
    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.post("/{invoice_id}/issue")
async def issue_invoice(
    invoice_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Mark an invoice as issued (ready for payment)."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    invoice.status = "sent"
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.INVOICE_ISSUED,
        entity_type="invoice",
        entity_id=invoice.id,
    )
    await db.commit()
    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.post("/{invoice_id}/send")
async def send_invoice(
    invoice_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Mark an invoice as sent to the customer and email them a copy."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    invoice.status = "sent"
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.INVOICE_SENT,
        entity_type="invoice",
        entity_id=invoice.id,
    )
    await db.commit()

    # Send email notification to the customer (best-effort; never fail the request).
    contact_email = invoice.contact.email if invoice.contact else None
    if contact_email:
        try:
            snapshot = _invoice_pdf_snapshot(invoice, tenant.name)
            pdf_bytes = await asyncio.to_thread(_render_invoice_pdf, snapshot)
            subject, html_body = render_invoice_sent_email(
                invoice_number=invoice.invoice_number,
                tenant_name=tenant.name,
                subtotal=invoice.subtotal,
                vat_amount=invoice.vat_amount,
                total=invoice.total,
                vat_rate=invoice.vat_rate,
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                customer_name=invoice.contact.name,
            )
            filename = f"invoice-{invoice.invoice_number}.pdf"
            await send_email(
                to_email=contact_email,
                subject=subject,
                html_body=html_body,
                attachments=[(filename, "application/pdf", pdf_bytes)],
            )
        except Exception:
            logger.warning(
                "Failed to send invoice email",
                exc_info=True,
                extra={"invoice_id": str(invoice.id), "tenant_id": str(tenant.id)},
            )

    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.post("/{invoice_id}/mark-paid")
async def mark_invoice_paid(
    invoice_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Mark an invoice as paid."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    invoice.status = "paid"
    invoice.paid_at = datetime.utcnow()
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.INVOICE_PAID,
        entity_type="invoice",
        entity_id=invoice.id,
        payload={"total": str(invoice.total)},
    )
    await db.commit()
    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Cancel an invoice."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    invoice.status = "cancelled"
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.INVOICE_CANCELLED,
        entity_type="invoice",
        entity_id=invoice.id,
    )
    await db.commit()
    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """Delete an invoice."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    snapshot = {"invoice_number": invoice.invoice_number, "total": str(invoice.total)}
    await db.delete(invoice)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.INVOICE_DELETED,
        entity_type="invoice",
        entity_id=invoice_id,
        payload=snapshot,
    )
    await db.commit()
