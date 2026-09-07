"""Load normalized domestic electrical products into the shared cost database."""

import asyncio
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from qdrant_client.models import PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_pipeline.config import settings
from data_pipeline.database import get_db_session
from data_pipeline.embeddings import embed_texts, get_embedding_dimension
from data_pipeline.models import CostItem
from data_pipeline.normalizer.attributes import (
    extract_product_attributes,
    format_attributes_tail,
)
from data_pipeline.normalizer.unified_product import (
    ProductCategory,
    ProductNormalizer,
    UnifiedProduct,
)
from data_pipeline.qdrant import ensure_collection, get_qdrant_client
from data_pipeline.scrapers.screwfix_scraper import ScrewfixScraper
from data_pipeline.scrapers.toolstation_scraper import ToolstationScraper

TRADE = "electrical"
REGION = "UK"
SOURCE = "domestic_pipeline"
BATCH_SIZE = 500


def _clean_price(value: float, precision: Decimal = Decimal("0.0001")) -> Decimal:
    """Convert a float price to a rounded Decimal with the requested precision."""
    return Decimal(str(value)).quantize(precision)


def _extract_metre_length(name: str) -> int | None:
    """Attempt to extract a cable length in metres from a product name."""
    patterns = [
        r"(\d+)\s*m\b",
        r"x\s*(\d+)\s*m\b",
        r"(\d+)\s*metre",
    ]
    for pattern in patterns:
        match = re.search(pattern, name.lower())
        if match:
            return int(match.group(1))
    return None


def _category_to_cost_category(category: ProductCategory) -> str:
    """Map the normalizer category to a cost-item category."""
    mapping = {
        ProductCategory.CABLE: "Cable",
        ProductCategory.SWITCHES_SOCKETS: "Switches & Sockets",
        ProductCategory.CONSUMER_UNITS: "Consumer Units",
        ProductCategory.MCB_RCD_RCBO: "Circuit Protection",
        ProductCategory.LIGHTING: "Lighting",
        ProductCategory.CONDUIT_TRUNKING: "Conduit & Trunking",
        ProductCategory.TEST_EQUIPMENT: "Test Equipment",
        ProductCategory.SECURITY_FIRE: "Security & Fire",
        ProductCategory.WIRING_ACCESSORIES: "Wiring Accessories",
        ProductCategory.HEATING_COOLING: "Heating & Cooling",
        ProductCategory.DISTRIBUTION: "Distribution",
        ProductCategory.INDUSTRIAL: "Industrial",
        ProductCategory.SOLAR_EV: "Solar & EV",
        ProductCategory.TOOLS: "Tools",
        ProductCategory.FIXINGS: "Fixings",
        ProductCategory.GENERAL: "General",
    }
    return mapping.get(category, "General")


def _build_description(product: UnifiedProduct) -> str:
    """Build a searchable cost-item description from a product.

    Structured for retrieval quality:
    - category token first so lexical/BM25-style match keys off it
    - brand once (Screwfix listings sometimes lead the name with the brand,
      so avoid duplicating it as a separate prefix)
    - product name
    - a compact free-text description if it adds anything

    Deliberately omits ``Supplier: screwfix`` — that hint hurts vector search
    (every row shared the same token) and is redundant with the ``source``
    field on the row.
    """
    category = _category_to_cost_category(product.category)
    name = (product.name or "").strip()
    brand = (product.brand or "").strip()

    if brand and name and not name.lower().startswith(brand.lower()):
        name = f"{brand} {name}"

    parts = [f"[{category}]", name]
    if product.description and product.description.strip() and product.description != product.name:
        parts.append(product.description.strip())
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()


def unified_product_to_cost_item(product: UnifiedProduct) -> dict[str, Any] | None:
    """Convert a normalized product to a cost-item candidate.

    Returns None if the product cannot be converted (e.g. no price).
    """
    if product.current_price <= 0 and product.trade_price <= 0:
        return None

    category = _category_to_cost_category(product.category)
    price_incl_vat = (
        Decimal(str(product.current_price))
        if product.current_price > 0
        else Decimal(str(product.trade_price))
    )
    price_excl_vat = (
        (price_incl_vat / Decimal("1.20")).quantize(Decimal("0.0001"))
        if product.vat_included
        else price_incl_vat
    )

    unit = product.unit_of_measure or "each"
    unit_price = _clean_price(float(price_excl_vat))

    metre_length = _extract_metre_length(product.name)
    if metre_length and metre_length > 0 and product.category == ProductCategory.CABLE:
        unit = "m"
        unit_price = (price_excl_vat / Decimal(metre_length)).quantize(Decimal("0.0001"))

    supplier_value = product.supplier.value.lower()
    identifier = product.sku or product.supplier_product_id
    if not identifier:
        return None

    code = f"DOM-{supplier_value}-{identifier}".replace(" ", "_")[:63]
    attributes = extract_product_attributes(product)
    description = _build_description(product) + format_attributes_tail(attributes)

    return {
        "code": code,
        "trade": TRADE,
        "region": REGION,
        "category": category,
        "description": description,
        "unit": unit,
        "unit_price": unit_price,
        "currency": "GBP",
        "is_active": True,
        "source": SOURCE,
        "extra_data": {
            "supplier": product.supplier.value,
            "brand": product.brand,
            "supplier_product_id": product.supplier_product_id,
            "sku": product.sku,
            "mpn": product.mpn,
            "gtin": product.gtin,
            "product_url": product.product_url,
            "image_url": product.image_url,
            "vat_included": product.vat_included,
            "retail_price_incl_vat": float(price_incl_vat),
            "metre_length": metre_length,
            "scraped_at": product.scraped_at,
            "stock_status": product.stock_status,
            "attributes": attributes,
        },
    }


def deduplicate_products(products: list[UnifiedProduct]) -> list[UnifiedProduct]:
    """Deduplicate products by supplier + SKU, keeping the first occurrence."""
    seen: set[tuple[str, str]] = set()
    unique: list[UnifiedProduct] = []
    for product in products:
        key = (product.supplier.value, product.sku or product.supplier_product_id)
        if key in seen or not key[1]:
            continue
        seen.add(key)
        unique.append(product)
    return unique


async def _upsert_cost_items(
    db: AsyncSession,
    candidates: list[dict[str, Any]],
) -> list[CostItem]:
    """Upsert cost-item candidates into Postgres by code.

    Returns the list of CostItem rows that were created or updated.
    """
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


async def _deactivate_old_pipeline_items(
    db: AsyncSession,
    current_codes: set[str],
) -> list[CostItem]:
    """Deactivate pipeline items whose codes were not part of the latest run."""
    result = await db.execute(
        select(CostItem).where(CostItem.source == SOURCE, CostItem.is_active.is_(True))
    )
    stale = [item for item in result.scalars().all() if item.code not in current_codes]
    for item in stale:
        item.is_active = False
        item.updated_at = datetime.utcnow()
    if stale:
        await db.commit()
    return stale


def _cost_item_to_payload(item: CostItem) -> dict[str, Any]:
    """Build a Qdrant payload from a CostItem."""
    attributes = item.extra_data.get("attributes") or {}
    payload: dict[str, Any] = {
        "code": item.code,
        "trade": item.trade,
        "region": item.region,
        "category": item.category,
        "description": item.description,
        "search_text": item.description,
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
    # Flatten attributes to top-level payload keys so Qdrant field filters
    # (Filter/FieldCondition/MatchValue) can target them without dotted paths.
    for key, value in attributes.items():
        payload[f"attr_{key}"] = value
    return payload


async def _index_in_qdrant(items: list[CostItem]) -> None:
    """Embed and upsert cost items into the shared Qdrant collection."""
    if not items:
        return

    qdrant = get_qdrant_client()
    await ensure_collection(
        qdrant,
        settings.qdrant_collection_name,
        vector_size=get_embedding_dimension(),
    )

    vectors = await embed_texts([item.description for item in items])
    points = [
        PointStruct(
            id=str(item.id),
            vector=vector,
            payload=_cost_item_to_payload(item),
        )
        for item, vector in zip(items, vectors, strict=True)
    ]

    for i in range(0, len(points), BATCH_SIZE):
        await qdrant.upsert(
            collection_name=settings.qdrant_collection_name,
            points=points[i : i + BATCH_SIZE],
        )


async def _sync_stale_qdrant_points(stale_items: list[CostItem]) -> None:
    """Update Qdrant payloads for items that have been deactivated."""
    if not stale_items:
        return
    qdrant = get_qdrant_client()
    vectors = await embed_texts([item.description for item in stale_items])
    points = [
        PointStruct(
            id=str(item.id),
            vector=vector,
            payload=_cost_item_to_payload(item),
        )
        for item, vector in zip(stale_items, vectors, strict=True)
    ]
    for i in range(0, len(points), BATCH_SIZE):
        await qdrant.upsert(
            collection_name=settings.qdrant_collection_name,
            points=points[i : i + BATCH_SIZE],
        )


async def _run_with_session(db: AsyncSession, skip_qdrant: bool) -> dict[str, Any]:
    """Execute the pipeline using the supplied database session."""
    scraper_screwfix = ScrewfixScraper(api_token=settings.apify_api_token)

    raw_products: list[Any] = []

    products = scraper_screwfix.scrape_category(
        settings.screwfix_start_url,
        max_items=settings.screwfix_max_items,
        scrape_details=settings.screwfix_scrape_details,
        max_total_charge_usd=settings.screwfix_max_total_charge_usd,
        timeout_seconds=settings.screwfix_timeout_seconds,
    )
    raw_products.extend(products)

    if settings.toolstation_enabled:
        scraper_toolstation = ToolstationScraper(api_token=settings.apify_api_token)
        for category_url in ToolstationScraper.ELECTRICAL_CATEGORIES.values():
            toolstation_products = scraper_toolstation.browse_category(
                category_url,
                max_items=100,
            )
            raw_products.extend(toolstation_products)

    normalizer = ProductNormalizer()
    unified: list[UnifiedProduct] = []
    for raw in raw_products:
        if hasattr(raw, "source") and raw.source == "screwfix":
            unified.append(normalizer.from_screwfix(raw))
        elif hasattr(raw, "source") and raw.source == "toolstation":
            unified.append(normalizer.from_toolstation(raw))

    unified = deduplicate_products(unified)

    candidates = []
    for product in unified:
        candidate = unified_product_to_cost_item(product)
        if candidate:
            candidates.append(candidate)

    items = await _upsert_cost_items(db, candidates)

    # Only deactivate old items when the current run produced products. This
    # prevents a failed scrape (or a disabled demo fallback) from wiping out
    # previously imported real data.
    stale: list[CostItem] = []
    if raw_products:
        stale = await _deactivate_old_pipeline_items(db, {item.code for item in items})

    if not skip_qdrant:
        await _index_in_qdrant(items)
        await _sync_stale_qdrant_points(stale)

    return {
        "products_scraped": len(raw_products),
        "products_normalized": len(unified),
        "cost_items_upserted": len(items),
        "stale_items_deactivated": len(stale),
    }


async def run_pipeline(
    db: AsyncSession | None = None,
    skip_qdrant: bool = False,
) -> dict[str, Any]:
    """Run the full domestic electrical data pipeline.

    Scrapes Screwfix (and optionally Toolstation), normalizes the products,
    upserts them into Postgres and Qdrant, and deactivates stale pipeline items.
    """
    if db is not None:
        return await _run_with_session(db, skip_qdrant)

    async with get_db_session() as db_session:
        return await _run_with_session(db_session, skip_qdrant)


async def main() -> None:
    """CLI entry point for the pipeline."""
    result = await run_pipeline()
    print("Domestic electrical data pipeline complete.")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
