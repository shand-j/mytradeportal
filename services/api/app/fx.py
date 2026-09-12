"""USD→GBP exchange-rate lookup for AI cost attribution.

``AiCallEvent.cost_gbp`` is stamped at write time with the rate in force on
the event's date, so historical rows never drift when the rate moves. Rates
live in the ``fx_rates`` table (plain ``Base``, not tenant-scoped), populated
by a weekly refresh job owned by another workstream — this module is the read
path plus the ``store_fx_rate`` upsert helper that job uses.

Fallback chain (never raises for a missing rate):
    1. latest ``fx_rates`` row with ``rate_date <= at_date``
    2. latest ``fx_rates`` row overall (table populated but stale/future-dated)
    3. ``settings.fx_usd_gbp_fallback_rate`` (constant, default 0.79)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.config import settings
from app.models import FxRate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("api.fx")


async def store_fx_rate(db: AsyncSession, rate_date: date, usd_gbp: Decimal) -> FxRate:
    """Insert or update the USD→GBP rate for ``rate_date`` (idempotent upsert).

    The caller commits. Used by the weekly refresh job; safe to re-run for the
    same date — the latest fetch wins.
    """
    row = await db.get(FxRate, rate_date)
    if row is None:
        row = FxRate(rate_date=rate_date, usd_gbp=usd_gbp)
        db.add(row)
    else:
        row.usd_gbp = usd_gbp
    await db.flush()
    return row


async def get_usd_gbp_rate(db: AsyncSession, at_date: date | None = None) -> tuple[Decimal, date]:
    """Return ``(rate, rate_date)`` for ``at_date`` (today when omitted).

    ``rate_date`` is the date the returned rate was actually recorded for —
    callers stamp it on the event alongside the rate so stale-rate fallbacks
    are visible in the data. Falls back to the configured constant when the
    table is empty.
    """
    day = at_date or date.today()
    row = await db.scalar(
        select(FxRate).where(FxRate.rate_date <= day).order_by(FxRate.rate_date.desc()).limit(1)
    )
    if row is None:
        row = await db.scalar(select(FxRate).order_by(FxRate.rate_date.desc()).limit(1))
    if row is not None:
        return row.usd_gbp, row.rate_date
    logger.warning(
        "fx_rate_fallback",
        reason="fx_rates_empty",
        fallback_rate=settings.fx_usd_gbp_fallback_rate,
    )
    return Decimal(str(settings.fx_usd_gbp_fallback_rate)), day
