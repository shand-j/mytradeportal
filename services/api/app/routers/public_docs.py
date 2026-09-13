"""Public, no-auth quote/invoice render endpoints.

Backs the secure customer-facing web pages on the landing site
(``/quote/{token}`` and ``/invoice/{token}``) for customers who do not have
the app. A :class:`~app.models.DocumentAccessToken` is minted when the
quote/invoice is emailed (``send_quote`` / ``send_invoice``); the raw token
only ever appears in that emailed link.

Security posture:

* Tokens are 256-bit random, stored SHA-256-hashed; the lookup is an exact
  match on the hash, so no timing signal distinguishes "unknown token" from
  "expired/revoked token".
* Every failure (unknown, expired, revoked, kind mismatch, deleted document)
  returns the same 404 — the endpoint never confirms a document exists.
* The payload is a deliberately narrow render model: no internal ids, no
  contact PII beyond a first name, no tenant secrets.
* Rate-limited per source IP.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any, Literal
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import stripe_client
from app.config import PUBLIC_DOCS_BASE_URL
from app.database import get_db
from app.limiter import limiter
from app.models import Contact, DocumentAccessToken, Invoice, Quote, StripeAccount, Tenant
from app.rls import bypass_rls_for_transaction

if TYPE_CHECKING:
    from uuid import UUID

router = APIRouter(prefix="/public", tags=["Public documents"])
logger = structlog.get_logger("api.public_docs")
DbDep = Annotated[AsyncSession, Depends(get_db)]

DOCUMENT_TOKEN_TTL_DAYS = 30
_TOKEN_BYTES = 32

DocumentKind = Literal["quote", "invoice"]


def hash_document_token(raw: str) -> str:
    """SHA-256 of the raw bearer token — only this digest is persisted."""
    return hashlib.sha256(raw.encode()).hexdigest()


def public_document_url(kind: DocumentKind, raw_token: str) -> str:
    """Absolute landing-site URL for a freshly minted document token."""
    return f"{PUBLIC_DOCS_BASE_URL}/{kind}/{raw_token}"


async def issue_document_token(
    db: AsyncSession,
    *,
    kind: DocumentKind,
    document_id: UUID,
    tenant_id: UUID,
    contact_email: str | None,
) -> str:
    """Mint a document access token and return the raw value for the email link.

    Revokes any still-valid earlier tokens for the same document so only the
    newest emailed link opens it (the document may have changed between
    sends). The caller commits with the rest of the send transaction.
    """
    await db.execute(
        update(DocumentAccessToken)
        .where(
            DocumentAccessToken.kind == kind,
            DocumentAccessToken.document_id == document_id,
            DocumentAccessToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.utcnow())
    )
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    db.add(
        DocumentAccessToken(
            tenant_id=tenant_id,
            kind=kind,
            document_id=document_id,
            token_hash=hash_document_token(raw),
            contact_email=contact_email,
            expires_at=datetime.utcnow() + timedelta(days=DOCUMENT_TOKEN_TTL_DAYS),
        )
    )
    await db.flush()
    return raw


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _first_name(full_name: str | None) -> str:
    return full_name.split()[0] if full_name else "there"


def _tenant_block(tenant: Tenant) -> dict[str, Any]:
    return {
        "name": tenant.name,
        "brand_color": tenant.primary_color,
        "logo_url": tenant.logo_url,
        "reply_email": tenant.email or None,
    }


async def _load_token(db: AsyncSession, kind: str, raw_token: str) -> DocumentAccessToken:
    """Resolve a raw token to its row, or raise an indistinguishable 404."""
    record = await db.scalar(
        select(DocumentAccessToken).where(
            DocumentAccessToken.token_hash == hash_document_token(raw_token)
        )
    )
    if (
        record is None
        or record.kind != kind
        or record.revoked_at is not None
        or record.expires_at < datetime.utcnow()
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return record


_OPEN_INTENT_STATUSES = frozenset(
    {"requires_payment_method", "requires_confirmation", "requires_action"}
)


def _invoice_accepts_card(invoice: Invoice, tenant: Tenant) -> bool:
    """Resolve the per-invoice override against the tenant settings default.

    Mirrors ``app.routers.payments.invoice_accepts_card`` (re-implemented here
    to keep this module free of router→router import cycles).
    """
    if invoice.accept_card_payments is not None:
        return invoice.accept_card_payments
    payments = (tenant.settings or {}).get("payments") or {}
    return bool(payments.get("accept_card_default", False))


async def _invoice_payment_url(
    db: AsyncSession, invoice: Invoice, tenant: Tenant, raw_token: str
) -> str | None:
    """Stripe /pay URL for an unpaid invoice, or None.

    Card payment is offered only when Stripe is configured, the tenant has a
    charges-enabled Connect account, and the invoice (or tenant default) opts
    in. An open PaymentIntent for the current total is reused; otherwise a new
    destination charge is created and persisted on the invoice. Everything is
    best-effort: a Stripe outage or misconfiguration must never break document
    viewing, so any failure degrades to ``null`` (the page omits the Pay
    button).

    URL contract for the landing /pay page (ships separately):
    ``{PUBLIC_DOCS_BASE_URL}/pay/{doc_token}?pi={payment_intent_id}
    &cs={payment_intent_client_secret}`` — the page confirms the intent with
    Stripe.js using the client secret; no card data touches our servers.
    """
    if invoice.status in {"paid", "cancelled", "refunded"}:
        return None
    if not stripe_client.is_configured():
        return None
    if not _invoice_accepts_card(invoice, tenant):
        return None
    try:
        account = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant.id))
        if account is None or not account.charges_enabled:
            return None

        amount_pence = int((invoice.total * 100).quantize(Decimal("1")))
        intent: dict[str, Any] | None = None
        if invoice.stripe_payment_intent_id:
            existing = await stripe_client.retrieve_payment_intent(invoice.stripe_payment_intent_id)
            if existing["status"] in _OPEN_INTENT_STATUSES and existing["amount"] == amount_pence:
                intent = existing
        if intent is None:
            intent = await stripe_client.create_payment_intent(
                amount_pence=amount_pence,
                currency="gbp",
                connected_account_id=account.stripe_account_id,
                invoice_id=str(invoice.id),
                tenant_id=str(tenant.id),
            )
            invoice.stripe_payment_intent_id = str(intent["id"])
            await db.commit()

        query = urlencode({"pi": str(intent["id"]), "cs": str(intent["client_secret"])})
        return f"{PUBLIC_DOCS_BASE_URL}/pay/{raw_token}?{query}"
    except Exception:
        logger.warning("public_doc_payment_url_failed", invoice_id=str(invoice.id))
        return None


@router.get("/{kind}/{token}")
@limiter.limit("60/hour")
async def get_public_document(
    request: Request,
    kind: str,
    token: str,
    db: DbDep,
) -> dict[str, Any]:
    """Return the safe render payload for a quote/invoice access token."""
    if kind not in ("quote", "invoice"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await bypass_rls_for_transaction(db)
    record = await _load_token(db, kind, token)

    tenant = await db.get(Tenant, record.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    payload: dict[str, Any] = {
        "kind": kind,
        "tenant": _tenant_block(tenant),
        "currency": "GBP",
        "payment_url": None,
    }

    if kind == "quote":
        quote = await db.scalar(
            select(Quote)
            .where(Quote.id == record.document_id)
            .options(selectinload(Quote.line_items))
        )
        if quote is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        contact = await db.get(Contact, quote.contact_id)
        payload.update(
            {
                "status": quote.status,
                "title": quote.title,
                "description": quote.description,
                "invoice_number": None,
                "customer_first_name": _first_name(contact.name if contact else None),
                "lines": [
                    {
                        "description": line.description,
                        "quantity": str(line.quantity),
                        "unit": line.unit,
                        "unit_price": str(line.unit_price),
                        "total": str(line.total),
                    }
                    for line in quote.line_items
                ],
                "subtotal": _money(quote.subtotal),
                "vat_rate": str(quote.vat_rate),
                "vat_amount": _money(quote.vat_amount),
                "total": _money(quote.total),
                "sent_at": quote.sent_at.isoformat() if quote.sent_at else None,
                "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
                "due_date": None,
                "paid_at": None,
            }
        )
        return payload

    invoice = await db.scalar(
        select(Invoice)
        .where(Invoice.id == record.document_id)
        .options(selectinload(Invoice.line_items))
    )
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    contact = await db.get(Contact, invoice.contact_id)
    payload.update(
        {
            "status": invoice.status,
            "title": None,
            "description": invoice.notes,
            "invoice_number": invoice.invoice_number,
            "customer_first_name": _first_name(contact.name if contact else None),
            "lines": [
                {
                    "description": line.description,
                    "quantity": str(line.quantity),
                    "unit": "ea",
                    "unit_price": str(line.unit_price),
                    "total": str(line.total),
                }
                for line in invoice.line_items
            ],
            "subtotal": _money(invoice.subtotal),
            "vat_rate": str(invoice.vat_rate),
            "vat_amount": _money(invoice.vat_amount),
            "total": _money(invoice.total),
            "sent_at": invoice.issue_date.isoformat() if invoice.issue_date else None,
            "valid_until": None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            "payment_url": await _invoice_payment_url(db, invoice, tenant, token),
        }
    )
    return payload
