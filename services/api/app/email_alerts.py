"""Staff alerts for undeliverable customer-facing emails.

Founder rule: when a customer email notification bounces or fails to send,
the electrician must be told and directed to an alternative contact method
(phone). Two sources feed the same alert path:

* **Send-time** — :func:`app.email.send_customer_email` invokes
  :func:`alert_staff_email_failure` through its ``on_failure`` hook when the
  Resend/SMTP transport raises.
* **Resend webhooks** — ``POST /webhooks/resend`` (``email.bounced`` /
  ``email.failed``) resolves the ``mtp_tenant``/``mtp_contact`` tags stamped
  at send time and calls the same helper.

Dedupe: at most one staff notification per (tenant, contact, calendar day),
ledgered in the ``email_failure_alerts`` table, so a dead mailbox cannot
re-page the electrician on every reminder sweep or webhook retry. Everything
here is best-effort and never raises — a failing alert must not break the
workflow whose email failed, and staff-facing mail deliberately goes through
plain ``send_event_email`` (no failure hook) so alerts cannot loop.
"""

from datetime import date
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.email import send_event_email
from app.models import Contact, EmailFailureAlert, User
from app.push import notify_staff
from app.rls import set_tenant_in_session

logger = structlog.get_logger("api.email_alerts")

# Cap on staff alert emails per incident — the in-app notification already
# reaches every staff user; the email is a fallback for staff away from it.
_MAX_STAFF_EMAIL_RECIPIENTS = 5


def _alert_content(
    *,
    name: str,
    recipient_email: str | None,
    purpose: str,
    error_class: str,
    phone: str | None,
) -> tuple[str, str]:
    """Title + body for the staff alert, including the phone directive."""
    title = f"Email to {name} wasn't delivered"
    directive = (
        f"Contact them by phone instead: {phone}"
        if phone
        else "Reach them another way — their email isn't working."
    )
    body = f"The {purpose} email to {recipient_email or name} failed ({error_class}). {directive}"
    return title, body


async def _email_staff_about_failure(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    title: str,
    body: str,
) -> None:
    """Best-effort platform no-reply email to the tenant's staff users.

    Sent through plain ``send_event_email`` (no ``on_failure`` hook, no
    ``mtp_*`` tags) so a failing staff alert email can never raise another
    alert. Platform-branded: no tenant display name, no Reply-To.
    """
    try:
        staff_emails = (
            (
                await db.execute(
                    select(User.email)
                    .where(User.tenant_id == tenant_id, User.is_active.is_(True))
                    .limit(_MAX_STAFF_EMAIL_RECIPIENTS)
                )
            )
            .scalars()
            .all()
        )
    except Exception as exc:
        logger.error(
            "email_failure_staff_lookup_failed",
            tenant_id=str(tenant_id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return
    for staff_email in staff_emails:
        if not staff_email:
            continue
        await send_event_email(
            to_email=staff_email,
            subject=title,
            html_body=f"<p>{body}</p>",
            text_body=body,
            event="email_failure_staff_alert",
            template="email_failure_staff_alert",
            context={"tenant_id": str(tenant_id)},
        )


async def alert_staff_email_failure(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID | None,
    recipient_email: str | None,
    purpose: str,
    error_class: str,
    source: str,
) -> bool:
    """Notify tenant staff that a customer email failed. Never raises.

    Returns ``True`` when a new alert was raised, ``False`` when deduped (an
    alert for this contact already went out today) or when alerting itself
    failed. The caller's session is used and the caller commits (same
    convention as :func:`app.push.notify_staff`); the writes run inside a
    savepoint so a dedupe race or RLS problem rolls back only the alert, not
    the caller's work.
    """
    try:
        # The session may carry no tenant GUC (bounce webhooks, post-commit
        # portal flows) — scope it so the RLS-forced notifications write and
        # the contact lookup pass.
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
                "email_failure_alert_deduped",
                tenant_id=str(tenant_id),
                contact_id=str(contact_id) if contact_id else None,
                source=source,
            )
            return False
        contact = await db.get(Contact, contact_id) if contact_id is not None else None
        name = (
            contact.name
            if contact is not None and contact.name
            else (recipient_email or "the customer")
        )
        phone = contact.phone if contact is not None else None
        title, body = _alert_content(
            name=name,
            recipient_email=recipient_email,
            purpose=purpose,
            error_class=error_class,
            phone=phone,
        )
        async with db.begin_nested():
            db.add(
                EmailFailureAlert(
                    tenant_id=tenant_id,
                    contact_id=contact_id,
                    alert_date=today,
                    source=source,
                    purpose=purpose,
                    error_class=error_class,
                )
            )
            await notify_staff(
                db,
                tenant_id,
                kind="email_failed",
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
            "email_failure_alert_raised",
            tenant_id=str(tenant_id),
            contact_id=str(contact_id) if contact_id else None,
            purpose=purpose,
            error_class=error_class,
            source=source,
        )
    except Exception as exc:
        logger.error(
            "email_failure_alert_failed",
            tenant_id=str(tenant_id),
            contact_id=str(contact_id) if contact_id else None,
            source=source,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return False
    await _email_staff_about_failure(db, tenant_id=tenant_id, title=title, body=body)
    return True
