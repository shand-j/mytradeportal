"""Seed the cost_items catalogue with a curated UK electrical starter set.

The full catalogue is produced by the Screwfix/Toolstation scrape in
``services/data-pipeline`` (``python -m data_pipeline.loader``). This script
exists so a local/dev stack has a useful, realistic catalogue without running
the paid Apify scrape: ~40 common UK domestic electrical items with plausible
ex-VAT trade prices, marked ``source='curated_seed'`` so they can be told
apart from scraped (``domestic_pipeline``) rows and bulk-removed later.

The script is idempotent: rows are upserted by their unique ``code``.

It only writes to Postgres. Qdrant is intentionally not indexed here (no
embedding provider is required); the API's lexical fallback retrieval searches
this table directly when no embedding key is configured.

Usage:
    # Against the docker-compose stack's Postgres (the DB the API uses):
    docker compose exec -T api python /app/services/api/scripts/seed_cost_items.py

    # From the repo .venv, pointing at the container DB explicitly:
    DATABASE_URL=postgresql+asyncpg://mtp:mtp@localhost:5432/mtp \
        python services/api/scripts/seed_cost_items.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Allow running both as ``python -m scripts.seed_cost_items`` from services/api
# and as a plain script path from the repo root / api container.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models import CostItem

TRADE = "electrical"
REGION = "UK"
SOURCE = "curated_seed"


def _item(
    code: str,
    category: str,
    description: str,
    unit: str,
    price: str,
    *,
    supplier: str,
    brand: str | None = None,
) -> dict[str, Any]:
    """Build a cost-item row dict with standard curated-seed metadata."""
    unit_price = Decimal(price)
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
            "supplier": supplier,
            "brand": brand,
            "retail_price_incl_vat": float(
                (unit_price * Decimal("1.20")).quantize(Decimal("0.01"))
            ),
            "curated": True,
        },
    }


SF = "Screwfix"
TS = "Toolstation"

# Plausible ex-VAT UK trade prices (Screwfix/Toolstation list minus VAT ballpark).
CURATED_ITEMS: list[dict[str, Any]] = [
    # Consumer units & circuit protection
    _item(
        "ELEC-CU-10W-SPD",
        "Consumer Units",
        "10-Way High Integrity Consumer Unit with Type 2 SPD, 100A Main Switch and 8 MCBs",
        "each",
        "105.00",
        supplier=SF,
        brand="FuseBox",
    ),
    _item(
        "ELEC-CU-6W-SPD",
        "Consumer Units",
        "6-Way Consumer Unit with Type 2 SPD and 100A Main Switch (garage/extension board)",
        "each",
        "78.50",
        supplier=SF,
        brand="FuseBox",
    ),
    _item(
        "ELEC-CU-14W-RCD",
        "Consumer Units",
        "14-Way Dual RCD Consumer Unit with 100A Main Switch (no SPD)",
        "each",
        "92.00",
        supplier=TS,
        brand="Lewden",
    ),
    _item(
        "ELEC-RCBO-6A-B",
        "Circuit Protection",
        "6A Type B RCBO 6kA 30mA Type A Single Module",
        "each",
        "23.00",
        supplier=SF,
        brand="FuseBox",
    ),
    _item(
        "ELEC-RCBO-16A-B",
        "Circuit Protection",
        "16A Type B RCBO 6kA 30mA Type A Single Module",
        "each",
        "23.00",
        supplier=SF,
        brand="FuseBox",
    ),
    _item(
        "ELEC-RCBO-32A-B",
        "Circuit Protection",
        "32A Type B RCBO 6kA 30mA Type A Single Module",
        "each",
        "24.50",
        supplier=SF,
        brand="FuseBox",
    ),
    _item(
        "ELEC-RCBO-40A-B",
        "Circuit Protection",
        "40A Type B RCBO 6kA 30mA Type A Single Module",
        "each",
        "25.00",
        supplier=TS,
        brand="Lewden",
    ),
    _item(
        "ELEC-MCB-6A-B",
        "Circuit Protection",
        "6A Type B MCB 6kA Single Pole",
        "each",
        "4.20",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-MCB-16A-B",
        "Circuit Protection",
        "16A Type B MCB 6kA Single Pole",
        "each",
        "4.20",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-MCB-32A-B",
        "Circuit Protection",
        "32A Type B MCB 6kA Single Pole",
        "each",
        "4.20",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-MS-100A",
        "Circuit Protection",
        "100A Double Pole Main Switch Isolator",
        "each",
        "9.50",
        supplier=TS,
        brand="Lewden",
    ),
    _item(
        "ELEC-SPD-T2",
        "Circuit Protection",
        "Type 2 Surge Protection Device (SPD) Module for Consumer Unit",
        "each",
        "38.00",
        supplier=SF,
        brand="FuseBox",
    ),
    _item(
        "ELEC-RCD-63A-A",
        "Circuit Protection",
        "63A 30mA Double Pole RCD Type A",
        "each",
        "32.00",
        supplier=TS,
        brand="MK",
    ),
    # Cable (per metre)
    _item(
        "ELEC-CABLE-TE-1.5",
        "Cable",
        "1.5mm² Twin & Earth Cable 6242Y Grey (lighting circuits)",
        "m",
        "0.75",
        supplier=SF,
        brand="Prysmian",
    ),
    _item(
        "ELEC-CABLE-TE-2.5",
        "Cable",
        "2.5mm² Twin & Earth Cable 6242Y Grey (socket ring finals)",
        "m",
        "1.10",
        supplier=SF,
        brand="Prysmian",
    ),
    _item(
        "ELEC-CABLE-TE-6.0",
        "Cable",
        "6mm² Twin & Earth Cable 6242Y Grey (cooker/shower circuits)",
        "m",
        "2.40",
        supplier=SF,
        brand="Prysmian",
    ),
    _item(
        "ELEC-CABLE-TE-10.0",
        "Cable",
        "10mm² Twin & Earth Cable 6242Y Grey (electric shower/high-load cooker)",
        "m",
        "3.80",
        supplier=SF,
        brand="Prysmian",
    ),
    _item(
        "ELEC-CABLE-SWA-2C-1.5",
        "Cable",
        "1.5mm² 2-Core SWA Steel Wire Armoured Cable 6942X (outdoor/garden supply)",
        "m",
        "1.60",
        supplier=TS,
    ),
    _item(
        "ELEC-CABLE-SWA-3C-2.5",
        "Cable",
        "2.5mm² 3-Core SWA Steel Wire Armoured Cable 6943X (shed/garage supply)",
        "m",
        "2.60",
        supplier=TS,
    ),
    _item(
        "ELEC-CABLE-SWA-3C-6.0",
        "Cable",
        "6mm² 3-Core SWA Steel Wire Armoured Cable 6943X (outbuilding sub-main)",
        "m",
        "4.20",
        supplier=TS,
    ),
    _item(
        "ELEC-CABLE-FLEX-3C-1.0",
        "Cable",
        "1.0mm² 3-Core Flexible Cable 3183Y White (light fittings)",
        "m",
        "0.65",
        supplier=SF,
    ),
    _item(
        "ELEC-CABLE-EARTH-16",
        "Cable",
        "16mm² Single Core Earth Cable 6491X Green/Yellow (main earthing conductor)",
        "m",
        "2.10",
        supplier=SF,
        brand="Prysmian",
    ),
    _item(
        "ELEC-CABLE-BOND-10",
        "Cable",
        "10mm² Green/Yellow Bonding Conductor 6491X (gas/water main bonding)",
        "m",
        "1.60",
        supplier=SF,
        brand="Prysmian",
    ),
    # Sockets, switches & faceplates
    _item(
        "ELEC-SOCK-2G",
        "Switches & Sockets",
        "13A 2-Gang Double Switched Socket White Moulded",
        "each",
        "1.90",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-SOCK-1G",
        "Switches & Sockets",
        "13A 1-Gang Single Switched Socket White Moulded",
        "each",
        "1.50",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-SOCK-2G-USB",
        "Switches & Sockets",
        "13A 2-Gang Switched Socket with USB A+C Outlets White",
        "each",
        "12.50",
        supplier=SF,
        brand="LAP",
    ),
    _item(
        "ELEC-FACE-MET-2G",
        "Switches & Sockets",
        "13A 2-Gang Switched Socket Brushed Stainless Steel Flat Plate",
        "each",
        "7.50",
        supplier=TS,
        brand="LAP",
    ),
    _item(
        "ELEC-SW-1G-2W",
        "Switches & Sockets",
        "10AX 1-Gang 2-Way Light Switch White Moulded",
        "each",
        "1.40",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-SW-2G-2W",
        "Switches & Sockets",
        "10AX 2-Gang 2-Way Light Switch White Moulded",
        "each",
        "1.80",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-SW-DIM-2G",
        "Switches & Sockets",
        "2-Gang 2-Way LED Dimmer Switch White (trailing edge)",
        "each",
        "14.00",
        supplier=SF,
        brand="Varilight",
    ),
    _item(
        "ELEC-SPUR-13A",
        "Switches & Sockets",
        "13A Switched Fused Connection Unit (FCU / fused spur) White",
        "each",
        "3.20",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-COOK-45A",
        "Switches & Sockets",
        "45A Double Pole Cooker Switch with 13A Socket White",
        "each",
        "9.00",
        supplier=TS,
        brand="British General",
    ),
    # Lighting
    _item(
        "ELEC-DL-FR-GU10",
        "Lighting",
        "Fire-Rated GU10 Downlight Fixed White (lamp not included)",
        "each",
        "4.50",
        supplier=SF,
        brand="LAP",
    ),
    _item(
        "ELEC-DL-FR-INT-6W",
        "Lighting",
        "Integrated LED Fire-Rated Downlight 6W CCT Selectable IP65 Dimmable",
        "each",
        "9.00",
        supplier=SF,
        brand="LAP",
    ),
    _item(
        "ELEC-PEND-SET",
        "Lighting",
        "Pendant Set with Ceiling Rose and 6in BC Lampholder White",
        "each",
        "2.50",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-EXT-BULK-PIR",
        "Lighting",
        "Outdoor LED Bulkhead Light with PIR Sensor IP65 Black",
        "each",
        "18.00",
        supplier=TS,
        brand="LAP",
    ),
    # EV charging
    _item(
        "ELEC-EV-7KW-TETH",
        "Solar & EV",
        "7kW Tethered EV Charger Unit Type 2 with 6m Cable (Mode 3, app-controlled)",
        "each",
        "475.00",
        supplier=SF,
        brand="Zappi",
    ),
    _item(
        "ELEC-EV-7KW-UNT",
        "Solar & EV",
        "7kW Untethered EV Charger Unit Type 2 Socket (Mode 3, app-controlled)",
        "each",
        "425.00",
        supplier=TS,
        brand="Rolec",
    ),
    # Earthing & bonding
    _item(
        "ELEC-EARTH-ROD-4FT",
        "Wiring Accessories",
        "4ft (1.2m) Copper-Bonded Earth Rod with Clamp",
        "each",
        "12.00",
        supplier=TS,
    ),
    _item(
        "ELEC-EARTH-CLAMP",
        "Wiring Accessories",
        "Earth Clamp 12-32mm for Bonding Conductor (BS 951)",
        "each",
        "1.80",
        supplier=SF,
    ),
    # Containment & enclosures
    _item(
        "ELEC-TRUNK-25X16",
        "Conduit & Trunking",
        "25x16mm Mini Trunking White Self-Adhesive 2m Length",
        "each",
        "2.00",
        supplier=SF,
        brand="D-Line",
    ),
    _item(
        "ELEC-TRUNK-50X25",
        "Conduit & Trunking",
        "50x25mm Maxi Trunking White 3m Length",
        "each",
        "6.50",
        supplier=TS,
    ),
    _item(
        "ELEC-COND-20MM",
        "Conduit & Trunking",
        "20mm Round PVC Conduit White 3m Length",
        "each",
        "2.20",
        supplier=SF,
    ),
    _item(
        "ELEC-BACKBOX-1G-35",
        "Conduit & Trunking",
        "1-Gang Metal Back Box 35mm Deep Galvanised",
        "each",
        "0.95",
        supplier=SF,
    ),
    _item(
        "ELEC-BACKBOX-2G-25",
        "Conduit & Trunking",
        "2-Gang Metal Back Box 25mm Deep Galvanised",
        "each",
        "1.10",
        supplier=SF,
    ),
    # Fire & security
    _item(
        "ELEC-SMOKE-INT",
        "Security & Fire",
        "Mains-Powered Interlinked Optical Smoke Alarm with 9V Battery Backup",
        "each",
        "14.00",
        supplier=SF,
        brand="FireAngel",
    ),
    _item(
        "ELEC-HEAT-INT",
        "Security & Fire",
        "Mains-Powered Interlinked Heat Alarm with 9V Battery Backup (kitchen)",
        "each",
        "15.00",
        supplier=SF,
        brand="FireAngel",
    ),
    _item(
        "ELEC-PIR-EXT",
        "Security & Fire",
        "External PIR Motion Sensor IP44 Adjustable 180° Black",
        "each",
        "8.00",
        supplier=TS,
        brand="LAP",
    ),
    # Sundries
    _item(
        "ELEC-GLAND-SWA-20",
        "Wiring Accessories",
        "20mm SWA Cable Gland Kit BW20S Pack of 2",
        "each",
        "3.50",
        supplier=SF,
    ),
    _item(
        "ELEC-JBOX-20A",
        "Wiring Accessories",
        "20A 5-Terminal Junction Box White",
        "each",
        "1.20",
        supplier=SF,
        brand="British General",
    ),
    _item(
        "ELEC-CLIP-TUB",
        "Fixings",
        "Assorted Cable Clips Tub of 500 (T&E sizes)",
        "each",
        "5.00",
        supplier=SF,
    ),
    _item(
        "ELEC-SUND-BOX",
        "General",
        "Assorted Electrical Sundries Box (connectors, glands, sleeving, grommets, tape)",
        "each",
        "8.00",
        supplier=SF,
    ),
]


async def seed_cost_items(database_url: str) -> dict[str, int]:
    """Upsert the curated catalogue by code. Returns created/updated counts."""
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            codes = [item["code"] for item in CURATED_ITEMS]
            result = await db.execute(select(CostItem).where(CostItem.code.in_(codes)))
            existing_by_code = {row.code: row for row in result.scalars().all()}

            created = 0
            updated = 0
            for candidate in CURATED_ITEMS:
                existing = existing_by_code.get(candidate["code"])
                if existing is not None:
                    existing.category = candidate["category"]
                    existing.description = candidate["description"]
                    existing.unit = candidate["unit"]
                    existing.unit_price = candidate["unit_price"]
                    existing.is_active = candidate["is_active"]
                    existing.source = candidate["source"]
                    existing.extra_data = candidate["extra_data"]
                    updated += 1
                else:
                    db.add(CostItem(**candidate))
                    created += 1
            await db.commit()

            total = await db.execute(
                select(CostItem.code).where(
                    CostItem.trade == TRADE,
                    CostItem.region == REGION,
                    CostItem.is_active.is_(True),
                )
            )
            active_total = len(list(total.scalars().all()))
            return {"created": created, "updated": updated, "active_total": active_total}
    finally:
        await engine.dispose()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL") or settings.database_url
    counts = asyncio.run(seed_cost_items(database_url))
    print(
        "Curated seed complete: "
        f"{counts['created']} created, {counts['updated']} updated "
        f"(idempotent upsert by code, source={SOURCE!r})."
    )
    print(f"Active electrical/UK cost_items in catalogue: {counts['active_total']}")


if __name__ == "__main__":
    main()
