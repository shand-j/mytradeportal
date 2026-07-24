"""Import all Apify datasets into the cost database, deduplicated.

Scans every dataset in the Apify account, fetches the items, normalises them,
merges duplicates across datasets, and upserts the result into Postgres and
Qdrant. Existing cost items are updated (not duplicated) by their unique code.

Usage:
    python -m data_pipeline.scripts.import_all_apify_datasets --dry-run
    python -m data_pipeline.scripts.import_all_apify_datasets --execute
    python -m data_pipeline.scripts.import_all_apify_datasets --execute --actor-id datasaurus~screwfix-event
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

import requests

from data_pipeline.config import settings
from data_pipeline.database import get_db_session
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

APIFY_BASE = "https://api.apify.com/v2"


def _apify_paginated_get(
    url: str,
    api_token: str,
    limit: int = 1000,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Generic helper for Apify paginated list endpoints."""
    params: dict[str, Any] = {"token": api_token, "limit": limit, "desc": "true"}
    items: list[dict[str, Any]] = []
    offset = 0

    while True:
        params["offset"] = offset
        if verbose:
            print(f"GET {url} offset={offset}")
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        if verbose:
            print(f"  response keys: {list(data.keys())}")
            if isinstance(data.get("data"), dict):
                print(f"  data keys: {list(data['data'].keys())}")
                print(f"  total: {data['data'].get('total')} count: {data['data'].get('count')}")

        payload = data.get("data", data)
        if isinstance(payload, dict):
            page_items = payload.get("items", [])
        elif isinstance(payload, list):
            page_items = payload
        else:
            page_items = []

        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < limit:
            break
        offset += limit

    return items


def _list_datasets(
    api_token: str,
    actor_id: str | None = None,
    limit: int = 1000,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Return all accessible Apify datasets, optionally filtered by actor id.

    Direct dataset listing is tried first; if that returns nothing, we fall back
    to scanning actor runs and collecting their defaultDatasetId values. This
    catches datasets created via actor tasks, which sometimes do not appear in
    the /datasets endpoint for the same token.
    """
    direct = _apify_paginated_get(f"{APIFY_BASE}/datasets", api_token, limit=limit, verbose=verbose)
    if verbose:
        print(f"Direct /datasets returned {len(direct)} items")

    if actor_id:
        direct = [d for d in direct if d.get("actId") == actor_id or d.get("actorId") == actor_id]

    if direct:
        return direct

    print("Direct /datasets returned no items; scanning actor runs for defaultDatasetId...")
    runs = _apify_paginated_get(f"{APIFY_BASE}/actor-runs", api_token, limit=limit, verbose=verbose)
    if verbose:
        print(f"/actor-runs returned {len(runs)} items")

    dataset_ids: set[str] = set()
    fallback: list[dict[str, Any]] = []
    for run in runs:
        ds_id = run.get("defaultDatasetId")
        if not ds_id or ds_id in dataset_ids:
            continue
        if actor_id and run.get("actId") != actor_id and run.get("actorId") != actor_id:
            continue
        dataset_ids.add(ds_id)
        fallback.append(
            {
                "id": ds_id,
                "name": run.get("actorTaskName") or run.get("name") or "<from run>",
                "actId": run.get("actId") or run.get("actorId"),
                "createdAt": run.get("startedAt"),
            }
        )

    return fallback


def _fetch_all_dataset_items(
    scraper: ScrewfixScraper,
    dataset_id: str,
) -> list[Any]:
    """Fetch every item from a single Apify dataset."""
    try:
        return scraper.fetch_dataset(dataset_id)
    except requests.exceptions.RequestException as exc:
        print(f"WARNING: failed to fetch dataset {dataset_id}: {exc}")
        return []


def _deduplicate_across_datasets(
    unified: list[UnifiedProduct],
) -> list[UnifiedProduct]:
    """Deduplicate products across all datasets, keeping the most recent by scraped_at."""
    by_key: dict[tuple[str, str], UnifiedProduct] = {}
    for product in unified:
        key = (product.supplier.value, product.sku or product.supplier_product_id)
        if not key[1]:
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = product
        else:
            # Keep the most recently scraped record when duplicate keys exist.
            existing_date = existing.scraped_at or datetime.utcnow().isoformat()
            new_date = product.scraped_at or datetime.utcnow().isoformat()
            if new_date > existing_date:
                by_key[key] = product
    return list(by_key.values())


async def import_all_datasets(
    execute: bool,
    actor_id: str | None = None,
    verbose: bool = False,
) -> dict[str, int]:
    """Discover all Apify datasets, deduplicate, and upsert into Postgres + Qdrant."""
    if not settings.apify_api_token:
        raise RuntimeError("APIFY_API_TOKEN is not set")

    scraper = ScrewfixScraper(api_token=settings.apify_api_token)

    datasets = _list_datasets(settings.apify_api_token, actor_id=actor_id, verbose=verbose)
    if actor_id:
        print(f"Discovered {len(datasets)} Apify datasets for actor {actor_id!r}")
    else:
        print(f"Discovered {len(datasets)} Apify datasets")

    for dataset in datasets:
        created = dataset.get("createdAt", "?")
        name = dataset.get("name", "<unnamed>")
        act_id = dataset.get("actId") or dataset.get("actorId") or "<unknown>"
        print(f"  - {dataset['id']} | actor={act_id} | created={created} | {name}")

    if not datasets:
        return {"datasets": 0, "raw_products": 0, "normalized": 0, "cost_items": 0}

    all_raw: list[Any] = []
    for dataset in datasets:
        dataset_id = dataset["id"]
        name = dataset.get("name", "<unnamed>")
        print(f"Fetching dataset {dataset_id} ({name})...")
        items = _fetch_all_dataset_items(scraper, dataset_id)
        print(f"  -> {len(items)} items")
        all_raw.extend(items)

    print(f"Total raw products across all datasets: {len(all_raw)}")

    normalizer = ProductNormalizer()
    unified: list[UnifiedProduct] = []
    for raw in all_raw:
        if hasattr(raw, "source") and raw.source == "screwfix":
            unified.append(normalizer.from_screwfix(raw))

    unified = deduplicate_products(unified)
    unified = _deduplicate_across_datasets(unified)

    print(f"Unique products after deduplication: {len(unified)}")

    candidates: list[dict[str, Any]] = []
    for product in unified:
        candidate = unified_product_to_cost_item(product)
        if candidate:
            candidates.append(candidate)

    print(f"Cost-item candidates: {len(candidates)}")

    if not execute:
        print("Dry run: no database writes. Use --execute to import.")
        return {
            "datasets": len(datasets),
            "raw_products": len(all_raw),
            "normalized": len(unified),
            "cost_items": len(candidates),
        }

    async with get_db_session() as db:
        items: list[CostItem] = await _upsert_cost_items(db, candidates)
        await _index_in_qdrant(items)

    print(f"Upserted {len(items)} cost items into Postgres and Qdrant")
    return {
        "datasets": len(datasets),
        "raw_products": len(all_raw),
        "normalized": len(unified),
        "cost_items": len(items),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import all Apify datasets into the cost database, deduplicated"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--execute",
        action="store_true",
        help="Actually write to Postgres and Qdrant (default: dry-run)",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing (default behaviour)",
    )
    parser.add_argument(
        "--actor-id",
        type=str,
        default=None,
        help="Only import datasets created by this actor (by default all datasets are imported)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print raw Apify API response details for debugging",
    )
    args = parser.parse_args()

    result = asyncio.run(
        import_all_datasets(execute=args.execute, actor_id=args.actor_id, verbose=args.verbose)
    )
    print("Import summary:")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
