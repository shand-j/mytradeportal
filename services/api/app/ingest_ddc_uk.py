"""Ingest the DDC CWICR UK cost database into Postgres and Qdrant."""

import asyncio
import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pyarrow.parquet as pq
from qdrant_client.models import PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import CostItem
from app.qdrant import ensure_collection, get_qdrant_client
from app.rag.retrieval import embed_texts, get_embedding_dimension

PARQUET_URL = (
    "https://raw.githubusercontent.com/datadrivenconstruction/"
    "OpenConstructionEstimate-DDC-CWICR/main/UK___DDC_CWICR/"
    "UK_GBP_workitems_costs_resources_DDC_CWICR.parquet"
)
ELECTRICAL_KEYWORDS = ("electr", "light industry")
BATCH_SIZE = 500


def _is_electrical_collection(name: str | None) -> bool:
    if not name:
        return False
    low = str(name).lower()
    return any(kw in low for kw in ELECTRICAL_KEYWORDS)


def _make_description(row: dict[str, Any]) -> str:
    parts = [row.get("rate_final_name") or row.get("rate_original_name")]
    composition = row.get("work_composition_text")
    if composition:
        parts.append(composition)
    return " ".join(str(p) for p in parts if p).strip()


def _make_code(rate_code: str, final_name: str) -> str:
    # Rate codes are not unique across all detailed variants; append a short
    # hash of the human-readable name to disambiguate.
    name_hash = hashlib.sha256(final_name.encode()).hexdigest()[:8]
    return f"{rate_code}-{name_hash}"


async def _download_parquet(client: httpx.AsyncClient) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        path = Path(f.name)
    async with client.stream("GET", PARQUET_URL, follow_redirects=True) as resp:
        resp.raise_for_status()
        with path.open("wb") as f:
            async for chunk in resp.aiter_bytes():
                f.write(chunk)
    return path


def _load_scope_rows(path: Path) -> list[dict[str, Any]]:
    table = pq.read_table(path)  # type: ignore[no-untyped-call]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for i in range(table.num_rows):
        if not table.column("is_scope")[i].as_py():
            continue
        if table.column("row_type")[i].as_py() != "Scope of work":
            continue
        collection = table.column("collection_name")[i].as_py()
        if not _is_electrical_collection(collection):
            continue

        row = {name: table.column(name)[i].as_py() for name in table.column_names}
        price = row.get("total_cost_per_position")
        if price is None:
            continue

        final_name = cast("str", row.get("rate_final_name") or "")
        unit = cast("str", row.get("rate_unit") or "")
        dedup_key = (cast("str", row.get("rate_code")), final_name, unit, str(price))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        rows.append(row)

    return rows


async def ingest_ddc_uk(
    db: AsyncSession,
    parquet_path: Path | None = None,
    skip_qdrant: bool = False,
) -> int:
    """Download (if needed) and ingest DDC CWICR UK electrical cost items."""
    if parquet_path is None:
        async with httpx.AsyncClient(timeout=120.0) as client:
            parquet_path = await _download_parquet(client)

    rows = _load_scope_rows(parquet_path)
    if not rows:
        return 0

    codes = [_make_code(r["rate_code"], r.get("rate_final_name") or "") for r in rows]
    result = await db.execute(select(CostItem).where(CostItem.code.in_(codes)))
    existing_codes = {item.code for item in result.scalars().all()}

    new_items: list[CostItem] = []
    for row in rows:
        final_name = row.get("rate_final_name") or ""
        code = _make_code(row["rate_code"], final_name)
        if code in existing_codes:
            continue

        description = _make_description(row)
        if not description:
            continue

        item = CostItem(
            code=code,
            trade="electrical",
            region="UK",
            category=row.get("collection_name") or "Electrical",
            description=description,
            unit=row.get("rate_unit") or "",
            unit_price=Decimal(str(row["total_cost_per_position"])),
            currency="GBP",
            is_active=True,
            source="ddc_cwicr_uk",
            extra_data={
                "department": row.get("department_name"),
                "section": row.get("section_name"),
                "subsection": row.get("subsection_name"),
                "rate_code": row.get("rate_code"),
                "price_region": row.get("price_region"),
            },
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

    for i in range(0, len(points), BATCH_SIZE):
        await qdrant.upsert(
            collection_name=settings.qdrant_collection_name,
            points=points[i : i + BATCH_SIZE],
        )

    return len(new_items)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        count = await ingest_ddc_uk(db)
        print(f"Ingested {count} new DDC CWICR UK electrical cost items.")


if __name__ == "__main__":
    asyncio.run(main())
