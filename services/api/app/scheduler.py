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
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, func, select, text

from app.alerting import fetch_usd_gbp_rate, send_alert
from app.audit import Actions, write_audit_log
from app.config import (
    AI_FAIR_USE_MONTHLY_THRESHOLD,
    AI_MONTHLY_BUDGET_GBP,
    FX_REFRESH_MAX_AGE_DAYS,
    REMINDER_TICK_SECONDS,
    ROLLUP_RUN_HOUR_UTC,
    ROLLUP_RUN_MINUTE_UTC,
    ROLLUP_TICK_SECONDS,
)
from app.database import AsyncSessionLocal
from app.email import send_event_email
from app.email_templates import invoice_reminder as invoice_reminder_template
from app.email_templates import quote_reminder as quote_reminder_template
from app.fx import store_fx_rate
from app.models import (
    AiAlertState,
    AiCallEvent,
    AiRollupFeatureDay,
    AiRollupUserDay,
    Contact,
    FxRate,
    Invoice,
    Quote,
    Reminder,
    Tenant,
)
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


async def _document_view_url(
    db: AsyncSession, kind: str, document_id: UUID, tenant_id: UUID, contact_email: str | None
) -> str:
    """Secure web link for a customer-facing document (mytradeportal.co.uk).

    Mints a fresh DocumentAccessToken per send — tokens are hashed at rest so
    an earlier link can't be recovered; minting revokes prior links for the
    document ("newest link wins", same as the send_quote/send_invoice flow).
    """
    from app.routers.public_docs import issue_document_token, public_document_url

    raw = await issue_document_token(
        db,
        kind=kind,  # type: ignore[arg-type]
        document_id=document_id,
        tenant_id=tenant_id,
        contact_email=contact_email,
    )
    return public_document_url(kind, raw)  # type: ignore[arg-type]


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
            view_url=await _document_view_url(
                db, "quote", quote.id, tenant.id, contact.email if contact else None
            ),
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
            view_url=await _document_view_url(
                db, "invoice", invoice.id, tenant.id, contact.email if contact else None
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


# ---------------------------------------------------------------------------
# W1-C NIGHTLY AI ROLLUP + ALERTS
#
# A second asyncio loop (``rollup_loop``) started from the lifespan next to
# ``reminder_loop``. Once per UTC day (default 02:30) it:
#
# 1. Re-folds the previous UTC day from ``ai_call_events`` into
#    ``ai_rollup_user_day`` (tenant/user/feature) and ``ai_rollup_feature_day``
#    (platform-wide). The fold deletes and re-inserts that day's rows inside
#    a global advisory lock, so it is idempotent and safe to re-run.
# 2. Refreshes the USD→GBP rate when the newest ``fx_rates`` row is older
#    than ``FX_REFRESH_MAX_AGE_DAYS`` (weekly cadence; failures keep the
#    last-known rate).
# 3. Fires budget alerts (50/80/100% of ``AI_MONTHLY_BUDGET_GBP``, each once
#    per month), anomaly alerts (daily cost > 3x trailing-7-day mean;
#    daily latency p95 > 2x trailing-7-day p95, each once per day), and
#    fair-use alerts (an org's current-month AI action count reaches
#    ``AI_FAIR_USE_MONTHLY_THRESHOLD``, once per org per month — internal ops
#    only, never customer-visible), all deduped via the ``ai_alert_state``
#    table. An unhandled exception in the pass itself fires a once-per-day
#    ``rollup_failed`` alert and the loop keeps its schedule.
#
# The loop never raises; per-step failures are logged and the next step still
# runs (alerts must not be lost because the FX endpoint is down).
# ---------------------------------------------------------------------------

# Advisory-lock namespace for the rollup job (distinct from the reminder
# scheduler's 727). One global lock covers the whole fold: there is exactly
# one (date) target per run, so per-tenant locking buys nothing here.
_ROLLUP_LOCK_NAMESPACE = 728

_OUTCOME_FEATURE = "outcome"
_QUOTE_SENT_OUTCOME = "quote_sent"

# Monthly budget thresholds, checked in ascending order; each fires once per
# month via ai_alert_state.
_BUDGET_THRESHOLDS: tuple[tuple[str, Decimal], ...] = (
    ("budget_50", Decimal("0.50")),
    ("budget_80", Decimal("0.80")),
    ("budget_100", Decimal("1.00")),
)

_COST_SPIKE_FACTOR = Decimal("3")
_LATENCY_SPIKE_FACTOR = 2.0
# Require at least this many trailing days of data before anomaly detection
# fires, so a quiet first week does not page anyone.
_ANOMALY_MIN_TRAILING_DAYS = 3


class _Measures:
    """Accumulator for one rollup group (user-day or feature-day)."""

    __slots__ = (
        "cost_gbp",
        "est_cost_usd",
        "generations",
        "latencies",
        "quotes_sent",
        "retries",
        "tokens_cached",
        "tokens_input",
        "tokens_output",
    )

    def __init__(self) -> None:
        self.generations = 0
        self.retries = 0
        self.tokens_input = 0
        self.tokens_output = 0
        self.tokens_cached = 0
        self.est_cost_usd = Decimal("0")
        self.cost_gbp = Decimal("0")
        self.latencies: list[float] = []
        self.quotes_sent = 0

    def add(self, event: AiCallEvent) -> None:
        if event.feature == _OUTCOME_FEATURE:
            if (event.raw_payload or {}).get("outcome") == _QUOTE_SENT_OUTCOME:
                self.quotes_sent += 1
            return
        if event.status == "success":
            self.generations += 1
        else:
            self.retries += 1
        self.tokens_input += event.gen_ai_usage_input_tokens or 0
        self.tokens_output += event.gen_ai_usage_output_tokens or 0
        self.tokens_cached += event.gen_ai_usage_cached_input_tokens or 0
        self.est_cost_usd += event.est_cost_usd or Decimal("0")
        self.cost_gbp += event.cost_gbp or Decimal("0")
        if event.latency_seconds is not None:
            self.latencies.append(event.latency_seconds)


def _percentile(sorted_values: list[float], pct: int) -> float | None:
    """Nearest-rank percentile of an ascending-sorted list (None when empty)."""
    if not sorted_values:
        return None
    index = max(0, math.ceil(pct / 100 * len(sorted_values)) - 1)
    return sorted_values[index]


def _mean_decimal(values: list[Decimal]) -> Decimal:
    """Arithmetic mean of a non-empty Decimal list."""
    return sum(values, Decimal("0")) / Decimal(len(values))


def fold_events(events: list[AiCallEvent]) -> dict[tuple[Any, ...], _Measures]:
    """Group raw events into rollup measures keyed by (tenant_id, user_id, feature).

    Pure function over already-fetched events so the fold math is unit-testable
    without a database. Events with ``tenant_id=None`` (demo/embedding) are
    excluded — they are platform-rollups-only and land in
    :func:`fold_events_platform` instead.
    """
    groups: dict[tuple[Any, ...], _Measures] = {}
    for event in events:
        if event.tenant_id is None:
            continue
        key = (event.tenant_id, event.user_id, event.feature)
        groups.setdefault(key, _Measures()).add(event)
    return groups


def fold_events_platform(events: list[AiCallEvent]) -> dict[str, _Measures]:
    """Group raw events into platform-wide measures keyed by feature."""
    groups: dict[str, _Measures] = {}
    for event in events:
        groups.setdefault(event.feature, _Measures()).add(event)
    return groups


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    """True when ``table_name`` exists in the public schema.

    Used to fold ``ai_draft_feedback`` defensively: that table is built by a
    concurrent workstream, so the rollup must work whether or not it has
    landed yet.
    """
    result = await db.scalar(select(func.to_regclass(f"public.{table_name}")))
    return result is not None


async def _load_keep_rates(
    db: AsyncSession, day_start: datetime, day_end: datetime
) -> tuple[dict[tuple[Any, ...], Decimal], dict[str, Decimal]]:
    """Average keep_rate per group from ai_draft_feedback, when that table exists.

    Feedback rows are attributed to the tenant/user/feature of the generation
    event they reference (``generation_event_id`` → ``ai_call_events``). Raw
    SQL because the ORM model lives in a different workstream's tree.
    Returns (user_day_rates, feature_day_rates); both empty when the table is
    absent.
    """
    if not await _table_exists(db, "ai_draft_feedback"):
        return {}, {}
    rows = (
        await db.execute(
            text(
                "SELECT e.tenant_id, e.user_id, e.feature, AVG(f.keep_rate) "
                "FROM ai_draft_feedback f "
                "JOIN ai_call_events e ON e.id = f.generation_event_id "
                "WHERE f.created_at >= :start AND f.created_at < :end "
                "GROUP BY e.tenant_id, e.user_id, e.feature"
            ),
            {"start": day_start, "end": day_end},
        )
    ).all()
    user_day: dict[tuple[Any, ...], Decimal] = {}
    feature_day: dict[str, list[Decimal]] = {}
    for tenant_id, user_id, feature, avg_keep in rows:
        if avg_keep is None:
            continue
        rate = Decimal(str(avg_keep)).quantize(Decimal("0.001"))
        if tenant_id is not None:
            user_day[(tenant_id, user_id, feature)] = rate
        feature_day.setdefault(feature, []).append(rate)
    feature_rates = {
        feature: _mean_decimal(rates).quantize(Decimal("0.001"))
        for feature, rates in feature_day.items()
    }
    return user_day, feature_rates


async def _events_for_day(
    db: AsyncSession, day_start: datetime, day_end: datetime
) -> list[AiCallEvent]:
    return list(
        (
            await db.execute(
                select(AiCallEvent).where(
                    AiCallEvent.created_at >= day_start,
                    AiCallEvent.created_at < day_end,
                )
            )
        )
        .scalars()
        .all()
    )


def _user_day_row(
    day: date, key: tuple[Any, ...], measures: _Measures, keep_rates: dict[tuple[Any, ...], Decimal]
) -> AiRollupUserDay:
    tenant_id, user_id, feature = key
    ordered = sorted(measures.latencies)
    return AiRollupUserDay(
        date=day,
        tenant_id=tenant_id,
        user_id=user_id,
        feature=feature,
        generations=measures.generations,
        retries=measures.retries,
        tokens_input=measures.tokens_input,
        tokens_output=measures.tokens_output,
        tokens_cached=measures.tokens_cached,
        est_cost_usd=measures.est_cost_usd.quantize(Decimal("0.000001")),
        cost_gbp=measures.cost_gbp.quantize(Decimal("0.0001")),
        latency_p50=_percentile(ordered, 50),
        latency_p95=_percentile(ordered, 95),
        avg_keep_rate=keep_rates.get(key),
        quotes_sent=measures.quotes_sent,
    )


def _feature_day_row(
    day: date, feature: str, measures: _Measures, keep_rates: dict[str, Decimal]
) -> AiRollupFeatureDay:
    ordered = sorted(measures.latencies)
    return AiRollupFeatureDay(
        date=day,
        feature=feature,
        generations=measures.generations,
        retries=measures.retries,
        tokens_input=measures.tokens_input,
        tokens_output=measures.tokens_output,
        tokens_cached=measures.tokens_cached,
        est_cost_usd=measures.est_cost_usd.quantize(Decimal("0.000001")),
        cost_gbp=measures.cost_gbp.quantize(Decimal("0.0001")),
        latency_p50=_percentile(ordered, 50),
        latency_p95=_percentile(ordered, 95),
        avg_keep_rate=keep_rates.get(feature),
        quotes_sent=measures.quotes_sent,
    )


async def run_rollup_for_day(db: AsyncSession, day: date) -> dict[str, int]:
    """Idempotently re-fold one UTC day of ai_call_events into both rollup tables.

    Takes the global rollup advisory lock for the transaction; a concurrent
    replica folds nothing and reports ``locked=1``. Deletes + re-inserts the
    day's rows so re-runs converge to the same state.
    """
    locked = (
        await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:namespace, hashtext(:key))"),
            {"namespace": _ROLLUP_LOCK_NAMESPACE, "key": "ai_rollup"},
        )
    ).scalar()
    if not locked:
        logger.info("rollup_locked_elsewhere", date=str(day))
        return {"user_day_rows": 0, "feature_day_rows": 0, "locked": 1}

    day_start = datetime(day.year, day.month, day.day)
    day_end = day_start + timedelta(days=1)
    events = await _events_for_day(db, day_start, day_end)
    user_keep_rates, feature_keep_rates = await _load_keep_rates(db, day_start, day_end)

    await db.execute(delete(AiRollupUserDay).where(AiRollupUserDay.date == day))
    await db.execute(delete(AiRollupFeatureDay).where(AiRollupFeatureDay.date == day))

    user_rows = [
        _user_day_row(day, key, measures, user_keep_rates)
        for key, measures in fold_events(events).items()
    ]
    feature_rows = [
        _feature_day_row(day, feature, measures, feature_keep_rates)
        for feature, measures in fold_events_platform(events).items()
    ]
    db.add_all(user_rows)
    db.add_all(feature_rows)
    await db.commit()
    return {
        "user_day_rows": len(user_rows),
        "feature_day_rows": len(feature_rows),
        "locked": 0,
    }


async def _maybe_refresh_fx(db: AsyncSession, today: date) -> str:
    """Refresh USD→GBP when the newest stored rate is stale. Never raises."""
    latest = await db.scalar(select(FxRate).order_by(FxRate.rate_date.desc()).limit(1))
    if latest is not None and (today - latest.rate_date).days < FX_REFRESH_MAX_AGE_DAYS:
        return "fresh"
    rate = await fetch_usd_gbp_rate()
    if rate is None:
        logger.warning("fx_refresh_skipped", reason="fetch_failed_keeping_last_known")
        return "fetch_failed"
    await store_fx_rate(db, today, Decimal(str(rate)))
    await db.commit()
    logger.info("fx_rate_refreshed", rate_date=str(today), usd_gbp=rate)
    return "refreshed"


async def _fire_alert_once(
    db: AsyncSession, period: str, threshold: str, subject: str, body: str
) -> bool:
    """Dispatch an alert unless (period, threshold) already fired. Returns fired?."""
    existing = await db.scalar(
        select(AiAlertState).where(
            AiAlertState.period == period, AiAlertState.threshold == threshold
        )
    )
    if existing is not None:
        return False
    db.add(
        AiAlertState(period=period, threshold=threshold, payload={"subject": subject, "body": body})
    )
    await db.commit()
    channels = await send_alert(subject, body)
    logger.info("ai_alert_fired", period=period, threshold=threshold, channels=channels)
    return True


async def _check_budget_alerts(db: AsyncSession, day: date) -> list[str]:
    """Fire 50/80/100% monthly-budget alerts against feature-day rollups."""
    if not AI_MONTHLY_BUDGET_GBP:
        return []
    try:
        budget = Decimal(AI_MONTHLY_BUDGET_GBP)
    except Exception:
        logger.warning("ai_budget_invalid", value=AI_MONTHLY_BUDGET_GBP)
        return []
    if budget <= 0:
        return []
    month_start = date(day.year, day.month, 1)
    month_end = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    spent = await db.scalar(
        select(func.coalesce(func.sum(AiRollupFeatureDay.cost_gbp), 0)).where(
            AiRollupFeatureDay.date >= month_start,
            AiRollupFeatureDay.date < month_end,
        )
    )
    spent_gbp = Decimal(str(spent or 0))
    period = f"{day.year:04d}-{day.month:02d}"
    fired: list[str] = []
    for threshold_name, fraction in _BUDGET_THRESHOLDS:
        if spent_gbp < budget * fraction:
            break
        subject = f"AI spend {fraction * 100:.0f}% of monthly budget ({period})"
        body = (
            f"Platform AI spend for {period} is £{spent_gbp:.2f} — "
            f"{fraction * 100:.0f}% of the £{budget:.2f} monthly budget."
        )
        if await _fire_alert_once(db, period, threshold_name, subject, body):
            fired.append(threshold_name)
    return fired


async def _daily_platform_latency_p95(
    db: AsyncSession, start: date, end: date
) -> dict[date, float]:
    """Per-day platform latency p95 over non-outcome events in [start, end)."""
    rows = (
        await db.execute(
            select(AiCallEvent.created_at, AiCallEvent.latency_seconds).where(
                AiCallEvent.created_at >= datetime(start.year, start.month, start.day),
                AiCallEvent.created_at < datetime(end.year, end.month, end.day),
                AiCallEvent.feature != _OUTCOME_FEATURE,
                AiCallEvent.latency_seconds.isnot(None),
            )
        )
    ).all()
    by_day: dict[date, list[float]] = {}
    for created_at, latency in rows:
        by_day.setdefault(created_at.date(), []).append(latency)
    result: dict[date, float] = {}
    for day, latencies in by_day.items():
        p95 = _percentile(sorted(latencies), 95)
        if p95 is not None:
            result[day] = p95
    return result


async def _check_anomaly_alerts(db: AsyncSession, day: date) -> list[str]:
    """Fire daily cost/latency anomaly alerts vs the trailing 7 days."""
    fired: list[str] = []
    period = day.isoformat()
    trailing_start = day - timedelta(days=7)

    cost_rows = (
        await db.execute(
            select(AiRollupFeatureDay.date, func.sum(AiRollupFeatureDay.cost_gbp))
            .where(
                AiRollupFeatureDay.date >= trailing_start,
                AiRollupFeatureDay.date <= day,
            )
            .group_by(AiRollupFeatureDay.date)
        )
    ).all()
    daily_cost = {row_date: Decimal(str(total)) for row_date, total in cost_rows}
    trailing_costs = [total for row_date, total in daily_cost.items() if row_date < day]
    today_cost = daily_cost.get(day, Decimal("0"))
    if len(trailing_costs) >= _ANOMALY_MIN_TRAILING_DAYS:
        mean_cost = _mean_decimal(trailing_costs)
        if mean_cost > 0 and today_cost > mean_cost * _COST_SPIKE_FACTOR:
            subject = f"AI daily cost spike ({period})"
            body = (
                f"Platform AI spend on {period} was £{today_cost:.2f} — more than "
                f"{_COST_SPIKE_FACTOR}x the trailing-7-day mean of £{mean_cost:.2f}."
            )
            if await _fire_alert_once(db, period, "cost_spike", subject, body):
                fired.append("cost_spike")

    latency_end = day + timedelta(days=1)
    daily_p95 = await _daily_platform_latency_p95(db, trailing_start, latency_end)
    trailing_p95 = [p95 for row_date, p95 in daily_p95.items() if row_date < day]
    today_p95 = daily_p95.get(day)
    if (
        today_p95 is not None
        and len(trailing_p95) >= _ANOMALY_MIN_TRAILING_DAYS
        and (mean_p95 := sum(trailing_p95) / len(trailing_p95)) > 0
        and today_p95 > mean_p95 * _LATENCY_SPIKE_FACTOR
    ):
        subject = f"AI latency p95 spike ({period})"
        body = (
            f"Platform AI latency p95 on {period} was {today_p95:.2f}s — more than "
            f"{_LATENCY_SPIKE_FACTOR}x the trailing-7-day mean of {mean_p95:.2f}s."
        )
        if await _fire_alert_once(db, period, "latency_p95_spike", subject, body):
            fired.append("latency_p95_spike")
    return fired


async def _check_fair_use_alerts(db: AsyncSession, day: date) -> list[str]:
    """Fire one internal ops alert per org per month at the fair-use cap.

    Counts each tenant's current-month ``ai_call_events`` (outcome rows
    excluded — they carry no AI spend) and alerts ops when the count reaches
    ``AI_FAIR_USE_MONTHLY_THRESHOLD``. Internal only: this must never surface
    to the customer. Deduped per (tenant, month) via ``ai_alert_state``; the
    tenant id rides in the ``threshold`` column (``fair_use:<uuid>``) so the
    ``period`` stays the shared ``YYYY-MM`` shape.
    """
    if AI_FAIR_USE_MONTHLY_THRESHOLD <= 0:
        return []
    month_start = datetime(day.year, day.month, 1)
    month_end = datetime(day.year + (day.month == 12), day.month % 12 + 1, 1)
    rows = (
        await db.execute(
            select(AiCallEvent.tenant_id, func.count(AiCallEvent.id))
            .where(
                AiCallEvent.tenant_id.isnot(None),
                AiCallEvent.feature != _OUTCOME_FEATURE,
                AiCallEvent.created_at >= month_start,
                AiCallEvent.created_at < month_end,
            )
            .group_by(AiCallEvent.tenant_id)
            .having(func.count(AiCallEvent.id) >= AI_FAIR_USE_MONTHLY_THRESHOLD)
        )
    ).all()
    period = f"{day.year:04d}-{day.month:02d}"
    fired: list[str] = []
    for tenant_id, action_count in rows:
        subject = f"AI fair-use threshold reached by tenant ({period})"
        body = (
            f"Tenant {tenant_id} has used {action_count} AI actions in {period}, "
            f"reaching the fair-use threshold of {AI_FAIR_USE_MONTHLY_THRESHOLD}. "
            "Internal ops alert — review the tenant's usage; nothing is customer-visible."
        )
        if await _fire_alert_once(db, period, f"fair_use:{tenant_id}", subject, body):
            fired.append(str(tenant_id))
    return fired


async def _run_rollup_tick(db: AsyncSession, now: datetime) -> dict[str, Any]:
    """One nightly pass: fold yesterday, refresh FX, evaluate alerts."""
    yesterday = (now - timedelta(days=1)).date()
    summary: dict[str, Any] = {"date": yesterday.isoformat()}
    summary.update(await run_rollup_for_day(db, yesterday))
    summary["fx"] = await _maybe_refresh_fx(db, now.date())
    try:
        summary["budget_alerts"] = await _check_budget_alerts(db, yesterday)
        summary["anomaly_alerts"] = await _check_anomaly_alerts(db, yesterday)
        summary["fair_use_alerts"] = await _check_fair_use_alerts(db, yesterday)
    except Exception as exc:
        # Alert evaluation must not be lost with the fold — the rollup rows
        # are already committed; log and continue.
        await db.rollback()
        summary["alert_error"] = type(exc).__name__
        logger.error(
            "ai_alert_check_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
    return summary


async def run_rollup_tick(
    db: AsyncSession | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Run one nightly rollup+alert pass (``db`` injectable for tests)."""
    now = now or datetime.utcnow()
    if db is not None:
        return await _run_rollup_tick(db, now)
    async with AsyncSessionLocal() as session:
        return await _run_rollup_tick(session, now)


# In-process fallback dedupe for the rollup-failure alert, used only when the
# database itself is the failure (the ai_alert_state write cannot land).
_rollup_failure_alerted_in_process: set[str] = set()


async def _alert_rollup_failure(exc: Exception, db: AsyncSession | None = None) -> None:
    """Fire a once-per-day ops alert when the nightly pass itself crashes.

    Deduped through ``ai_alert_state`` (``threshold="rollup_failed"``, period
    = today's date). When the database itself is the failure the dedupe write
    cannot land, so an in-process set bounds the blast radius to one send per
    day per replica. Never raises — the caller is the scheduler's last line
    of defence.
    """
    period = datetime.utcnow().date().isoformat()
    subject = f"AI rollup job failed ({period})"
    body = (
        f"The nightly AI rollup pass raised {type(exc).__name__}: {str(exc)[:300]}. "
        "The scheduler loop is still running and will retry on the next tick."
    )
    try:
        if db is not None:
            await _fire_alert_once(db, period, "rollup_failed", subject, body)
            return
        async with AsyncSessionLocal() as session:
            await _fire_alert_once(session, period, "rollup_failed", subject, body)
    except Exception as fallback_exc:
        if period in _rollup_failure_alerted_in_process:
            return
        _rollup_failure_alerted_in_process.add(period)
        logger.warning(
            "rollup_failure_alert_dedupe_unavailable",
            error_type=type(fallback_exc).__name__,
            error=str(fallback_exc)[:300],
        )
        await send_alert(subject, body)


async def rollup_loop(stop: asyncio.Event) -> None:
    """Scheduler task body: run the nightly pass once per UTC day.

    Ticks every ``ROLLUP_TICK_SECONDS`` but only acts once the wall clock is
    past ``ROLLUP_RUN_HOUR_UTC``:``ROLLUP_RUN_MINUTE_UTC`` (default 02:30
    UTC); a process that boots after the run time catches up the missed fold
    on its first tick. The fold itself is idempotent, so a crash between fold
    and bookkeeping is harmless. The task never raises.
    """
    logger.info(
        "rollup_scheduler_started",
        tick_seconds=ROLLUP_TICK_SECONDS,
        run_at_utc=f"{ROLLUP_RUN_HOUR_UTC:02d}:{ROLLUP_RUN_MINUTE_UTC:02d}",
    )
    last_run_date: date | None = None
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=ROLLUP_TICK_SECONDS)
            break
        except TimeoutError:
            pass
        now = datetime.utcnow()
        run_at = now.replace(
            hour=ROLLUP_RUN_HOUR_UTC,
            minute=ROLLUP_RUN_MINUTE_UTC,
            second=0,
            microsecond=0,
        )
        if now < run_at or last_run_date == now.date():
            continue
        try:
            summary = await run_rollup_tick()
            last_run_date = now.date()
            logger.info("rollup_tick_complete", **summary)
        except Exception as exc:
            logger.error(
                "rollup_tick_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
            # The pass crashed before its own per-step guards (e.g. the fold
            # itself raised): alert ops once per day and keep the schedule.
            await _alert_rollup_failure(exc)
    logger.info("rollup_scheduler_stopped")
