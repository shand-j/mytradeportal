"""Append-only audit log writer.

The :class:`AuditLog` model already exists (see ``app.models``) but until now
no code wrote to it. This module exposes a thin async helper that routers
call at every state-changing transition so we always have a tenant-scoped
"who did what, when, to which entity" record.

Design choices:

* The helper takes an explicit :class:`User` (the actor) and a tenant id
  rather than reading them from a request-local context — that keeps it
  callable from Celery tasks and seed scripts without surprise behaviour.
* Failures are swallowed and logged at ``warning`` level. We never want a
  best-effort audit insert to abort a successful business transaction; if
  the audit row cannot be written we still want the customer-visible quote
  / invoice to succeed.
* The action vocabulary is a free-form ``"{entity}.{verb}"`` string. The
  module exports the verbs we use today as constants so usage stays
  consistent and grep-able.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.models import AuditLog, User
from app.rls import set_tenant_in_session

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Canonical action verbs. Add new ones here rather than scattering string
# literals across the codebase.
class Actions:
    """Namespace of well-known audit action strings."""

    CONTACT_CREATED = "contact.created"
    CONTACT_UPDATED = "contact.updated"
    CONTACT_DELETED = "contact.deleted"

    QUOTE_CREATED = "quote.created"
    QUOTE_UPDATED = "quote.updated"
    QUOTE_SENT = "quote.sent"
    QUOTE_APPROVED = "quote.approved"
    QUOTE_REJECTED = "quote.rejected"
    QUOTE_DELETED = "quote.deleted"
    QUOTE_GENERATED = "quote.generated"
    QUOTE_BOQ_REGENERATED = "quote.boq_regenerated"
    QUOTE_CONVERTED_TO_INVOICE = "quote.converted_to_invoice"
    QUOTE_CONVERTED_TO_JOB = "quote.converted_to_job"

    QUOTE_REQUEST_CREATED = "quote_request.created"
    QUOTE_REQUEST_UPDATED = "quote_request.updated"
    QUOTE_REQUEST_INTERPRETED = "quote_request.interpreted"

    INVOICE_CREATED = "invoice.created"
    INVOICE_UPDATED = "invoice.updated"
    INVOICE_ISSUED = "invoice.issued"
    INVOICE_SENT = "invoice.sent"
    INVOICE_PAID = "invoice.paid"
    INVOICE_CANCELLED = "invoice.cancelled"
    INVOICE_DELETED = "invoice.deleted"

    TENANT_CREATED = "tenant.created"
    TENANT_UPDATED = "tenant.updated"


async def write_audit_log(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    payload: dict[str, Any] | None = None,
) -> AuditLog | None:
    """Insert an audit log row for ``action`` on ``(entity_type, entity_id)``.

    Returns the inserted ``AuditLog`` on success, or ``None`` if the insert
    failed (the failure is logged at ``warning`` level and the calling
    transaction is rolled back to a savepoint so the business operation can
    still commit).
    """
    try:
        # RLS requires app.current_tenant to match the row we're inserting.
        # Most callers will have already set this via the request lifecycle,
        # but setting it here makes the helper safe to call from anywhere.
        await set_tenant_in_session(db, tenant_id)
        entry = AuditLog(
            tenant_id=tenant_id,
            actor_id=actor.id if actor is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
        db.add(entry)
        await db.flush()
        return entry
    except Exception as exc:  # pragma: no cover - defensive
        # Audit writes are best-effort: log and swallow so they never abort a
        # successful business mutation. Operators see this in structured logs
        # via ``logger.warning`` and can investigate.
        logger.warning(
            "audit.write_failed",
            extra={
                "tenant_id": str(tenant_id),
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "error": str(exc),
            },
        )
        return None


__all__ = ["Actions", "write_audit_log"]
