"""Load the curated electrical seed catalogue into Postgres and Qdrant.

This is intentionally separate from the scraper pipeline so that curated items
are not deactivated when the supplier scrape runs.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from qdrant_client.models import PointStruct
from sqlalchemy import select

from data_pipeline.config import settings
from data_pipeline.database import get_db_session
from data_pipeline.embeddings import embed_texts, get_embedding_dimension
from data_pipeline.models import CostItem
from data_pipeline.qdrant import ensure_collection, get_qdrant_client

TRADE = "electrical"
REGION = "UK"
SOURCE = "curated_seed"
BATCH_SIZE = 500

SEED_PATH = Path(__file__).parent / "data" / "curated_electrical_items.json"


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def _load_seed() -> list[dict[str, Any]]:
    with SEED_PATH.open() as fh:
        return json.load(fh)


def _build_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    now = datetime.utcnow().isoformat()
    for record in records:
        unit_price = _to_decimal(record["unit_price"])
        retail_incl_vat = (unit_price * Decimal("1.20")).quantize(Decimal("0.01"))
        extra_data = {
            "supplier": record.get("supplier", SOURCE),
            "brand": record.get("brand"),
            "sku": record.get("sku", record["code"]),
            "product_url": record.get("product_url"),
            "retail_price_incl_vat": float(retail_incl_vat),
            "scraped_at": now,
        }
        candidates.append(
            {
                "code": record["code"],
                "trade": TRADE,
                "region": REGION,
                "category": record["category"],
                "description": record["description"],
                "unit": record["unit"],
                "unit_price": unit_price,
                "currency": "GBP",
                "is_active": True,
                "source": SOURCE,
                "extra_data": extra_data,
            }
        )
    return candidates


async def _upsert_cost_items(candidates: list[dict[str, Any]]) -> list[CostItem]:
    async with get_db_session() as db:
        codes = [c["code"] for c in candidates]
        result = await db.execute(select(CostItem).where(CostItem.code.in_(codes)))
        existing_by_code = {item.code: item for item in result.scalars().all()}

        updated_items: list[CostItem] = []
        for candidate in candidates:
            existing = existing_by_code.get(candidate["code"])
            if existing:
                existing.description = candidate["description"]
                existing.category = candidate["category"]
                existing.unit = candidate["unit"]
                existing.unit_price = candidate["unit_price"]
                existing.is_active = candidate["is_active"]
                existing.source = candidate["source"]
                existing.extra_data = candidate["extra_data"]
                existing.updated_at = datetime.utcnow()
                updated_items.append(existing)
            else:
                item = CostItem(
                    code=candidate["code"],
                    trade=candidate["trade"],
                    region=candidate["region"],
                    category=candidate["category"],
                    description=candidate["description"],
                    unit=candidate["unit"],
                    unit_price=candidate["unit_price"],
                    currency=candidate["currency"],
                    is_active=candidate["is_active"],
                    source=candidate["source"],
                    extra_data=candidate["extra_data"],
                )
                db.add(item)
                updated_items.append(item)

        await db.commit()
        for item in updated_items:
            await db.refresh(item)
        return updated_items


def _cost_item_to_payload(item: CostItem) -> dict[str, Any]:
    return {
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
        "supplier": item.extra_data.get("supplier"),
        "brand": item.extra_data.get("brand"),
        "sku": item.extra_data.get("sku"),
        "product_url": item.extra_data.get("product_url"),
        "retail_price_incl_vat": str(item.extra_data.get("retail_price_incl_vat"))
        if item.extra_data.get("retail_price_incl_vat") is not None
        else None,
        "metre_length": item.extra_data.get("metre_length"),
        "scraped_at": item.extra_data.get("scraped_at"),
    }


async def _index_in_qdrant(items: list[CostItem]) -> None:
    qdrant = get_qdrant_client()
    await ensure_collection(
        qdrant,
        settings.qdrant_collection_name,
        vector_size=get_embedding_dimension(),
    )

    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        vectors = await embed_texts([item.description for item in batch])
        points = [
            PointStruct(
                id=str(item.id),
                vector=vector,
                payload=_cost_item_to_payload(item),
            )
            for item, vector in zip(batch, vectors, strict=False)
        ]
        await qdrant.upsert(
            collection_name=settings.qdrant_collection_name,
            points=points,
        )


async def run() -> dict[str, int]:
    """Upsert the curated seed and index it in Qdrant."""
    records = _load_seed()
    candidates = _build_candidates(records)
    items = await _upsert_cost_items(candidates)
    await _index_in_qdrant(items)
    return {"loaded": len(items)}


async def main() -> None:
    stats = await run()
    print(f"Curated seed loaded: {stats['loaded']} items")


if __name__ == "__main__":
    asyncio.run(main())
