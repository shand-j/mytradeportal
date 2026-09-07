#!/usr/bin/env python3
"""Seed the local ``cost_items`` catalogue from a captured Apify dataset dump.

The production Screwfix Apify scrape only runs on the 1st of each month, so the
local stack usually has an empty ``cost_items`` table and quote generation
falls back to guide-priced-only output (no retrieval grounding). This script
loads a JSON snapshot of the latest production Apify dataset — checked in at
``services/data-pipeline/tests/data/screwfix_cost_items.json`` — and runs it
through the same normaliser + upsert path the pipeline uses in production.

Usage (from the repo root, with the repo venv active):

    docker compose up -d postgres qdrant
    source .venv/bin/activate
    python scripts/seed_cost_items.py                # Postgres only
    python scripts/seed_cost_items.py --with-qdrant  # also embed + index

Qdrant indexing calls whichever OpenAI-compatible embeddings endpoint the
pipeline is configured with (``EMBEDDING_API_BASE`` + ``EMBEDDING_API_KEY``,
falling back to ``OPENAI_API_KEY``). Kimi has no embeddings API, so the
embedder is intentionally decoupled from the chat LLM. When no embedding key
is configured, the script Postgres-seeds only and prints a note; retrieval
then falls back to lexical Postgres search so quotes still get grounding.

The script is idempotent: items are upserted by ``code``, so re-running only
refreshes prices/descriptions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SRC = ROOT / "services" / "data-pipeline" / "src"
if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

from data_pipeline.config import settings  # noqa: E402
from data_pipeline.database import get_db_session  # noqa: E402
from data_pipeline.loader import (  # noqa: E402
    _index_in_qdrant,
    _upsert_cost_items,
    deduplicate_products,
    unified_product_to_cost_item,
)
from data_pipeline.normalizer.unified_product import ProductNormalizer  # noqa: E402
from data_pipeline.scrapers.screwfix_scraper import ScrewfixScraper  # noqa: E402

DEFAULT_JSON_PATH = (
    ROOT / "services" / "data-pipeline" / "tests" / "data" / "screwfix_cost_items.json"
)


def _load_raw_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Cost-item JSON not found at {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array at {path}, got {type(data).__name__}")
    return data


def _prepare_raw_item(item: dict[str, Any]) -> dict[str, Any]:
    """Bridge the captured schema to what ``ScrewfixScraper._normalize_item`` expects.

    The Apify dataset dump uses ``link`` for the product URL, whereas the
    scraper reads ``url``. Everything else already aligns.
    """
    if "link" in item and "url" not in item:
        item = {**item, "url": item["link"]}
    return item


async def seed(json_path: Path, with_qdrant: bool) -> dict[str, int]:
    raw_items = _load_raw_items(json_path)

    scraper = ScrewfixScraper(api_token="")  # only using its normaliser
    products = [scraper._normalize_item(_prepare_raw_item(item)) for item in raw_items]

    normalizer = ProductNormalizer()
    unified = [normalizer.from_screwfix(p) for p in products]
    unified = deduplicate_products(unified)

    candidates: list[dict[str, Any]] = []
    for product in unified:
        candidate = unified_product_to_cost_item(product)
        if candidate:
            candidates.append(candidate)

    async with get_db_session() as db:
        items = await _upsert_cost_items(db, candidates)
        if with_qdrant:
            await _index_in_qdrant(items)

    return {
        "raw_items": len(raw_items),
        "normalized": len(unified),
        "cost_items_upserted": len(items),
        "qdrant_indexed": len(items) if with_qdrant else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"Path to the JSON dump (default: {DEFAULT_JSON_PATH.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--with-qdrant",
        action="store_true",
        help="Also embed the seeded items and upsert them into Qdrant.",
    )
    args = parser.parse_args()

    with_qdrant = args.with_qdrant
    if with_qdrant and not settings.resolved_embedding_api_key:
        print(
            "No embedding key configured (EMBEDDING_API_KEY / OPENAI_API_KEY) — "
            "skipping Qdrant indexing. Retrieval will fall back to lexical "
            "Postgres search.",
            file=sys.stderr,
        )
        with_qdrant = False

    result = asyncio.run(seed(args.json, with_qdrant))
    print("Local cost-item seed complete.")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
