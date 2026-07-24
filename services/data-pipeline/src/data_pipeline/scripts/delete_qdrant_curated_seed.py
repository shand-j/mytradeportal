"""Delete Qdrant points whose payload source is 'curated_seed'.

Useful when Postgres has already been cleaned and you only need to sync
Qdrant.

Usage:
    python -m data_pipeline.scripts.delete_qdrant_curated_seed --dry-run
    python -m data_pipeline.scripts.delete_qdrant_curated_seed --execute
"""

from __future__ import annotations

import argparse
import asyncio

from qdrant_client.models import FieldCondition, Filter, MatchValue

from data_pipeline.config import settings
from data_pipeline.qdrant import get_qdrant_client

SOURCE = "curated_seed"
BATCH_SIZE = 500


async def delete_curated_seed_from_qdrant(execute: bool) -> dict[str, int]:
    """Scroll Qdrant for curated_seed points and delete them."""
    qdrant = get_qdrant_client()
    collection = settings.qdrant_collection_name

    exists = await qdrant.collection_exists(collection)
    if not exists:
        print(f"Qdrant collection {collection!r} does not exist")
        return {"scanned": 0, "deleted": 0}

    filter_ = Filter(must=[FieldCondition(key="source", match=MatchValue(value=SOURCE))])

    all_ids: list[str] = []
    offset: str | None = None
    while True:
        result = await qdrant.scroll(
            collection_name=collection,
            scroll_filter=filter_,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        points, next_offset = result
        all_ids.extend([str(point.id) for point in points])
        if next_offset is None:
            break
        offset = next_offset

    print(f"Found {len(all_ids)} Qdrant points with source={SOURCE!r}")

    if not all_ids:
        return {"scanned": 0, "deleted": 0}

    if execute:
        for i in range(0, len(all_ids), BATCH_SIZE):
            await qdrant.delete(
                collection_name=collection,
                points_selector=all_ids[i : i + BATCH_SIZE],
            )
        print(f"Deleted {len(all_ids)} points from Qdrant")
    else:
        print("Dry run: no points deleted. Use --execute to delete.")

    return {"scanned": len(all_ids), "deleted": len(all_ids) if execute else 0}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete Qdrant points whose payload source is 'curated_seed'"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete points; without this flag the script runs in dry-run mode",
    )
    args = parser.parse_args()

    result = asyncio.run(delete_curated_seed_from_qdrant(execute=args.execute))
    print(f"Scanned: {result['scanned']}, Deleted: {result['deleted']}")


if __name__ == "__main__":
    main()
