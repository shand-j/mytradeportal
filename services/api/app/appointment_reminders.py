"""SMS appointment reminders — plan-included, fair-use guarded.

Called once per tenant from the reminder sweep (``app.scheduler``) after the
quote/invoice/dunning passes. For every ``Appointment`` approaching one of the
configured windows (default 24 h and 2 h before ``start_at``) it reminds BOTH
sides of the booking:

* **Customer** — SMS to ``Contact.phone`` (normalised to E.164). No usable
  number, SMS unconfigured, or SMS paused → one email via the
  ``appointment_reminder`` template instead.
* **Assigned electrician** — SMS to ``User.phone`` when present; staff always
  get the free in-app/push notification regardless.

Sender identity is the tenant's business name, sent as a Telnyx alphanumeric
sender ID (falling back to the configured from-number / messaging profile).

Messages always fit ONE SMS segment (the fair-use cost model assumes one
segment per reminder): bodies are built compactly — address line and greeting
dropped first if over budget — then hard-truncated at a word boundary, and
the limit is 70 chars rather than 160 whenever the text contains a
non-GSM-7 character (see :func:`app.sms.sms_segment_limit`).

STOP opt-out trade-off: "Reply STOP to opt out" is only appended when the
resolved sender is a NUMBER. When the tenant's name is used as an
alphanumeric sender ID, customer replies cannot reach us (and UK STOP
handling is not wired), so promising an opt-out mechanism would be
misleading — the line is omitted rather than lied about.

Dispatch state lives in the same ``reminders`` table as the other chases:
one row per actually-delivered reminder, keyed
``(entity_type="appointment", entity_id, payload.window_hours, payload.role)``
so an hourly sweep can never double-fire a window, and an SMS row also
suppresses the email fallback for the same window+role (channel-agnostic
dedupe). Failed sends record nothing — mirroring the quote/invoice chase
semantics, a customer we could not reach must not burn a slot.

Plan + fair use: ``sms_reminders`` is on every tier (cost basis: worst case
≈ £1.60/month SMS for the cheapest plan), but like AI tokens it carries an
invisible monthly fair-use guardrail: once the tenant's current-UTC-month SMS
reminder count reaches ``SMS_FAIR_USE_MONTHLY_THRESHOLD`` (default 500),
SMS degrades to email/push until the month rolls over. Crossing fires exactly
one internal staff alert (deduped via ``ai_alert_state``), never anything
customer-visible. The whole check is fail-open: an error pauses nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.alerting import send_alert
from app.audit import Actions, write_audit_log
from app.config import (
    APPOINTMENT_REMINDER_PAD_MINUTES,
    APPOINTMENT_REMINDER_WINDOWS_HOURS,
    SMS_FAIR_USE_MONTHLY_THRESHOLD,
    SMS_REMINDERS_ENABLED,
)
from app.email import send_customer_email
from app.email_templates import appointment_reminder as appointment_reminder_template
from app.models import (
    AiAlertState,
    Appointment,
    Contact,
    Reminder,
    Subscription,
    User,
)
from app.plans import DEFAULT_PLAN_KEY, current_period, get_plan
from app.push import notify_staff
from app.sms import normalize_phone, normalize_sender, send_sms, sms_configured, sms_segment_limit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Tenant

logger = structlog.get_logger("api.appointment_reminders")

_ACTIVE_STATUSES = ("confirmed", "scheduled")


def _windows() -> list[int]:
    """Parse APPOINTMENT_REMINDER_WINDOWS_HOURS into positive ints (sorted)."""
    windows: list[int] = []
    for part in str(APPOINTMENT_REMINDER_WINDOWS_HOURS).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value > 0 and value not in windows:
            windows.append(value)
    return sorted(windows or [24, 2])


def _fit_single_segment(text: str) -> str:
    """Hard-truncate ``text`` to one SMS segment at a word boundary.

    Last resort after the compact body forms have been tried: cut at the
    last word boundary that fits (with an ellipsis), verifying the result
    against the limit for the characters actually used — "…" is not GSM-7,
    so a GSM-7 body fitted with "…" drops to the 70-char UCS-2 budget.
    """
    if len(text) <= sms_segment_limit(text):
        return text
    for ellipsis in ("…", "..."):
        limit = sms_segment_limit(ellipsis)
        body = text[: limit - len(ellipsis)].rstrip()
        space = body.rfind(" ")
        if space > 0:
            body = body[:space].rstrip()
        if not body:
            continue
        fitted = f"{body}{ellipsis}"
        if len(fitted) <= sms_segment_limit(fitted):
            return fitted
    return text[:70]


def _customer_sms_text(
    *, tenant_name: str, first_name: str, appointment: Appointment, include_stop: bool
) -> str:
    """Customer reminder text, guaranteed to fit one SMS segment.

    Builds the fullest form first (greeting + title + address) and drops
    the address line, then the greeting, then the business name if over
    budget; anything still over limit is word-boundary truncated by
    :func:`_fit_single_segment`.
    """
    start = appointment.start_at
    when = f"{start:%a %d %b at %H:%M}"
    title = (appointment.title or "").strip() or "your appointment"
    address = (appointment.address or "").strip()
    stop = " Reply STOP to opt out." if include_stop else ""
    greeting = f"Hi {first_name}, " if first_name else ""
    forms = [
        f'{greeting}reminder from {tenant_name}: "{title}" on {when}.'
        + (f" At: {address}." if address else "")
        + stop,
        f'{greeting}reminder from {tenant_name}: "{title}" on {when}.{stop}',
        f'Reminder from {tenant_name}: "{title}" on {when}.{stop}',
        f'Reminder: "{title}" on {when}.{stop}',
    ]
    for form in forms:
        if len(form) <= sms_segment_limit(form):
            return form
    return _fit_single_segment(forms[-1])


def _staff_sms_text(*, tenant_name: str, appointment: Appointment) -> str:
    """Staff reminder text, fitted to one SMS segment."""
    body = (
        f"Reminder from {tenant_name}: '{appointment.title}' on "
        f"{appointment.start_at:%a %d %b at %H:%M}. Open the app for details."
    )
    if len(body) > sms_segment_limit(body):
        return _fit_single_segment(body)
    return body


async def _sms_fair_use_paused(db: AsyncSession, tenant: Tenant, now: datetime) -> bool:
    """True when SMS is paused for this tenant this month.

    Pause state lives in ``tenant.settings`` (``sms_reminders_paused`` +
    ``sms_fair_use_period``, same pattern as the AI ``ai_cheap_route`` flag).
    On the first crossing of ``SMS_FAIR_USE_MONTHLY_THRESHOLD`` the keys are
    persisted and exactly one staff alert fires (deduped via ``ai_alert_state``
    with a per-tenant threshold key). A new month clears the pause.
    """
    settings_dict = dict(tenant.settings or {})
    period = current_period()
    stored_period = settings_dict.get("sms_fair_use_period")
    if settings_dict.get("sms_reminders_paused") and stored_period == period:
        return True
    if stored_period and stored_period != period:
        # Month rolled over: clear the pause and count afresh.
        settings_dict.pop("sms_reminders_paused", None)
        settings_dict.pop("sms_fair_use_period", None)
        tenant.settings = settings_dict
        await db.flush()

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = (
        await db.scalar(
            select(func.count(Reminder.id)).where(
                Reminder.tenant_id == tenant.id,
                Reminder.channel == "sms",
                Reminder.created_at >= month_start,
            )
        )
    ) or 0
    if count < SMS_FAIR_USE_MONTHLY_THRESHOLD:
        return False

    settings_dict["sms_reminders_paused"] = True
    settings_dict["sms_fair_use_period"] = period
    tenant.settings = settings_dict
    await db.flush()
    await _fire_fair_use_alert_once(db, tenant, count)
    return True


async def _fire_fair_use_alert_once(db: AsyncSession, tenant: Tenant, monthly_count: int) -> None:
    """Dispatch exactly one SMS fair-use staff alert per org per month."""
    period = current_period()
    try:
        async with db.begin_nested():
            db.add(
                AiAlertState(
                    period=period,
                    threshold=f"sms_fair_use:{tenant.id}",
                    payload={"tenant_id": str(tenant.id), "monthly_sms": monthly_count},
                )
            )
            await db.flush()
    except IntegrityError:
        return  # already fired this month
    await send_alert(
        subject=f"SMS fair-use threshold crossed ({tenant.slug})",
        text=(
            f"Tenant {tenant.slug} ({tenant.id}) has sent {monthly_count} SMS reminders this "
            f"month, crossing the fair-use threshold of {SMS_FAIR_USE_MONTHLY_THRESHOLD}. "
            "SMS appointment reminders are paused for this tenant until the month rolls "
            "over; reminders degrade to email/push in the meantime. Internal only — no "
            "customer action needed."
        ),
    )


async def process_appointment_reminders(
    db: AsyncSession, tenant: Tenant, now: datetime
) -> dict[str, int]:
    """Send due appointment reminders for one tenant.

    Returns counts: ``customer_sms``, ``staff_sms``, ``email_fallbacks``.
    Assumes the session is already tenant-scoped (``set_tenant_in_session``)
    and that the caller commits — the same contract as the other scheduler
    passes.
    """
    counts = {"customer_sms": 0, "staff_sms": 0, "email_fallbacks": 0}
    if not SMS_REMINDERS_ENABLED:
        return counts
    # Deferred import: app.scheduler imports this module at its own import
    # time, so the shared settings helper cannot be imported at module level.
    from app.scheduler import _bool_setting

    if not _bool_setting(tenant.settings or {}, "appointment_reminders_enabled", True):
        return counts

    windows = _windows()
    pad = timedelta(minutes=APPOINTMENT_REMINDER_PAD_MINUTES)
    horizon = now + timedelta(hours=windows[-1])

    appointments = (
        (
            await db.execute(
                select(Appointment).where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.status.in_(_ACTIVE_STATUSES),
                    Appointment.start_at > now,
                    Appointment.start_at <= horizon,
                )
            )
        )
        .scalars()
        .all()
    )
    if not appointments:
        return counts

    # Channel-agnostic dedupe: a row for (window, role) — regardless of
    # channel — means that reminder already went out (SMS success, email
    # fallback or staff push all count).
    rows = (
        (
            await db.execute(
                select(Reminder).where(
                    Reminder.entity_type == "appointment",
                    Reminder.entity_id.in_([a.id for a in appointments]),
                )
            )
        )
        .scalars()
        .all()
    )
    fired: set[tuple[str, str]] = {
        (str((r.payload or {}).get("window_hours")), str((r.payload or {}).get("role")))
        for r in rows
    }
    sequences = {a.id: sum(1 for r in rows if r.entity_id == a.id) for a in appointments}

    # Plan gate: sms_reminders is on every tier, but a plan without it (or no
    # Telnyx credentials) degrades everything to email/push.
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    plan = get_plan(sub.plan_key) if sub is not None else get_plan(DEFAULT_PLAN_KEY)
    sms_allowed = "sms_reminders" in plan.features and sms_configured()

    sms_paused = False
    if sms_allowed:
        try:
            sms_paused = await _sms_fair_use_paused(db, tenant, now)
        except Exception as exc:
            # Fail-open like fair_use_guard: a blip in the guardrail must
            # never take appointment reminders down.
            logger.error(
                "sms_fair_use_check_failed",
                tenant_id=str(tenant.id),
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
    sms_allowed = sms_allowed and not sms_paused
    # STOP opt-out only makes sense when replies can reach us: an
    # alphanumeric sender ID (tenant business name) cannot receive texts.
    numeric_sender = normalize_sender(tenant.name) is None

    for appointment in appointments:
        delta = appointment.start_at - now
        due_windows = [
            w for w in windows if delta <= timedelta(hours=w) and delta > timedelta(hours=w) - pad
        ]
        if not due_windows:
            continue
        contact = await db.get(Contact, appointment.contact_id)
        staff = (
            await db.get(User, appointment.assigned_user_id)
            if appointment.assigned_user_id is not None
            else None
        )

        for window in due_windows:
            for role in ("customer", "staff"):
                if (str(window), role) in fired:
                    continue
                if role == "customer":
                    delivered = await _remind_customer(
                        db, tenant, appointment, contact, window, sms_allowed, numeric_sender
                    )
                else:
                    if staff is None:
                        continue
                    delivered = await _remind_staff(
                        db, tenant, appointment, staff, window, sms_allowed
                    )
                if delivered is None:
                    continue
                channel = delivered
                fired.add((str(window), role))
                appointment_sequences = sequences.setdefault(appointment.id, 0) + 1
                sequences[appointment.id] = appointment_sequences
                payload: dict[str, Any] = {
                    "appointment_id": str(appointment.id),
                    "window_hours": str(window),
                    "role": role,
                }
                if channel == "sms":
                    phone = (
                        (contact.phone if contact is not None else None)
                        if role == "customer"
                        else (staff.phone if staff is not None else None)
                    )
                    payload["to"] = normalize_phone(phone)
                db.add(
                    Reminder(
                        tenant_id=tenant.id,
                        entity_type="appointment",
                        entity_id=appointment.id,
                        channel=channel,
                        sequence=appointment_sequences,
                        payload=payload,
                    )
                )
                await notify_staff(
                    db,
                    tenant.id,
                    kind="appointment_reminder_sent",
                    title="Appointment reminder sent",
                    body=(
                        f"{window}h reminder for '{appointment.title}' "
                        f"({appointment.start_at:%a %d %b %H:%M}) sent to "
                        f"the {role} via {channel}."
                    ),
                    link=None,
                )
                await write_audit_log(
                    db,
                    tenant_id=tenant.id,
                    actor=None,
                    action=Actions.APPOINTMENT_REMINDER_SENT,
                    entity_type="appointment",
                    entity_id=appointment.id,
                    payload={"window_hours": window, "role": role, "channel": channel},
                )
                if channel == "sms":
                    counts["customer_sms" if role == "customer" else "staff_sms"] += 1
                elif channel == "email":
                    counts["email_fallbacks"] += 1
    return counts


async def _remind_customer(
    db: AsyncSession,
    tenant: Tenant,
    appointment: Appointment,
    contact: Contact | None,
    window: int,
    sms_allowed: bool,
    numeric_sender: bool,
) -> str | None:
    """Customer reminder: SMS when allowed, else the email fallback.

    Returns the delivered channel (``"sms"``/``email``), or ``None`` when
    there was no usable channel (no phone and no email) — nothing recorded,
    mirroring the quote/invoice "failed sends don't burn slots" rule.
    """
    if contact is None:
        return None
    if sms_allowed and contact.phone and normalize_phone(contact.phone):
        body = _customer_sms_text(
            tenant_name=tenant.name,
            first_name=(contact.name.split()[0] if contact.name else ""),
            appointment=appointment,
            include_stop=numeric_sender,
        )
        message_id = await send_sms(
            to_phone=contact.phone,
            text=body,
            tenant_name=tenant.name,
            tenant_id=tenant.id,
        )
        if message_id:
            return "sms"
        # Telnyx failure → degrade to email for this window rather than
        # dropping the reminder entirely.
    if not contact.email:
        return None
    start = appointment.start_at
    subject, html, text = appointment_reminder_template(
        customer_name=contact.name.split()[0] if contact.name else "there",
        business_name=tenant.name,
        job_title=appointment.title,
        visit_date=f"{start:%a %d %b}",
        time_window=f"{start:%H:%M}",
        address=appointment.address or contact.address,
    )
    delivered = await send_customer_email(
        db,
        tenant_id=tenant.id,
        contact_id=contact.id,
        purpose="appointment reminder",
        to_email=contact.email,
        subject=subject,
        html_body=html,
        text_body=text,
        event="appointment_reminder",
        template="appointment_reminder",
        from_name=tenant.name,
        context={
            "appointment_id": str(appointment.id),
            "tenant_id": str(tenant.id),
        },
    )
    if not delivered:
        return None
    return "email"


async def _remind_staff(
    db: AsyncSession,
    tenant: Tenant,
    appointment: Appointment,
    staff: User,
    window: int,
    sms_allowed: bool,
) -> str:
    """Staff reminder: free in-app/push always; SMS too when a phone is set.

    Returns the delivered channel: ``"sms"`` when the text went out, else
    ``"push"`` (push-only still records a reminder row so the window dedupes).
    """
    channel = "push"
    if sms_allowed and staff.phone and normalize_phone(staff.phone):
        body = _staff_sms_text(tenant_name=tenant.name, appointment=appointment)
        message_id = await send_sms(
            to_phone=staff.phone,
            text=body,
            tenant_name=tenant.name,
            tenant_id=tenant.id,
        )
        if message_id:
            channel = "sms"
    return channel
