"""Payment-failure dunning for Paddle-billed subscriptions.

When a renewal payment fails, Paddle flips the subscription to ``past_due``
and retries in the background (Paddle Retain). This module runs the
customer-comms side of that dunning window:

* a "payment failed — update your payment method" email carrying a fresh
  Paddle customer-portal session URL (``attempt`` 1), then
* follow-up reminders every :data:`DUNNING_INTERVAL_DAYS`, stopping after
  :data:`DUNNING_MAX_REMINDERS` emails per episode.

Episode model
-------------
A dunning episode is (subscription, billing period): the episode key is the
period end date — when the failed payment came due. Episode state lives in
the existing ``reminders`` ledger (``entity_type="subscription"``, one row
per dispatched email), so there is a full audit trail and no schema change.
A later failure in a new billing period opens a fresh episode because the
period-end key differs.

Triggers and stops
------------------
* :func:`maybe_start_dunning` runs from the Paddle webhook handler on
  ``subscription.past_due`` and ``transaction.payment_failed``. It is
  idempotent per episode: a replayed webhook (or each extra failed Paddle
  retry) never double-emails.
* :func:`run_dunning_followups` runs from the reminder scheduler sweep and
  covers follow-ups, plus opens the episode itself if the webhook was
  somehow missed.
* Recovery or cancellation needs no explicit state flip: the sweep only
  chases subscriptions whose status is still ``past_due``, so a
  ``subscription.updated``/``activated`` (payment recovered) or
  ``subscription.canceled`` event stops the sequence on its own.

The tenant owner (the account that pays for the business) is the recipient;
``send_customer_email`` carries the ``mtp_tenant`` correlation tag and the
staff failure alert, and a failed send is not recorded as a reminder so the
episode is never short-changed by a transport blip.
"""

from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.email import send_customer_email
from app.email_templates import payment_failed as payment_failed_template
from app.models import Reminder, Subscription, Tenant
from app.paddle_client import create_customer_portal_session
from app.rls import set_tenant_in_session

logger = structlog.get_logger("api.dunning")

# Total dunning emails per episode, including the initial notice.
DUNNING_MAX_REMINDERS = 3
# Days between dunning emails (initial → follow-up 1 → follow-up 2).
DUNNING_INTERVAL_DAYS = 3

_ENTITY_TYPE = "subscription"


def episode_period_end(subscription: Subscription) -> str | None:
    """Episode key: ISO date of the failed period's end (the payment due date)."""
    if subscription.current_period_end is None:
        return None
    return subscription.current_period_end.date().isoformat()


async def _episode_reminders(
    db: AsyncSession, subscription: Subscription, period_end: str | None
) -> list[Reminder]:
    """Reminder rows already sent for this (subscription, episode) pair."""
    rows = (
        (
            await db.execute(
                select(Reminder).where(
                    Reminder.entity_type == _ENTITY_TYPE,
                    Reminder.entity_id == subscription.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return [r for r in rows if (r.payload or {}).get("period_end") == period_end]


async def _send_dunning_email(
    db: AsyncSession,
    subscription: Subscription,
    tenant: Tenant,
    *,
    sequence: int,
    period_end: str | None,
) -> bool:
    """Send one dunning email and record it in the ledger. Never raises."""
    portal_url: str | None = None
    if subscription.paddle_customer_id:
        try:
            portal_url = await create_customer_portal_session(subscription.paddle_customer_id)
        except Exception as exc:
            # The notice still matters without the link — the email falls
            # back to in-app instructions. Loud log so the gap is visible.
            logger.warning(
                "dunning_portal_session_failed",
                tenant_id=str(tenant.id),
                paddle_subscription_id=subscription.paddle_subscription_id,
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
    subject, html, text = payment_failed_template(
        business_name=tenant.name,
        portal_url=portal_url,
        attempt=sequence,
        max_attempts=DUNNING_MAX_REMINDERS,
    )
    delivered = await send_customer_email(
        db,
        tenant_id=tenant.id,
        contact_id=None,
        purpose="subscription payment reminder",
        to_email=tenant.email or None,
        subject=subject,
        html_body=html,
        text_body=text,
        event="subscription_payment_failed",
        template="payment_failed",
        from_name="My Trade Portal",
        context={
            "paddle_subscription_id": subscription.paddle_subscription_id,
            "sequence": sequence,
        },
    )
    if not delivered:
        # Not recorded: an unreachable address must not burn a dunning slot.
        return False
    db.add(
        Reminder(
            tenant_id=tenant.id,
            entity_type=_ENTITY_TYPE,
            entity_id=subscription.id,
            channel="email",
            sequence=sequence,
            payload={
                "paddle_subscription_id": subscription.paddle_subscription_id,
                "period_end": period_end,
                "sequence": sequence,
            },
        )
    )
    logger.info(
        "dunning_email_sent",
        tenant_id=str(tenant.id),
        paddle_subscription_id=subscription.paddle_subscription_id,
        sequence=sequence,
        period_end=period_end,
    )
    return True


async def start_dunning_episode(
    db: AsyncSession, subscription: Subscription, tenant: Tenant
) -> bool:
    """Open a dunning episode: email #1, unless this episode already has one.

    Idempotent per (subscription, billing period) — repeated webhook
    deliveries and each extra failed Paddle retry funnel through here without
    ever double-emailing.
    """
    period_end = episode_period_end(subscription)
    if await _episode_reminders(db, subscription, period_end):
        return False
    return await _send_dunning_email(db, subscription, tenant, sequence=1, period_end=period_end)


async def maybe_start_dunning(paddle_subscription_id: str | None) -> bool:
    """Webhook entry point: open the episode for a past-due subscription.

    Uses its own engine session (like the webhook upsert) and sets the RLS
    tenant context, because the reminders ledger is tenant-scoped. Never
    raises — a dunning email must never turn a verified webhook into a 500
    (Paddle would retry the whole event, and the episode guard makes even
    that safe).
    """
    if not paddle_subscription_id:
        return False
    try:
        from app.database import engine

        async with AsyncSession(engine) as session:
            subscription = await session.scalar(
                select(Subscription).where(
                    Subscription.paddle_subscription_id == paddle_subscription_id
                )
            )
            if subscription is None or subscription.status != "past_due":
                return False
            tenant = await session.get(Tenant, subscription.tenant_id)
            if tenant is None:
                return False
            await set_tenant_in_session(session, tenant.id)
            started = await start_dunning_episode(session, subscription, tenant)
            await session.commit()
            return started
    except Exception as exc:
        logger.error(
            "dunning_start_failed",
            paddle_subscription_id=paddle_subscription_id,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return False


async def run_dunning_followups(db: AsyncSession, tenant: Tenant, now: datetime) -> int:
    """Scheduler entry point: follow up open dunning episodes for one tenant.

    Chases only subscriptions still in ``past_due`` (recovery or cancellation
    stops the sequence implicitly). Opens the episode itself when the webhook
    trigger was missed. Returns the number of emails sent this sweep.
    """
    subscription = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    if subscription is None or subscription.status != "past_due":
        return 0
    period_end = episode_period_end(subscription)
    sent_rows = await _episode_reminders(db, subscription, period_end)
    if not sent_rows:
        # Webhook missed or failed: open the episode now.
        return 1 if await start_dunning_episode(db, subscription, tenant) else 0
    if len(sent_rows) >= DUNNING_MAX_REMINDERS:
        return 0
    last_sent = max(row.created_at for row in sent_rows if row.created_at is not None)
    if now - last_sent < timedelta(days=DUNNING_INTERVAL_DAYS):
        return 0
    return (
        1
        if await _send_dunning_email(
            db, subscription, tenant, sequence=len(sent_rows) + 1, period_end=period_end
        )
        else 0
    )
