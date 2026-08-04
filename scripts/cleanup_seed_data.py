#!/usr/bin/env python3
"""Remove legacy seed catalogue rows from Postgres and Qdrant.

This runs as part of the API pre-deploy step so that any environment that was
previously bootstrapped with the ``seed_minimum_catalog`` or ``curated_seed``
fallback data has that data purged. It is idempotent and safe to run on every
deploy: once the target rows are gone the script becomes a no-op.

Targets:

- Postgres ``cost_items`` rows where ``code`` starts with ``DOM-SEED-`` (from
  the removed ``seed_minimum_catalog`` bootstrap).
- Postgres ``cost_items`` rows where ``source = 'curated_seed'`` (from the
  historical data-pipeline curated seed loader).
- Qdrant points in the catalogue collection whose payload has
  ``supplier = 'seed'`` or ``source = 'curated_seed'``.

Qdrant failures never fail the deploy; the catalogue is authoritative in
Postgres and the data-pipeline reindexes vectors on its own schedule.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.qdrant import get_qdrant_client  # noqa: E402

QDRANT_BATCH_SIZE = 500


async def _delete_postgres_seed_rows() -> tuple[int, int]:
    """Delete legacy seed cost_items from Postgres.

    Returns a tuple ``(dom_seed_deleted, curated_seed_deleted)``.
    """
    async with AsyncSessionLocal() as db:
        dom_seed = await db.execute(
            text("DELETE FROM cost_items WHERE code LIKE 'DOM-SEED-%' RETURNING id")
        )
        dom_seed_ids = [row[0] for row in dom_seed.fetchall()]

        curated = await db.execute(
            text("DELETE FROM cost_items WHERE source = 'curated_seed' RETURNING id")
        )
        curated_ids = [row[0] for row in curated.fetchall()]

        await db.commit()
    return len(dom_seed_ids), len(curated_ids)


async def _delete_qdrant_seed_points() -> int:
    """Best-effort delete of Qdrant seed/curated_seed payload points.

    Never raises: any error is logged and the deploy continues.
    """
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
    except Exception as exc:  # pragma: no cover - defensive: import guard
        print(f"[cleanup_seed_data] qdrant_client not importable, skipping: {exc}")
        return 0

    qdrant = get_qdrant_client()
    collection = settings.qdrant_collection_name

    try:
        exists = await qdrant.collection_exists(collection)
    except Exception as exc:
        print(
            f"[cleanup_seed_data] Qdrant unavailable, skipping vector cleanup "
            f"({type(exc).__name__}: {exc})."
        )
        return 0

    if not exists:
        return 0

    filter_ = Filter(
        should=[
            FieldCondition(key="supplier", match=MatchValue(value="seed")),
            FieldCondition(key="source", match=MatchAny(any=["curated_seed"])),
        ],
    )

    total = 0
    offset: str | int | None = None
    try:
        while True:
            points, next_offset = await qdrant.scroll(
                collection_name=collection,
                scroll_filter=filter_,
                limit=QDRANT_BATCH_SIZE,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            if not points:
                break
            ids = [str(p.id) for p in points]
            await qdrant.delete(collection_name=collection, points_selector=ids)
            total += len(ids)
            if next_offset is None:
                break
            offset = next_offset
    except Exception as exc:
        print(
            f"[cleanup_seed_data] Qdrant delete failed after {total} points "
            f"({type(exc).__name__}: {exc}); Postgres cleanup is authoritative."
        )
        return total

    return total


async def main() -> None:
    dom_seed_deleted, curated_deleted = await _delete_postgres_seed_rows()
    qdrant_deleted = await _delete_qdrant_seed_points()
    print(
        f"[cleanup_seed_data] Deleted {dom_seed_deleted} DOM-SEED-* rows, "
        f"{curated_deleted} curated_seed rows, "
        f"{qdrant_deleted} Qdrant points."
    )


if __name__ == "__main__":
    asyncio.run(main())
