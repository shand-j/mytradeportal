"""Re-index every cost_items row in Postgres into Qdrant — no scraping.

Use after restoring cost_items from another environment (e.g. a local dump)
so the vector index matches the database without an Apify run. The ingest
``ensure_collection`` recreates the collection when the configured embedding
dimensions changed (logged loudly), so this also repairs an index wiped or
left stale by an embedding-model bump.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from data_pipeline.database import get_db_session
from data_pipeline.loader import _index_in_qdrant
from data_pipeline.models import CostItem


async def reindex() -> int:
    async with get_db_session() as db:
        result = await db.execute(select(CostItem).where(CostItem.is_active.is_(True)))
        items = list(result.scalars().all())
    if not items:
        print("No active cost_items rows found — nothing indexed")
        return 0
    await _index_in_qdrant(items)
    print(f"Indexed {len(items)} cost items from Postgres into Qdrant")
    return len(items)


def main() -> None:
    asyncio.run(reindex())


if __name__ == "__main__":
    main()
