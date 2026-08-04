"""Tests for the cleanup_seed_data.py pre-deploy script.

Focuses on the Postgres deletion path (idempotent DELETE of DOM-SEED-* and
curated_seed rows). The Qdrant path is best-effort and is exercised only when
Qdrant is available; it never fails the deploy, so we only assert graceful
no-op behaviour when Qdrant is missing.

Uses ``AsyncSessionLocal`` directly (rather than the ``client``/``db``
fixtures) because the script opens its own session outside any per-test
savepoint. This keeps the test aligned with how the pre-deploy step actually
runs.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from app.database import AsyncSessionLocal
from app.models import CostItem
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


async def _wipe_cost_items() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM cost_items"))
        await session.commit()


@pytest.mark.asyncio
async def test_delete_postgres_seed_rows_removes_expected(test_database_url: str) -> None:
    from cleanup_seed_data import _delete_postgres_seed_rows

    await _wipe_cost_items()
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                CostItem(
                    code="DOM-SEED-CU-10WAY",
                    trade="electrical",
                    region="UK",
                    category="Consumer Units",
                    description="Seed CU",
                    unit="each",
                    unit_price=Decimal("100.0000"),
                    currency="GBP",
                    is_active=True,
                    source="domestic_pipeline",
                    extra_data={"supplier": "seed"},
                ),
                CostItem(
                    code="CURATED-1",
                    trade="electrical",
                    region="UK",
                    category="Cable",
                    description="Curated seed row",
                    unit="m",
                    unit_price=Decimal("0.5000"),
                    currency="GBP",
                    is_active=True,
                    source="curated_seed",
                    extra_data={},
                ),
                CostItem(
                    code="DOM-screwfix-42",
                    trade="electrical",
                    region="UK",
                    category="Cable",
                    description="Real pipeline row",
                    unit="m",
                    unit_price=Decimal("0.7200"),
                    currency="GBP",
                    is_active=True,
                    source="domestic_pipeline",
                    extra_data={"supplier": "Screwfix"},
                ),
            ]
        )
        await session.commit()

    try:
        dom_seed_deleted, curated_deleted = await _delete_postgres_seed_rows()
        assert dom_seed_deleted == 1
        assert curated_deleted == 1

        async with AsyncSessionLocal() as session:
            remaining = await session.execute(text("SELECT code FROM cost_items ORDER BY code"))
            codes = [row[0] for row in remaining.fetchall()]
        assert codes == ["DOM-screwfix-42"]
    finally:
        await _wipe_cost_items()


@pytest.mark.asyncio
async def test_delete_postgres_seed_rows_is_idempotent(test_database_url: str) -> None:
    from cleanup_seed_data import _delete_postgres_seed_rows

    await _wipe_cost_items()
    try:
        dom_seed_deleted, curated_deleted = await _delete_postgres_seed_rows()
        assert dom_seed_deleted == 0
        assert curated_deleted == 0

        dom_seed_deleted, curated_deleted = await _delete_postgres_seed_rows()
        assert dom_seed_deleted == 0
        assert curated_deleted == 0
    finally:
        await _wipe_cost_items()
