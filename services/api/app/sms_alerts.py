"""Staff alerts for undeliverable customer-facing SMS.

Mirrors :mod:`app.email_alerts` (the founder rule applied to texts): when an
appointment-reminder SMS permanently fails — reported by the Telnyx delivery
receipt webhook (``POST /webhooks/telnyx``, ``message.finalized`` with
``sending_failed`` / ``delivery_failed``) — the electrician is paged and
directed to an alternative contact channel (email, or "another way" when the
contact has no email).

Dedupe shares the ``email_failure_alerts`` ledger with email failures: at
most one staff notification per (tenant, contact, calendar day) regardless of
channel, so a customer whose contact details are simply wrong cannot re-page
the electrician once for email and again for SMS on the same day. Everything
here is best-effort and never raises — a failing alert must not break the
webhook that reported the delivery failure.
"""

from datetime import date
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.email_alerts import _email_staff_about_failure
from app.models import Contact, EmailFailureAlert, Tenant
from app.push import notify_staff
from app.rls import set_tenant_in_session

logger = structlog.get_logger("api.sms_alerts")


def _alert_content(
    *,
    name: str,
    recipient_phone: str | None,
    purpose: str,
    error_class: str,
    email: str | None,
    detail: str | None = None,
) -> tuple[str, str]:
    """Title + body for the staff alert, including the email directive."""
    title = f"SMS to {name} wasn't delivered"
    directive = (
        f"Reach them by email instead: {email}"
        if email
        else "Reach them another way — their number isn't receiving texts."
    )
    detail_part = f" Telnyx error: {detail}." if detail else ""
    body = (
        f"The {purpose} SMS to {recipient_phone or name} failed ({error_class})."
        f"{detail_part} {directive}"
    )
    return title, body


async def alert_staff_sms_failure(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID | None,
    recipient_phone: str | None,
    purpose: str,
    error_class: str,
    detail: str | None = None,
) -> bool:
    """Notify tenant staff that a customer SMS failed. Never raises.

    Returns ``True`` when a new alert was raised, ``False`` when deduped (an
    alert for this contact — either channel — already went out today) or when
    alerting itself failed. ``detail`` (the Telnyx error code/title) is
    appended to the staff alert body so deliverability issues are diagnosable
    from the alert alone. The caller's session is used and the caller commits;
    the writes run inside a savepoint so a dedupe race or RLS problem rolls
    back only the alert (same convention as
    :func:`app.email_alerts.alert_staff_email_failure`).
    """
    try:
        # Delivery receipts arrive for every environment sharing the Telnyx
        # account; a reminder row matched here could still reference a tenant
        # torn down between send and receipt, and the notifications tenant FK
        # would reject the insert. Verify before doing anything else.
        tenant_exists = await db.scalar(select(Tenant.id).where(Tenant.id == tenant_id))
        if tenant_exists is None:
            logger.info("sms_failure_unknown_tenant", tenant_id=str(tenant_id))
            return False
        # The webhook session may carry no tenant GUC — scope it so the
        # RLS-forced notifications write and the contact lookup pass.
        await set_tenant_in_session(db, tenant_id)
        today = date.today()
        existing = await db.scalar(
            select(EmailFailureAlert.id).where(
                EmailFailureAlert.tenant_id == tenant_id,
                EmailFailureAlert.contact_id == contact_id,
                EmailFailureAlert.alert_date == today,
            )
        )
        if existing is not None:
            logger.info(
                "sms_failure_alert_deduped",
                tenant_id=str(tenant_id),
                contact_id=str(contact_id) if contact_id else None,
            )
            return False
        contact = await db.get(Contact, contact_id) if contact_id is not None else None
        name = (
            contact.name
            if contact is not None and contact.name
            else (recipient_phone or "the customer")
        )
        email = contact.email if contact is not None else None
        title, body = _alert_content(
            name=name,
            recipient_phone=recipient_phone,
            purpose=purpose,
            error_class=error_class,
            email=email,
            detail=detail,
        )
        async with db.begin_nested():
            db.add(
                EmailFailureAlert(
                    tenant_id=tenant_id,
                    contact_id=contact_id,
                    alert_date=today,
                    source="telnyx_dlr",
                    purpose=purpose,
                    error_class=error_class,
                )
            )
            await notify_staff(
                db,
                tenant_id,
                kind="sms_failed",
                title=title,
                body=body,
                link=f"/customers/{contact_id}" if contact_id is not None else None,
            )
            # Flush inside the savepoint: app sessions run autoflush=False, so
            # without this the inserts would only hit the database at the
            # caller's commit — where a dedupe-race IntegrityError would
            # poison the caller's whole transaction instead of just the alert.
            await db.flush()
        logger.info(
            "sms_failure_alert_raised",
            tenant_id=str(tenant_id),
            contact_id=str(contact_id) if contact_id else None,
            purpose=purpose,
            error_class=error_class,
            detail=detail,
        )
    except Exception as exc:
        logger.error(
            "sms_failure_alert_failed",
            tenant_id=str(tenant_id),
            contact_id=str(contact_id) if contact_id else None,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return False
    await _email_staff_about_failure(db, tenant_id=tenant_id, title=title, body=body)
    return True
