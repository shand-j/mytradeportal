"""Invoice endpoints."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai_telemetry import record_quote_outcome
from app.audit import Actions, write_audit_log
from app.calculations import build_invoice_from_quote, calculate_invoice_totals, tenant_vat_rate
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.email import send_email
from app.email_templates import invoice_sent as invoice_sent_template
from app.models import Contact, Invoice, InvoiceLineItem, Job, Quote, QuoteRequest, Tenant
from app.push import notify_customer, notify_staff
from app.rls import set_tenant_in_session
from app.schemas import InvoiceCreate, InvoiceRead, InvoiceUpdate

router = APIRouter(prefix="/invoices", tags=["Invoices"])
logger = structlog.get_logger("api.invoices")
DbDep = Annotated[AsyncSession, Depends(get_db)]


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


def _tenant_payment_details(
    settings: dict[str, Any] | None, *, reference: str
) -> dict[str, str] | None:
    """Build the bank-transfer block for the invoice email from tenant settings.

    The payment reference defaults to the invoice number so the customer can
    always reconcile the transfer. Returns None when no bank details are
    configured so the email omits the block entirely.
    """
    if not settings:
        return None
    details = {
        "account_name": str(settings.get("bank_account_name", "") or ""),
        "sort_code": str(settings.get("bank_sort_code", "") or ""),
        "account_number": str(settings.get("bank_account_number", "") or ""),
        "reference": reference,
    }
    if not any(details[key] for key in ("account_name", "sort_code", "account_number")):
        return None
    return details


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

    job: Job | None = None
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
            # InvoiceCreate.vat_rate defaults to 0.20, so "not sent" is only
            # detectable via model_fields_set — otherwise non-VAT-registered
            # tenants would never fall through to their 0% rate.
            vat_rate=(
                data.vat_rate if "vat_rate" in data.model_fields_set else tenant_vat_rate(tenant)
            ),
        )
        # When the caller did not supply line items, derive a sensible default from
        # the source record so the invoice is not empty. This happens when the
        # electrician taps "Create invoice" from a completed job without adding
        # manual line items in the app.
        if not data.line_items and job is not None:
            invoice.line_items = [
                InvoiceLineItem(
                    tenant_id=tenant.id,
                    description=job.title,
                    quantity=Decimal("1"),
                    unit_price=Decimal("0.00"),
                )
            ]
        else:
            invoice.line_items = [
                InvoiceLineItem(tenant_id=tenant.id, **item.model_dump())
                for item in data.line_items
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
    """Update an invoice's due date, notes, status, or line items."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    changed = data.model_dump(exclude_unset=True)

    if "line_items" in changed:
        # Full replacement, mirroring update_quote; totals recalculated.
        new_items = changed.pop("line_items")
        for item in list(invoice.line_items):
            await db.delete(item)
        invoice.line_items = [InvoiceLineItem(tenant_id=tenant.id, **item) for item in new_items]
        calculate_invoice_totals(invoice)

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
    """Mark an invoice as sent to the customer (in-app + email notification)."""
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

    # Notify the linked customer (in-app + push) and email the contact.
    customer_id = None
    if invoice.quote_id is not None:
        linked_request = await db.scalar(
            select(QuoteRequest).where(QuoteRequest.quote_id == invoice.quote_id)
        )
        if linked_request is not None:
            customer_id = linked_request.customer_id
    if customer_id is not None:
        await notify_customer(
            db,
            tenant.id,
            customer_id,
            kind="invoice_sent",
            title="Invoice ready",
            body=f"Invoice {invoice.invoice_number} is ready — £{invoice.total}.",
            link=f"/customer/invoice/{invoice.id}",
        )
    contact = await db.get(Contact, invoice.contact_id)
    tenant_row = await db.get(Tenant, tenant.id)
    if contact is not None and contact.email:
        business_name = tenant_row.name if tenant_row is not None else "Your electrician"
        payment_details = _tenant_payment_details(
            tenant_row.settings if tenant_row is not None else None,
            reference=invoice.invoice_number,
        )
        subject, html, text = invoice_sent_template(
            customer_name=contact.name.split()[0] if contact.name else "there",
            business_name=business_name,
            invoice_number=invoice.invoice_number,
            invoice_total=f"£{invoice.total}",
            payment_details=payment_details,
        )
        try:
            await send_email(
                to_email=contact.email,
                subject=subject,
                html_body=html,
                text_body=text,
                from_name=business_name,
                reply_to=tenant_row.email if tenant_row is not None and tenant_row.email else None,
            )
        except Exception:
            logger.warning("invoice_email_failed", invoice_id=str(invoice.id))

    await db.commit()
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
    await notify_staff(
        db,
        tenant.id,
        kind="invoice_paid",
        title="Invoice paid",
        body=f"Invoice {invoice.invoice_number} for £{invoice.total} has been marked paid.",
        link=f"/invoices/{invoice.id}",
    )
    # Close the AI funnel when the invoice traces back to an AI-drafted quote.
    if invoice.quote_id is not None:
        source_quote = await db.get(Quote, invoice.quote_id)
        if source_quote is not None:
            await record_quote_outcome(
                db,
                outcome="invoice_paid",
                tenant_id=tenant.id,
                quote=source_quote,
                user_id=current_user.id if current_user is not None else None,
                extra_payload={"invoice_id": str(invoice.id), "actor": "staff"},
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
