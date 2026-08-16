"""Quote endpoints."""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import Actions, write_audit_log
from app.calculations import build_invoice_from_quote, calculate_quote_totals
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.limiter import limiter, tenant_key
from app.models import BillOfQuantities, Contact, Quote, QuoteLineItem
from app.rag import generate_quote_from_prompt, search_cost_items, validate_generated_quote
from app.rag.validation import build_quote_from_validation
from app.rls import set_tenant_in_session
from app.routers.invoices import _get_invoice, generate_invoice_number
from app.schemas import (
    InvoiceRead,
    QuoteApprove,
    QuoteConvertToInvoice,
    QuoteCreate,
    QuoteGenerateRequest,
    QuoteRead,
    QuoteUpdate,
)

router = APIRouter(prefix="/quotes", tags=["Quotes"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
MONEY_QUANTIZE = Decimal("0.01")
logger = logging.getLogger(__name__)


async def _get_quote(db: AsyncSession, tenant_id: UUID, quote_id: UUID) -> Quote:
    await set_tenant_in_session(db, tenant_id)
    result = await db.execute(
        select(Quote)
        .options(
            selectinload(Quote.line_items),
            selectinload(Quote.contact),
            selectinload(Quote.bill_of_quantities).selectinload(BillOfQuantities.line_items),
        )
        .where(Quote.id == quote_id, Quote.tenant_id == tenant_id)
    )
    quote = result.scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return quote


@router.get("")
async def list_quotes(tenant: TenantDep, db: DbDep) -> list[QuoteRead]:
    """List quotes for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(
        select(Quote)
        .options(
            selectinload(Quote.line_items),
            selectinload(Quote.contact),
            selectinload(Quote.bill_of_quantities).selectinload(BillOfQuantities.line_items),
        )
        .where(Quote.tenant_id == tenant.id)
        .order_by(Quote.created_at.desc())
    )
    return [QuoteRead.model_validate(q) for q in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_quote(
    data: QuoteCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Create a quote with line items."""
    await set_tenant_in_session(db, tenant.id)

    contact = await db.get(Contact, data.contact_id)
    if contact is None or contact.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    quote = Quote(
        tenant_id=tenant.id,
        contact_id=data.contact_id,
        title=data.title,
        description=data.description,
        vat_rate=data.vat_rate,
        valid_until=data.valid_until,
    )
    quote.line_items = [
        QuoteLineItem(tenant_id=tenant.id, **item.model_dump()) for item in data.line_items
    ]
    calculate_quote_totals(quote)

    db.add(quote)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_CREATED,
        entity_type="quote",
        entity_id=quote.id,
        payload={"title": quote.title, "total": str(quote.total)},
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.get("/{quote_id}")
async def get_quote(quote_id: UUID, tenant: TenantDep, db: DbDep) -> QuoteRead:
    """Get a single quote."""
    quote = await _get_quote(db, tenant.id, quote_id)
    return QuoteRead.model_validate(quote)


@router.patch("/{quote_id}")
async def update_quote(
    quote_id: UUID,
    data: QuoteUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Update a quote's details, status, or line items."""
    quote = await _get_quote(db, tenant.id, quote_id)
    update_data = data.model_dump(exclude_unset=True)

    if "line_items" in update_data:
        new_items = update_data.pop("line_items")
        for item in list(quote.line_items):
            await db.delete(item)
        quote.line_items = [QuoteLineItem(tenant_id=tenant.id, **item) for item in new_items]
        calculate_quote_totals(quote)

    for key, value in update_data.items():
        setattr(quote, key, value)

    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_UPDATED,
        entity_type="quote",
        entity_id=quote.id,
        payload={"changed_fields": sorted(data.model_dump(exclude_unset=True).keys())},
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/send")
async def send_quote(
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Mark a quote as sent."""
    quote = await _get_quote(db, tenant.id, quote_id)
    quote.status = "sent"
    quote.sent_at = datetime.utcnow()
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_SENT,
        entity_type="quote",
        entity_id=quote.id,
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/reject")
async def reject_quote(
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Mark a quote as rejected."""
    quote = await _get_quote(db, tenant.id, quote_id)
    quote.status = "rejected"
    quote.approved_at = None
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_REJECTED,
        entity_type="quote",
        entity_id=quote.id,
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/approve")
async def approve_quote(
    quote_id: UUID,
    data: QuoteApprove,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Approve or reject a quote."""
    quote = await _get_quote(db, tenant.id, quote_id)
    if data.approved:
        quote.status = "approved"
        quote.approved_at = datetime.utcnow()
        action = Actions.QUOTE_APPROVED
    else:
        quote.status = "rejected"
        quote.approved_at = None
        action = Actions.QUOTE_REJECTED
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=action,
        entity_type="quote",
        entity_id=quote.id,
        payload={"approved": data.approved},
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/{quote_id}/refine")
async def refine_quote(quote_id: UUID, tenant: TenantDep, db: DbDep) -> QuoteRead:
    """Placeholder endpoint for AI-driven quote refinement."""
    quote = await _get_quote(db, tenant.id, quote_id)
    return QuoteRead.model_validate(quote)


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """Delete a quote."""
    quote = await _get_quote(db, tenant.id, quote_id)
    snapshot = {"title": quote.title, "status": quote.status, "total": str(quote.total)}
    await db.delete(quote)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_DELETED,
        entity_type="quote",
        entity_id=quote_id,
        payload=snapshot,
    )
    await db.commit()


async def _generate_rag_quote(
    quote: Quote,
    data: QuoteGenerateRequest,
    tenant: TenantDep,
) -> None:
    """Populate a quote using the faster RAG path (retrieval + LLM)."""
    retrieved = await search_cost_items(data.description)
    generated = await generate_quote_from_prompt(
        job_description=data.description,
        cost_items=retrieved,
        tenant_settings=tenant.settings,
        property_type=data.property_type,
    )
    validated = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings=tenant.settings,
    )
    build_quote_from_validation(quote, validated)
    if not quote.line_items:
        raise RuntimeError(
            "No priced line items were generated. "
            "Cost catalogue items were not resolved for this job."
        )


async def _generate_quote_impl(
    data: QuoteGenerateRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Shared implementation for the quote-generation routes.

    Kept decorator-free: slowapi fires on internal calls too, so routes must
    wrap this rather than calling each other, or one request debits the
    tenant's rate-limit bucket twice.
    """
    await set_tenant_in_session(db, tenant.id)

    if data.contact_id:
        contact = await db.get(Contact, data.contact_id)
        if contact is None or contact.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")
    else:
        contact = Contact(
            tenant_id=tenant.id,
            name=data.customer_name or "Generated lead",
            email=data.customer_email,
            phone=data.customer_phone,
        )
        db.add(contact)
        await db.flush()
        await db.refresh(contact)

    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title=data.description[:80],
        description=data.description,
    )

    try:
        await _generate_rag_quote(quote, data, tenant)
        if not quote.line_items:
            raise RuntimeError(
                "No priced line items were generated. Ensure the cost catalogue is loaded "
                "and tenant labour-rate settings are configured."
            )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    db.add(quote)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_GENERATED,
        entity_type="quote",
        entity_id=quote.id,
        payload={
            "backend": "rag",
            "description_chars": len(data.description or ""),
            "property_type": data.property_type,
            "total": str(quote.total),
        },
    )
    await db.commit()
    return QuoteRead.model_validate(await _get_quote(db, tenant.id, quote.id))


@router.post("/generate", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute", key_func=tenant_key)
async def generate_quote(
    request: Request,
    data: QuoteGenerateRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """Generate a draft quote from a natural-language job description.

    Rate limited to 10 generations per minute per tenant — LLM + OCERP calls
    are expensive and a runaway client can otherwise exhaust the budget.
    """
    return await _generate_quote_impl(data, tenant, current_user, db)


@router.post("/generate-boq", status_code=status.HTTP_501_NOT_IMPLEMENTED)
@limiter.limit("10/minute", key_func=tenant_key)
async def generate_boq_quote(
    request: Request,
    data: QuoteGenerateRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRead:
    """OCERP / BoQ generation is parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OCERP / BoQ generation is parked for the mobile-pivot MVP. Use /quotes/generate instead.",
    )


@router.get("/{quote_id}/boq")
async def get_quote_boq(quote_id: UUID, tenant: TenantDep, db: DbDep) -> None:
    """OCERP / BoQ endpoints are parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="BoQ endpoints are parked for the mobile-pivot MVP.",
    )


@router.patch("/{quote_id}/boq")
async def update_quote_boq(
    quote_id: UUID,
    data: QuoteUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """OCERP / BoQ endpoints are parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="BoQ endpoints are parked for the mobile-pivot MVP.",
    )


@router.post(
    "/{quote_id}/boq/regenerate",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
@limiter.limit("10/minute", key_func=tenant_key)
async def regenerate_quote_boq(
    request: Request,
    quote_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """OCERP / BoQ endpoints are parked for the mobile-pivot MVP."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="BoQ endpoints are parked for the mobile-pivot MVP.",
    )


@router.post(
    "/{quote_id}/convert-to-invoice",
    status_code=status.HTTP_201_CREATED,
)
async def convert_quote_to_invoice(
    quote_id: UUID,
    data: QuoteConvertToInvoice,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> InvoiceRead:
    """Convert a quote into a draft invoice."""
    quote = await _get_quote(db, tenant.id, quote_id)

    if quote.status in {"invoiced", "cancelled", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote cannot be converted to an invoice",
        )
    if not quote.line_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote has no line items",
        )

    invoice_number = data.invoice_number or await generate_invoice_number(db, tenant.id)
    due_date = data.due_date or (datetime.utcnow() + timedelta(days=14))

    invoice = build_invoice_from_quote(quote, invoice_number, due_date)
    quote.status = "invoiced"

    db.add(invoice)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_CONVERTED_TO_INVOICE,
        entity_type="quote",
        entity_id=quote.id,
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
        },
    )
    await db.commit()
    return InvoiceRead.model_validate(await _get_invoice(db, tenant.id, invoice.id))


@router.get("/{quote_id}/pdf")
async def quote_pdf(quote_id: UUID, tenant: TenantDep, db: DbDep) -> StreamingResponse:
    """Generate a PDF version of a quote.

    FPDF is synchronous I/O and blocks the event loop for tens to hundreds of
    milliseconds per quote — long enough to stall every other request on the
    same worker. We snapshot the ORM data into plain dicts first (no lazy
    loading from inside the thread) and then build the PDF in a worker
    thread via :func:`asyncio.to_thread`.
    """
    quote = await _get_quote(db, tenant.id, quote_id)
    snapshot = _quote_pdf_snapshot(quote, tenant.name)
    pdf_bytes = await asyncio.to_thread(_render_quote_pdf, snapshot)

    buffer = BytesIO(pdf_bytes)
    buffer.seek(0)
    filename = f"quote-{quote.id}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


def _quote_pdf_snapshot(quote: Quote, tenant_name: str) -> dict[str, Any]:
    """Pre-materialise everything the PDF renderer needs as plain primitives.

    Done on the asyncio thread (where the AsyncSession lives) so the
    threadpool job never accidentally triggers an ORM lazy-load — which
    would crash with a "greenlet_spawn has not been called" error.
    """
    snapshot_line_items = [
        {
            "description": li.description,
            "quantity": float(li.quantity),
            "unit_price": float(li.unit_price),
            "total": float(li.total),
        }
        for li in quote.line_items
    ]

    boq = quote.bill_of_quantities
    if boq and boq.customer_summary_lines:
        snapshot_line_items = [
            {
                "description": str(item.get("description", "")),
                "quantity": 1.0,
                "unit_price": float(item.get("total", 0) or 0),
                "total": float(item.get("total", 0) or 0),
            }
            for item in boq.customer_summary_lines
        ]

    return {
        "id": str(quote.id),
        "tenant_name": tenant_name,
        "title": quote.title,
        "status": quote.status,
        "created_at": quote.created_at,
        "subtotal": float(quote.subtotal),
        "vat_rate": float(quote.vat_rate),
        "vat_amount": float(quote.vat_amount),
        "total": float(quote.total),
        "contact": {
            "name": quote.contact.name,
            "email": quote.contact.email,
            "phone": quote.contact.phone,
        },
        "line_items": snapshot_line_items,
    }


def _render_quote_pdf(snapshot: dict[str, Any]) -> bytes:
    """Render a quote PDF from a pre-materialised snapshot.

    Pure-sync, no ORM, safe to call from a worker thread.
    """
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, snapshot["tenant_name"], ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, "Quote", ln=True)  # type: ignore[arg-type]
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Customer details
    contact = snapshot["contact"]
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Customer", ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, contact["name"], ln=True)  # type: ignore[arg-type]
    if contact["email"]:
        pdf.cell(0, 8, contact["email"], ln=True)  # type: ignore[arg-type]
    if contact["phone"]:
        pdf.cell(0, 8, contact["phone"], ln=True)  # type: ignore[arg-type]
    pdf.ln(5)

    # Quote summary
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, snapshot["title"], ln=True)  # type: ignore[arg-type]
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {snapshot['created_at'].strftime('%d/%m/%Y')}", ln=True)  # type: ignore[arg-type]
    pdf.cell(0, 6, f"Status: {snapshot['status'].upper()}", ln=True)  # type: ignore[arg-type]
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
    pdf.cell(0, 8, f"Subtotal: £{snapshot['subtotal']:,.2f}", ln=True, align="R")  # type: ignore[arg-type]
    vat_label = f"VAT ({snapshot['vat_rate'] * 100:.0f}%): £{snapshot['vat_amount']:,.2f}"
    pdf.cell(0, 8, vat_label, ln=True, align="R")  # type: ignore[arg-type]
    pdf.cell(0, 8, f"Total: £{snapshot['total']:,.2f}", ln=True, align="R")  # type: ignore[arg-type]

    output = pdf.output(dest="S")  # type: ignore[call-overload]
    # fpdf2 returns bytearray; older fpdf returns str. Normalise to bytes.
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
