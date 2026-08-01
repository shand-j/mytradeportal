#!/usr/bin/env python3
"""Seed a minimal domestic catalogue required by deterministic BoQ generation.

This script is idempotent and safe to run on every deploy. It ensures a baseline
set of `domestic_pipeline` cost items exists so mandatory requirements (consumer
unit, alarms, back boxes, MCB, sockets, cable) can resolve even when external
scraping providers are unavailable.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from qdrant_client.models import PointStruct
from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import CostItem  # noqa: E402
from app.qdrant import ensure_collection, get_qdrant_client  # noqa: E402
from app.rag.retrieval import embed_texts, get_embedding_dimension  # noqa: E402

SEED_ITEMS: list[dict[str, object]] = [
    {
        "code": "DOM-SEED-CU-10WAY",
        "category": "Consumer Units",
        "description": "Metal consumer unit 10-way with SPD surge protection and main switch",
        "unit": "each",
        "unit_price": Decimal("145.0000"),
    },
    {
        "code": "DOM-SEED-MCB-B32",
        "category": "Circuit Protection",
        "description": "Type B MCB miniature circuit breaker 32A 6kA",
        "unit": "each",
        "unit_price": Decimal("8.7500"),
    },
    {
        "code": "DOM-SEED-SOCKET-2G",
        "category": "Switches & Sockets",
        "description": "13A double socket 2-gang switched white",
        "unit": "each",
        "unit_price": Decimal("4.2500"),
    },
    {
        "code": "DOM-SEED-CABLE-25MM",
        "category": "Cable",
        "description": "Twin and earth cable 2.5mm 50m drum",
        "unit": "m",
        "unit_price": Decimal("0.7200"),
    },
    {
        "code": "DOM-SEED-SMOKE-MAINS",
        "category": "Security & Fire",
        "description": "Mains interlinked smoke alarm detector",
        "unit": "each",
        "unit_price": Decimal("18.5000"),
    },
    {
        "code": "DOM-SEED-HEAT-DET",
        "category": "Security & Fire",
        "description": "Mains interlinked heat detector alarm",
        "unit": "each",
        "unit_price": Decimal("21.0000"),
    },
    {
        "code": "DOM-SEED-BBOX-1G",
        "category": "Wiring Accessories",
        "description": "Metal back box 1-gang 35mm pattress",
        "unit": "each",
        "unit_price": Decimal("1.9500"),
    },
    {
        "code": "DOM-SEED-BBOX-2G",
        "category": "Wiring Accessories",
        "description": "Metal back box 2-gang 35mm pattress",
        "unit": "each",
        "unit_price": Decimal("2.8500"),
    },
]


async def _upsert_seed_items() -> list[CostItem]:
    codes = [str(item["code"]) for item in SEED_ITEMS]
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(CostItem).where(CostItem.code.in_(codes)))
        existing_by_code = {row.code: row for row in existing.scalars().all()}

        rows: list[CostItem] = []
        for item in SEED_ITEMS:
            code = str(item["code"])
            row = existing_by_code.get(code)
            if row is None:
                row = CostItem(
                    code=code,
                    trade="electrical",
                    region="UK",
                    category=str(item["category"]),
                    description=str(item["description"]),
                    unit=str(item["unit"]),
                    unit_price=Decimal(str(item["unit_price"])),
                    currency="GBP",
                    is_active=True,
                    source="domestic_pipeline",
                    extra_data={
                        "supplier": "seed",
                        "brand": "Seed Catalogue",
                        "sku": code,
                        "product_url": None,
                        "retail_price_incl_vat": None,
                    },
                )
                db.add(row)
            else:
                row.category = str(item["category"])
                row.description = str(item["description"])
                row.unit = str(item["unit"])
                row.unit_price = Decimal(str(item["unit_price"]))
                row.is_active = True
                row.source = "domestic_pipeline"
                row.extra_data = {
                    **(row.extra_data or {}),
                    "supplier": "seed",
                    "brand": "Seed Catalogue",
                    "sku": code,
                    "product_url": None,
                    "retail_price_incl_vat": None,
                }
            rows.append(row)

        await db.commit()
        for row in rows:
            await db.refresh(row)

    return rows


async def _index_rows(rows: list[CostItem]) -> bool:
    """Best-effort vector indexing of the seed rows into Qdrant.

    The database rows are the source of truth for deterministic BoQ generation
    and are committed before this runs. Vector indexing is an optional
    enrichment for RAG retrieval, so a missing embedding provider or an
    unavailable Qdrant must never fail the deploy — the data-pipeline reindexes
    the full catalogue later regardless. Returns ``True`` when indexing
    succeeded and ``False`` when it was skipped.
    """
    if not rows:
        return False

    if not settings.openai_api_key:
        print(
            "[seed_minimum_catalog] OPENAI_API_KEY not set; skipping Qdrant vector "
            "indexing (database seed still applied)."
        )
        return False

    qdrant = get_qdrant_client()
    await ensure_collection(
        qdrant,
        settings.qdrant_collection_name,
        vector_size=get_embedding_dimension(),
    )

    vectors = await embed_texts([row.description for row in rows])
    points = [
        PointStruct(
            id=str(row.id),
            vector=vector,
            payload={
                "code": row.code,
                "trade": row.trade,
                "region": row.region,
                "category": row.category,
                "description": row.description,
                "unit": row.unit,
                "unit_price": str(row.unit_price),
                "currency": row.currency,
                "is_active": row.is_active,
                "source": row.source,
                "supplier": "seed",
                "brand": "Seed Catalogue",
                "sku": row.code,
                "product_url": None,
                "retail_price_incl_vat": None,
                "metre_length": 50 if row.code == "DOM-SEED-CABLE-25MM" else None,
            },
        )
        for row, vector in zip(rows, vectors, strict=True)
    ]

    await qdrant.upsert(collection_name=settings.qdrant_collection_name, points=points)
    return True


async def main() -> None:
    rows = await _upsert_seed_items()
    try:
        indexed = await _index_rows(rows)
    except Exception as exc:
        indexed = False
        print(
            "[seed_minimum_catalog] WARNING: vector indexing failed and was skipped "
            f"({type(exc).__name__}: {exc}). Database seed is still applied."
        )
    suffix = "and indexed " if indexed else "(vector indexing skipped) "
    print(f"[seed_minimum_catalog] Upserted {suffix}{len(rows)} minimum domestic items")


if __name__ == "__main__":
    asyncio.run(main())
