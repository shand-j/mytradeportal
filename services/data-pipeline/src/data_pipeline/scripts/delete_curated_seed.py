"""Remove curated seed catalogue items from Postgres and Qdrant.

Usage:
    python -m data_pipeline.scripts.delete_curated_seed --dry-run
    python -m data_pipeline.scripts.delete_curated_seed --execute

This script is idempotent: running it multiple times will delete no additional
rows once the curated seed data has been removed.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from data_pipeline.database import get_db_session
from data_pipeline.models import CostItem
from data_pipeline.qdrant import get_qdrant_client

SOURCE = "curated_seed"


async def count_by_source() -> dict[str, int]:
    """Return a mapping of cost_item source -> row count."""
    async with get_db_session() as db:
        rows = await db.execute(
            select(CostItem.source, func.count(CostItem.id)).group_by(CostItem.source)
        )
        return dict(rows.all())


async def delete_curated_seed(execute: bool) -> dict[str, int]:
    """Delete curated seed items from Postgres and Qdrant and return counts."""
    async with get_db_session() as db:
        result = await db.execute(select(CostItem.id).where(CostItem.source == SOURCE))
        ids = [row[0] for row in result.all()]

        print(f"Found {len(ids)} cost_items with source={SOURCE!r}")

        if not ids:
            return {"postgres_deleted": 0, "qdrant_deleted": 0}

        if execute:
            await db.execute(CostItem.__table__.delete().where(CostItem.source == SOURCE))
            await db.commit()

            qdrant = get_qdrant_client()
            await qdrant.delete(
                collection_name=CostItem.__table__.name,
                points_selector=[str(id_) for id_ in ids],
            )
            print(f"Deleted {len(ids)} points from Qdrant")
        else:
            print("Dry run: no rows deleted. Use --execute to delete.")

        return {"postgres_deleted": len(ids), "qdrant_deleted": len(ids) if execute else 0}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete curated seed catalogue items from Postgres and Qdrant"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows; without this flag the script runs in dry-run mode",
    )
    args = parser.parse_args()

    counts = asyncio.run(count_by_source())
    print("Current cost_items by source:")
    for source, count in sorted(counts.items()):
        print(f"  {source}: {count}")

    result = asyncio.run(delete_curated_seed(execute=args.execute))
    print(f"Postgres rows affected: {result['postgres_deleted']}")
    print(f"Qdrant points deleted: {result['qdrant_deleted']}")


if __name__ == "__main__":
    main()
