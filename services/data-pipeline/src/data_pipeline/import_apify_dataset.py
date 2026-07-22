"""Import products from existing Apify datasets into the cost database.

Useful when the Apify account has hit its usage limit but datasets from earlier
runs are still available. The dataset items are normalised and upserted into
Postgres and Qdrant exactly as if they had come from a fresh scrape.

Usage:
    python -m data_pipeline.import_apify_dataset <dataset_id> [<dataset_id> ...]

Example:
    python -m data_pipeline.import_apify_dataset 4MHcC1siHZ1EDWTfV
"""

from __future__ import annotations

import argparse
import asyncio
from typing import TYPE_CHECKING, Any

from data_pipeline.config import settings
from data_pipeline.loader import (
    _index_in_qdrant,
    _upsert_cost_items,
    deduplicate_products,
    unified_product_to_cost_item,
)
from data_pipeline.normalizer.unified_product import ProductNormalizer, UnifiedProduct
from data_pipeline.scrapers.screwfix_scraper import ScrewfixScraper

if TYPE_CHECKING:
    from data_pipeline.models import CostItem


def _fetch_products(dataset_ids: list[str]) -> list[Any]:
    """Fetch raw products from one or more Apify datasets."""
    scraper = ScrewfixScraper(api_token=settings.apify_api_token)
    raw_products: list[Any] = []
    for dataset_id in dataset_ids:
        products = scraper.fetch_dataset(dataset_id)
        raw_products.extend(products)
    return raw_products


async def import_datasets(dataset_ids: list[str]) -> dict[str, int]:
    """Import dataset items into Postgres and Qdrant."""
    raw_products = _fetch_products(dataset_ids)

    normalizer = ProductNormalizer()
    unified: list[UnifiedProduct] = []
    for raw in raw_products:
        if hasattr(raw, "source") and raw.source == "screwfix":
            unified.append(normalizer.from_screwfix(raw))

    unified = deduplicate_products(unified)

    candidates: list[dict[str, Any]] = []
    for product in unified:
        candidate = unified_product_to_cost_item(product)
        if candidate:
            candidates.append(candidate)

    from data_pipeline.database import get_db_session

    async with get_db_session() as db:
        items: list[CostItem] = await _upsert_cost_items(db, candidates)
        await _index_in_qdrant(items)

    return {
        "datasets": len(dataset_ids),
        "raw_products": len(raw_products),
        "normalized": len(unified),
        "cost_items_upserted": len(items),
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Import Screwfix products from existing Apify datasets"
    )
    parser.add_argument(
        "dataset_ids",
        nargs="+",
        help="One or more Apify dataset IDs to import",
    )
    args = parser.parse_args()

    result = asyncio.run(import_datasets(args.dataset_ids))

    print("Apify dataset import complete.")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
