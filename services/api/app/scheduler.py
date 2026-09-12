"""In-process quote/invoice reminder scheduler.

Runs as an asyncio task started from the FastAPI lifespan — no extra infra
(no Celery beat, no APScheduler dependency). A single sweep
(:func:`run_reminder_tick`) walks every active tenant and dispatches:

* **Quote reminders** — for quotes in ``sent`` status the customer has not
  answered. Default 3 reminders, then stop. Count and cadence are
  configurable per tenant via settings keys (see below).
* **Invoice reminders** — for unpaid invoices in ``sent`` status. Recur
  indefinitely until the invoice is paid/cancelled. Cadence is configurable.

Dispatch state lives in the ``reminders`` table (:class:`app.models.Reminder`):
one row per sent email. The row count per entity is the "how many have gone
out" state and the latest row's timestamp anchors the next interval, so the
scheduler is stateless and safe to restart at any point.

Concurrency: multiple API replicas each run this loop. Each tenant is
processed inside a transaction that first takes a PostgreSQL transaction-level
advisory lock keyed on the tenant, so only one worker ever chases a tenant at
a time; the others skip it for that sweep.

Tenant settings keys (merged via ``PATCH /tenants/me``):

* ``quote_reminders_enabled`` (bool, default true)
* ``quote_reminder_max`` (int, default 3)
* ``quote_reminder_interval_days`` (int, default 3)
* ``invoice_reminders_enabled`` (bool, default true)
* ``invoice_reminder_interval_days`` (int, default 7)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select, text

from app.audit import Actions, write_audit_log
from app.config import REMINDER_TICK_SECONDS
from app.config import settings as app_settings
from app.database import AsyncSessionLocal
from app.email import send_event_email
from app.email_templates import invoice_reminder as invoice_reminder_template
from app.email_templates import quote_reminder as quote_reminder_template
from app.models import Contact, Invoice, Quote, Reminder, Tenant
from app.push import notify_staff
from app.rls import set_tenant_in_session
from app.routers.invoices import _tenant_payment_details

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("api.scheduler")

# Advisory-lock namespace for the reminder scheduler (arbitrary constant so we
# never collide with other advisory-lock users in this database).
_LOCK_NAMESPACE = 727


def _bool_setting(settings: dict[str, Any], key: str, default: bool) -> bool:
    value = settings.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int_setting(
    settings: dict[str, Any], key: str, default: int, minimum: int, maximum: int
) -> int:
    try:
        value = int(str(settings.get(key, default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


class _ReminderConfig:
    """Per-tenant reminder cadence resolved from the settings dict."""

    def __init__(self, settings: dict[str, Any] | None) -> None:
        s = settings or {}
        self.quote_enabled = _bool_setting(s, "quote_reminders_enabled", True)
        self.quote_max = _int_setting(s, "quote_reminder_max", 3, 1, 10)
        self.quote_interval_days = _int_setting(s, "quote_reminder_interval_days", 3, 1, 90)
        self.invoice_enabled = _bool_setting(s, "invoice_reminders_enabled", True)
        self.invoice_interval_days = _int_setting(s, "invoice_reminder_interval_days", 7, 1, 90)


async def _reminder_state(
    db: AsyncSession, entity_type: str, entity_id: UUID
) -> tuple[int, datetime | None]:
    """Return (reminders sent so far, timestamp of the most recent one)."""
    count, last_sent = (
        await db.execute(
            select(func.count(Reminder.id), func.max(Reminder.created_at)).where(
                Reminder.entity_type == entity_type,
                Reminder.entity_id == entity_id,
            )
        )
    ).one()
    return count or 0, last_sent


def _quote_view_url(quote: Quote) -> str:
    origin = app_settings.app_public_url.rstrip("/") if app_settings.app_public_url else ""
    return f"{origin}/customer/quote/{quote.id}" if origin else f"/customer/quote/{quote.id}"


async def _process_quote_reminders(
    db: AsyncSession, tenant: Tenant, config: _ReminderConfig, now: datetime
) -> int:
    """Send due quote reminders for one tenant. Returns the number sent."""
    if not config.quote_enabled:
        return 0
    sent = 0
    interval = timedelta(days=config.quote_interval_days)
    quotes = (
        (
            await db.execute(
                select(Quote).where(
                    Quote.tenant_id == tenant.id,
                    Quote.status == "sent",
                    Quote.sent_at.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for quote in quotes:
        # An expired quote should not be chased further.
        if quote.valid_until is not None and quote.valid_until < now:
            continue
        count, last_sent = await _reminder_state(db, "quote", quote.id)
        if count >= config.quote_max:
            continue
        anchor = last_sent or quote.sent_at
        if anchor is None or now - anchor < interval:
            continue

        contact = await db.get(Contact, quote.contact_id)
        subject, html, text = quote_reminder_template(
            customer_name=contact.name.split()[0]
            if contact is not None and contact.name
            else "there",
            business_name=tenant.name,
            quote_title=quote.title,
            quote_total=f"£{quote.total}",
            view_url=_quote_view_url(quote),
        )
        delivered = await send_event_email(
            to_email=contact.email if contact is not None else None,
            subject=subject,
            html_body=html,
            text_body=text,
            event="quote_reminder",
            template="quote_reminder",
            from_name=tenant.name,
            reply_to=tenant.email or None,
            context={"quote_id": str(quote.id), "tenant_id": str(tenant.id)},
        )
        if not delivered:
            # Not recorded as a reminder: a customer we could not reach must
            # not burn one of their chase slots. send_event_email already
            # logged the skip/failure loudly.
            continue

        sequence = count + 1
        db.add(
            Reminder(
                tenant_id=tenant.id,
                entity_type="quote",
                entity_id=quote.id,
                channel="email",
                sequence=sequence,
                payload={"quote_id": str(quote.id), "total": str(quote.total)},
            )
        )
        await notify_staff(
            db,
            tenant.id,
            kind="quote_reminder_sent",
            title="Quote reminder sent",
            body=f"Reminder {sequence} of {config.quote_max} emailed to "
            f"{contact.name if contact is not None else 'the customer'} for '{quote.title}'.",
            link=f"/quotes/{quote.id}",
        )
        await write_audit_log(
            db,
            tenant_id=tenant.id,
            actor=None,
            action=Actions.QUOTE_REMINDER_SENT,
            entity_type="quote",
            entity_id=quote.id,
            payload={"sequence": sequence, "max": config.quote_max},
        )
        sent += 1
    return sent


async def _process_invoice_reminders(
    db: AsyncSession, tenant: Tenant, config: _ReminderConfig, now: datetime
) -> int:
    """Send due invoice reminders for one tenant. Returns the number sent."""
    if not config.invoice_enabled:
        return 0
    sent = 0
    interval = timedelta(days=config.invoice_interval_days)
    invoices = (
        (
            await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant.id,
                    Invoice.status == "sent",
                )
            )
        )
        .scalars()
        .all()
    )
    for invoice in invoices:
        count, last_sent = await _reminder_state(db, "invoice", invoice.id)
        # First reminder fires one interval after the due date (falling back
        # to the issue date when no due date was set); subsequent ones recur
        # every interval after the previous reminder, indefinitely.
        anchor = last_sent or invoice.due_date or invoice.issue_date
        if anchor is None or now - anchor < interval:
            continue

        contact = await db.get(Contact, invoice.contact_id)
        sequence = count + 1
        subject, html, text = invoice_reminder_template(
            customer_name=contact.name.split()[0]
            if contact is not None and contact.name
            else "there",
            business_name=tenant.name,
            invoice_number=invoice.invoice_number,
            invoice_total=f"£{invoice.total}",
            payment_details=_tenant_payment_details(
                tenant.settings, reference=invoice.invoice_number
            ),
        )
        delivered = await send_event_email(
            to_email=contact.email if contact is not None else None,
            subject=subject,
            html_body=html,
            text_body=text,
            event="invoice_reminder",
            template="invoice_reminder",
            from_name=tenant.name,
            reply_to=tenant.email or None,
            context={"invoice_id": str(invoice.id), "tenant_id": str(tenant.id)},
        )
        if not delivered:
            continue

        db.add(
            Reminder(
                tenant_id=tenant.id,
                entity_type="invoice",
                entity_id=invoice.id,
                channel="email",
                sequence=sequence,
                payload={
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "total": str(invoice.total),
                },
            )
        )
        await notify_staff(
            db,
            tenant.id,
            kind="invoice_reminder_sent",
            title="Invoice reminder sent",
            body=f"Payment reminder {sequence} emailed to "
            f"{contact.name if contact is not None else 'the customer'} for invoice "
            f"{invoice.invoice_number} (£{invoice.total}).",
            link=f"/invoices/{invoice.id}",
        )
        await write_audit_log(
            db,
            tenant_id=tenant.id,
            actor=None,
            action=Actions.INVOICE_REMINDER_SENT,
            entity_type="invoice",
            entity_id=invoice.id,
            payload={"sequence": sequence},
        )
        sent += 1
    return sent


async def _process_tenant(db: AsyncSession, tenant: Tenant, now: datetime) -> dict[str, int]:
    """Process one tenant inside a lock-guarded transaction."""
    locked = (
        await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:namespace, hashtext(:key))"),
            {"namespace": _LOCK_NAMESPACE, "key": f"reminders:{tenant.id}"},
        )
    ).scalar()
    if not locked:
        logger.info("reminder_tenant_locked_elsewhere", tenant_id=str(tenant.id))
        return {"quote_reminders": 0, "invoice_reminders": 0, "skipped_locked": 1}

    await set_tenant_in_session(db, tenant.id)
    config = _ReminderConfig(tenant.settings)
    quote_sent = await _process_quote_reminders(db, tenant, config, now)
    invoice_sent = await _process_invoice_reminders(db, tenant, config, now)
    await db.commit()
    return {
        "quote_reminders": quote_sent,
        "invoice_reminders": invoice_sent,
        "skipped_locked": 0,
    }


async def _run_tick(db: AsyncSession, now: datetime) -> dict[str, int]:
    summary = {
        "tenants": 0,
        "quote_reminders": 0,
        "invoice_reminders": 0,
        "skipped_locked": 0,
        "errors": 0,
    }
    tenants = (await db.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all()
    for tenant in tenants:
        summary["tenants"] += 1
        try:
            result = await _process_tenant(db, tenant, now)
        except Exception as exc:
            # A broken tenant (bad settings shape, transient DB error) must
            # not stop the sweep for everyone else.
            await db.rollback()
            summary["errors"] += 1
            logger.error(
                "reminder_tenant_failed",
                tenant_id=str(tenant.id),
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
            continue
        summary["quote_reminders"] += result["quote_reminders"]
        summary["invoice_reminders"] += result["invoice_reminders"]
        summary["skipped_locked"] += result["skipped_locked"]
    return summary


async def run_reminder_tick(
    db: AsyncSession | None = None, now: datetime | None = None
) -> dict[str, int]:
    """Run one reminder sweep across all active tenants.

    ``db`` is injectable for tests (which run inside a rolled-back outer
    transaction the default session factory cannot see); production callers
    get a fresh session. Returns a summary dict for logging.
    """
    now = now or datetime.utcnow()
    if db is not None:
        return await _run_tick(db, now)
    async with AsyncSessionLocal() as session:
        return await _run_tick(session, now)


async def reminder_loop(stop: asyncio.Event) -> None:
    """Scheduler task body: sweep once per ``REMINDER_TICK_SECONDS``.

    The first sweep runs one full interval after startup so a fresh deploy
    never immediately emails customers. The task never raises — sweep
    failures are logged and the loop continues.
    """
    logger.info("reminder_scheduler_started", tick_seconds=REMINDER_TICK_SECONDS)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=REMINDER_TICK_SECONDS)
            break
        except TimeoutError:
            pass
        try:
            summary = await run_reminder_tick()
            logger.info("reminder_tick_complete", **summary)
        except Exception as exc:
            logger.error(
                "reminder_tick_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
    logger.info("reminder_scheduler_stopped")
