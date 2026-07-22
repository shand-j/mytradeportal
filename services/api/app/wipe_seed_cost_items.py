"""Remove all seed cost items from Postgres and Qdrant.

This is a one-off maintenance script. Seed data is no longer used in the MVP;
quotes must be grounded in scraped domestic-pipeline prices only.
"""

import asyncio

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import delete, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import CostItem
from app.qdrant import get_qdrant_client


async def wipe_seed_cost_items() -> dict[str, int]:
    """Delete cost items where source == 'seed' from Postgres and Qdrant."""
    qdrant = get_qdrant_client()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CostItem.id).where(CostItem.source == "seed")
        )
        ids: list[str] = [str(row[0]) for row in result.all()]

        await db.execute(delete(CostItem).where(CostItem.source == "seed"))
        await db.commit()

    if ids:
        await qdrant.delete(
            collection_name=settings.qdrant_collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value="seed"))]
            ),
        )

    return {"postgres_deleted": len(ids), "qdrant_deleted": len(ids)}


async def main() -> None:
    counts = await wipe_seed_cost_items()
    print(f"Wiped seed cost items: {counts['postgres_deleted']}")


if __name__ == "__main__":
    asyncio.run(main())
