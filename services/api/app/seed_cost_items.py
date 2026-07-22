"""Seed the shared cost database with UK electrical cost items."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from qdrant_client.models import PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import CostItem
from app.qdrant import ensure_collection, get_qdrant_client
from app.rag.retrieval import embed_texts, get_embedding_dimension

DATA_PATH = Path(__file__).with_name("data") / "uk_electrical_cost_items.json"
TRADE = "electrical"
REGION = "UK"


def _load_items() -> list[dict[str, Any]]:
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


async def seed_cost_items(
    db: AsyncSession,
    skip_qdrant: bool = False,
) -> int:
    """Insert seed cost items into Postgres and Qdrant.

    Returns the number of new items inserted.
    """
    raw_items = _load_items()
    if not raw_items:
        return 0

    # Guard: do not re-introduce seed data when real scraped supplier data is
    # already loaded. Seed prices are intentionally inactive in the MVP.
    pipeline_check = await db.execute(
        select(CostItem.id).where(CostItem.source == "domestic_pipeline").limit(1)
    )
    if pipeline_check.scalar_one_or_none() is not None:
        print("Skipping seed: domestic_pipeline cost items already present.")
        return 0

    codes = [item["code"] for item in raw_items]
    result = await db.execute(select(CostItem).where(CostItem.code.in_(codes)))
    existing_by_code = {item.code: item for item in result.scalars().all()}

    new_items: list[CostItem] = []
    for raw in raw_items:
        if raw["code"] in existing_by_code:
            continue
        item = CostItem(
            code=raw["code"],
            trade=TRADE,
            region=REGION,
            category=raw["category"],
            description=raw["description"],
            unit=raw["unit"],
            unit_price=Decimal(raw["unit_price"]),
            currency="GBP",
            is_active=True,
            source="seed",
            extra_data={},
        )
        db.add(item)
        new_items.append(item)

    await db.commit()
    for item in new_items:
        await db.refresh(item)

    if skip_qdrant or not new_items:
        return len(new_items)

    qdrant = get_qdrant_client()
    await ensure_collection(
        qdrant,
        settings.qdrant_collection_name,
        vector_size=get_embedding_dimension(),
    )

    descriptions = [item.description for item in new_items]
    vectors = await embed_texts(descriptions)
    points = [
        PointStruct(
            id=str(item.id),
            vector=vector,
            payload={
                "code": item.code,
                "trade": item.trade,
                "region": item.region,
                "category": item.category,
                "description": item.description,
                "unit": item.unit,
                "unit_price": str(item.unit_price),
                "currency": item.currency,
                "is_active": item.is_active,
                "source": item.source,
            },
        )
        for item, vector in zip(new_items, vectors, strict=True)
    ]
    await qdrant.upsert(collection_name=settings.qdrant_collection_name, points=points)

    return len(new_items)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        count = await seed_cost_items(db)
        print(f"Seeded {count} new cost items.")


if __name__ == "__main__":
    asyncio.run(main())
