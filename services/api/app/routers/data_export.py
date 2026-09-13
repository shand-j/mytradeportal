"""Tenant data export ("no lock-in" trust feature, F3).

``GET /export/my-data`` returns a streaming JSON snapshot of everything the
authenticated tenant owns: business profile/settings, contacts, customer
accounts, quotes (with line items), jobs, invoices (with line items), and
communication history.

Isolation is enforced at two layers like every other staff endpoint: the
``TenantDep`` dependency pins the PostgreSQL RLS session GUC to the caller's
tenant, and every query additionally filters on ``tenant_id`` explicitly, so
a tenant can only ever receive their own rows.

The response shape is a stable contract — additive changes only:

.. code-block:: json

    {
      "format_version": "1.0",
      "generated_at": "<utc iso8601>",
      "tenant": {...},
      "contacts": [...],
      "customers": [...],
      "quotes": [{"line_items": [...], ...}],
      "jobs": [...],
      "invoices": [{"line_items": [...], ...}],
      "communications": [...]
    }

Secrets are never exported: password hashes, magic-link tokens, Paddle
checkout ids and similar credentials are deliberately excluded.
"""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies import ActiveUserDep, DbDep, TenantDep
from app.limiter import limiter, tenant_key
from app.models import (
    Communication,
    Contact,
    Customer,
    Invoice,
    InvoiceLineItem,
    Job,
    Quote,
    QuoteLineItem,
    Tenant,
)

router = APIRouter(prefix="/export", tags=["data-export"])

EXPORT_FORMAT_VERSION = "1.0"


def _iso(value: datetime | None) -> str | None:
    """Serialise a naive UTC datetime as ISO 8601 with a Z suffix."""
    if value is None:
        return None
    return f"{value.isoformat()}Z"


def _money(value: Decimal | None) -> str | None:
    """Serialise a Decimal as a plain string (no float rounding)."""
    return None if value is None else str(value)


def _uuid(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _tenant_dict(tenant: Tenant) -> dict[str, Any]:
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "code": tenant.code,
        "name": tenant.name,
        "status": tenant.status,
        "structure": tenant.structure,
        "year_established": tenant.year_established,
        "companies_house_number": tenant.companies_house_number,
        "nations_served": list(tenant.nations_served or []),
        "vat_registered": tenant.vat_registered,
        "vat_number": tenant.vat_number,
        "vat_scheme": tenant.vat_scheme,
        "quote_defaults": dict(tenant.quote_defaults or {}),
        "branding": dict(tenant.branding or {}),
        "settings": dict(tenant.settings or {}),
        "created_at": _iso(tenant.created_at),
        "updated_at": _iso(tenant.updated_at),
    }


def _contact_dict(contact: Contact) -> dict[str, Any]:
    return {
        "id": str(contact.id),
        "name": contact.name,
        "email": contact.email,
        "phone": contact.phone,
        "address": contact.address,
        "postcode": contact.postcode,
        "notes": contact.notes,
        "preferred_contact_method": contact.preferred_contact_method,
        "property_type": contact.property_type,
        "bedrooms": contact.bedrooms,
        "parking_notes": contact.parking_notes,
        "access_notes": contact.access_notes,
        "badge_overrides": dict(contact.badge_overrides or {}),
        "is_blocked": contact.is_blocked,
        "blocked_at": _iso(contact.blocked_at),
        "blocked_reason": contact.blocked_reason,
        "created_at": _iso(contact.created_at),
        "updated_at": _iso(contact.updated_at),
    }


def _customer_dict(customer: Customer) -> dict[str, Any]:
    # password_hash and magic_link_token are credentials, not exportable data.
    return {
        "id": str(customer.id),
        "contact_id": _uuid(customer.contact_id),
        "email": customer.email,
        "full_name": customer.full_name,
        "phone": customer.phone,
        "address": customer.address,
        "postcode": customer.postcode,
        "property_profile": dict(customer.property_profile or {}),
        "is_active": customer.is_active,
        "marketing_consent": customer.marketing_consent,
        "preferred_contact_method": customer.preferred_contact_method,
        "parking_notes": customer.parking_notes,
        "access_notes": customer.access_notes,
        "created_at": _iso(customer.created_at),
        "updated_at": _iso(customer.updated_at),
    }


def _quote_line_dict(line: QuoteLineItem) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "description": line.description,
        "quantity": _money(line.quantity),
        "unit": line.unit,
        "unit_price": _money(line.unit_price),
        "total": _money(line.total),
        "ai_generated": line.ai_generated,
        "created_at": _iso(line.created_at),
        "updated_at": _iso(line.updated_at),
    }


def _quote_dict(quote: Quote) -> dict[str, Any]:
    return {
        "id": str(quote.id),
        "contact_id": str(quote.contact_id),
        "title": quote.title,
        "description": quote.description,
        "status": quote.status,
        "subtotal": _money(quote.subtotal),
        "vat_rate": _money(quote.vat_rate),
        "vat_amount": _money(quote.vat_amount),
        "total": _money(quote.total),
        "rounding_adjustment": _money(quote.rounding_adjustment),
        "valid_until": _iso(quote.valid_until),
        "approved_at": _iso(quote.approved_at),
        "sent_at": _iso(quote.sent_at),
        "accepted_dates": list(quote.accepted_dates or []),
        "ai_metadata": dict(quote.ai_metadata or {}),
        "extra_data": dict(quote.extra_data or {}),
        "line_items": [_quote_line_dict(line) for line in quote.line_items],
        "created_at": _iso(quote.created_at),
        "updated_at": _iso(quote.updated_at),
    }


def _job_dict(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "contact_id": str(job.contact_id),
        "quote_id": _uuid(job.quote_id),
        "title": job.title,
        "description": job.description,
        "status": job.status,
        "scheduled_start": _iso(job.scheduled_start),
        "scheduled_end": _iso(job.scheduled_end),
        "completed_at": _iso(job.completed_at),
        "assigned_user_id": _uuid(job.assigned_user_id),
        "address": job.address,
        "postcode": job.postcode,
        "lat": _money(job.lat),
        "lng": _money(job.lng),
        "notes": job.notes,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }


def _invoice_line_dict(line: InvoiceLineItem) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "description": line.description,
        "quantity": _money(line.quantity),
        "unit_price": _money(line.unit_price),
        "total": _money(line.total),
        "created_at": _iso(line.created_at),
        "updated_at": _iso(line.updated_at),
    }


def _invoice_dict(invoice: Invoice) -> dict[str, Any]:
    # paddle_checkout_id / paddle_transaction_id are payment-provider
    # references, not tenant business data.
    return {
        "id": str(invoice.id),
        "contact_id": str(invoice.contact_id),
        "job_id": _uuid(invoice.job_id),
        "quote_id": _uuid(invoice.quote_id),
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "issue_date": _iso(invoice.issue_date),
        "due_date": _iso(invoice.due_date),
        "subtotal": _money(invoice.subtotal),
        "vat_rate": _money(invoice.vat_rate),
        "vat_amount": _money(invoice.vat_amount),
        "total": _money(invoice.total),
        "rounding_adjustment": _money(invoice.rounding_adjustment),
        "paid_at": _iso(invoice.paid_at),
        "notes": invoice.notes,
        "line_items": [_invoice_line_dict(line) for line in invoice.line_items],
        "created_at": _iso(invoice.created_at),
        "updated_at": _iso(invoice.updated_at),
    }


def _communication_dict(comm: Communication) -> dict[str, Any]:
    return {
        "id": str(comm.id),
        "contact_id": _uuid(comm.contact_id),
        "quote_request_id": _uuid(comm.quote_request_id),
        "channel": comm.channel,
        "direction": comm.direction,
        "sender_role": comm.sender_role,
        "subject": comm.subject,
        "body": comm.body,
        "status": comm.status,
        "created_at": _iso(comm.created_at),
        "updated_at": _iso(comm.updated_at),
    }


async def _build_export(tenant: Tenant, db: DbDep) -> dict[str, Any]:
    """Assemble the full export payload for one tenant."""
    contacts = (
        (
            await db.execute(
                select(Contact).where(Contact.tenant_id == tenant.id).order_by(Contact.created_at)
            )
        )
        .scalars()
        .all()
    )
    customers = (
        (
            await db.execute(
                select(Customer)
                .where(Customer.tenant_id == tenant.id)
                .order_by(Customer.created_at)
            )
        )
        .scalars()
        .all()
    )
    quotes = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.tenant_id == tenant.id)
                .options(selectinload(Quote.line_items))
                .order_by(Quote.created_at)
            )
        )
        .scalars()
        .all()
    )
    jobs = (
        (await db.execute(select(Job).where(Job.tenant_id == tenant.id).order_by(Job.created_at)))
        .scalars()
        .all()
    )
    invoices = (
        (
            await db.execute(
                select(Invoice)
                .where(Invoice.tenant_id == tenant.id)
                .options(selectinload(Invoice.line_items))
                .order_by(Invoice.created_at)
            )
        )
        .scalars()
        .all()
    )
    communications = (
        (
            await db.execute(
                select(Communication)
                .where(Communication.tenant_id == tenant.id)
                .order_by(Communication.created_at)
            )
        )
        .scalars()
        .all()
    )

    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "generated_at": _iso(datetime.utcnow()),
        "tenant": _tenant_dict(tenant),
        "contacts": [_contact_dict(c) for c in contacts],
        "customers": [_customer_dict(c) for c in customers],
        "quotes": [_quote_dict(q) for q in quotes],
        "jobs": [_job_dict(j) for j in jobs],
        "invoices": [_invoice_dict(i) for i in invoices],
        "communications": [_communication_dict(c) for c in communications],
    }


def _stream_json(payload: dict[str, Any]) -> AsyncIterator[str]:
    """Yield the JSON document in chunks so large exports stream."""

    async def _gen() -> AsyncIterator[str]:
        encoder = json.JSONEncoder()
        for chunk in encoder.iterencode(payload):
            yield chunk

    return _gen()


@router.get("/my-data")
@limiter.limit("6/hour", key_func=tenant_key)
async def export_my_data(
    request: Request,
    tenant: TenantDep,
    db: DbDep,
    user: ActiveUserDep,
) -> StreamingResponse:
    """Download a full JSON snapshot of the tenant's own data.

    Staff-only. Rate limited per tenant — an export is a full-table read, so
    a modest hourly budget keeps a misconfigured client from hammering the
    operational database.
    """
    payload = await _build_export(tenant, db)
    filename = f"mytradeportal-export-{tenant.slug}-{datetime.utcnow():%Y%m%d}.json"
    return StreamingResponse(
        _stream_json(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
