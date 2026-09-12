"""Tests for the USD→GBP rate lookup fallback chain."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.config import settings
from app.fx import get_usd_gbp_rate, store_fx_rate
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_fallback_constant_when_table_empty(db: AsyncSession) -> None:
    rate, rate_date = await get_usd_gbp_rate(db)
    assert rate == Decimal(str(settings.fx_usd_gbp_fallback_rate))
    assert rate_date == date.today()


@pytest.mark.asyncio
async def test_latest_rate_on_or_before_the_date_wins(db: AsyncSession) -> None:
    today = date.today()
    await store_fx_rate(db, today - timedelta(days=7), Decimal("0.75"))
    await store_fx_rate(db, today - timedelta(days=1), Decimal("0.78"))
    await store_fx_rate(db, today + timedelta(days=1), Decimal("0.99"))

    rate, rate_date = await get_usd_gbp_rate(db, today)
    assert rate == Decimal("0.78")
    assert rate_date == today - timedelta(days=1)


@pytest.mark.asyncio
async def test_date_before_all_rows_uses_earliest_known(db: AsyncSession) -> None:
    await store_fx_rate(db, date.today(), Decimal("0.80"))
    rate, rate_date = await get_usd_gbp_rate(db, date.today() - timedelta(days=30))
    assert rate == Decimal("0.80")
    assert rate_date == date.today()


@pytest.mark.asyncio
async def test_store_fx_rate_upserts_same_date(db: AsyncSession) -> None:
    day = date.today()
    await store_fx_rate(db, day, Decimal("0.75"))
    await store_fx_rate(db, day, Decimal("0.81"))
    rate, _ = await get_usd_gbp_rate(db, day)
    assert rate == Decimal("0.81")
