"""
Unified Product Data Model and Normalizer

This module defines a canonical product schema that all supplier data
is normalized into, regardless of source. This gives your AI quoting
agent a single, consistent interface to query products from any supplier.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar


class Supplier(StrEnum):
    """Supported electrical product suppliers."""

    SCREWFIX = "screwfix"
    TOOLSTATION = "toolstation"
    CEF = "cef"
    TLC_DIRECT = "tlc_direct"
    EDATA = "edata"
    SCHNEIDER_ELECTRIC = "schneider_electric"
    PRICELYNX = "pricelynx"
    NETXL = "netxl"
    ICECAT = "icecat"
    AMAZON = "amazon"
    CHANNEL3 = "channel3"
    UNKNOWN = "unknown"


class ProductCategory(StrEnum):
    """Standardized electrical product categories."""

    CABLE = "cable"
    SWITCHES_SOCKETS = "switches_and_sockets"
    CONSUMER_UNITS = "consumer_units"
    MCB_RCD_RCBO = "mcb_rcd_rcbo"
    LIGHTING = "lighting"
    CONDUIT_TRUNKING = "conduit_and_trunking"
    TEST_EQUIPMENT = "test_equipment"
    HEATING_COOLING = "heating_and_cooling"
    SECURITY_FIRE = "security_and_fire"
    WIRING_ACCESSORIES = "wiring_accessories"
    DISTRIBUTION = "distribution"
    INDUSTRIAL = "industrial"
    SOLAR_EV = "solar_and_ev"
    TOOLS = "tools"
    FIXINGS = "fixings"
    GENERAL = "general"


@dataclass
class UnifiedProduct:
    """
    Canonical product record - single schema for all suppliers.

    This is the data structure your AI quoting agent will consume.
    All supplier-specific scrapers/normalizers convert to this format.
    """

    # --- Core Identification ---
    unified_id: str = ""  # Generated: source + supplier_product_id
    supplier: Supplier = Supplier.UNKNOWN
    supplier_product_id: str = ""  # Original ID from supplier
    sku: str = ""  # Stock keeping unit
    mpn: str = ""  # Manufacturer part number
    gtin: str = ""  # Global Trade Item Number (EAN/UPC)

    # --- Product Info ---
    name: str = ""
    brand: str = ""
    description: str = ""
    category: ProductCategory = ProductCategory.GENERAL
    subcategory: str = ""

    # --- Pricing (GBP) ---
    current_price: float = 0.0  # Current selling price
    was_price: float = 0.0  # Original price before discount
    discount_percent: float = 0.0
    trade_price: float = 0.0  # Trade-only price if available
    price_per_unit: float = 0.0  # Normalized per-unit price
    unit_of_measure: str = "each"  # each, m, pack, drum, etc.
    vat_included: bool = True  # UK prices typically include VAT

    # --- Availability ---
    stock_status: str = ""  # e.g., "In Stock", "Low Stock", "Out of Stock"
    stock_quantity: int | None = None
    lead_time_days: int | None = None
    delivery_options: list[str] = field(default_factory=list)

    # --- Media ---
    image_url: str = ""
    datasheet_url: str = ""
    product_url: str = ""  # Deep link to supplier product page

    # --- Specifications (flexible key-value store) ---
    specifications: dict[str, Any] = field(default_factory=dict)

    # --- Ratings & Reviews ---
    rating: float = 0.0  # 0-5 scale
    review_count: int = 0

    # --- Metadata ---
    scraped_at: str = ""
    updated_at: str = ""
    data_quality_score: float = 0.0  # 0-1, confidence in data accuracy

    def __post_init__(self):
        if not self.scraped_at:
            self.scraped_at = datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = self.scraped_at
        if not self.unified_id and self.supplier and self.supplier_product_id:
            self.unified_id = f"{self.supplier.value}_{self.supplier_product_id}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["supplier"] = self.supplier.value
        result["category"] = self.category.value
        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    @property
    def is_in_stock(self) -> bool:
        """Quick stock check."""
        return self.stock_status.lower() in ["in stock", "available", "yes", "true", "instock"]

    @property
    def price_excl_vat(self) -> float:
        """Price excluding VAT (UK VAT = 20%)."""
        if self.vat_included and self.current_price > 0:
            return round(self.current_price / 1.2, 2)
        return self.current_price

    @property
    def savings_amount(self) -> float:
        """Money saved vs original price."""
        if self.was_price > self.current_price:
            return round(self.was_price - self.current_price, 2)
        return 0.0


class ProductNormalizer:
    """
    Normalizes product data from any supplier into the UnifiedProduct schema.

    Usage:
        normalizer = ProductNormalizer()

        # From Screwfix
        screwfix_product = screwfix_scraper.scrape_category(...)[0]
        unified = normalizer.from_screwfix(screwfix_product)

        # From Toolstation
        toolstation_product = toolstation_scraper.search_products(...)[0]
        unified = normalizer.from_toolstation(toolstation_product)
    """

    # Category mapping from supplier terms to standard categories
    CATEGORY_KEYWORDS: ClassVar[dict[ProductCategory, list[str]]] = {
        ProductCategory.CABLE: [
            "cable",
            "wire",
            "flex",
            "twin",
            "earth",
            "conductor",
            "6242",
            "6241",
            "6491",
            "armoured",
            "swa",
        ],
        ProductCategory.SWITCHES_SOCKETS: [
            "socket",
            "switch",
            "dp",
            "spur",
            "fused",
            "isolator",
            "toggle",
            "dimmer",
            "rocker",
        ],
        ProductCategory.CONSUMER_UNITS: [
            "consumer unit",
            "distribution board",
            "fuse board",
            "db",
            "duplex",
            "enclosure",
        ],
        ProductCategory.MCB_RCD_RCBO: [
            "mcb",
            "rcd",
            "rcbo",
            "breaker",
            "circuit breaker",
            "miniature",
            "residual",
        ],
        ProductCategory.LIGHTING: [
            "light",
            "led",
            "lamp",
            "luminaire",
            "downlight",
            "panel",
            "tube",
            "spotlight",
            "floodlight",
        ],
        ProductCategory.CONDUIT_TRUNKING: [
            "conduit",
            "trunking",
            "ducting",
            "channel",
            "raceway",
            "minitrunk",
            "maxi",
        ],
        ProductCategory.TEST_EQUIPMENT: [
            "tester",
            "multimeter",
            "megger",
            "fluke",
            "installation tester",
            "pat tester",
        ],
        ProductCategory.HEATING_COOLING: [
            "heater",
            "fan",
            "ventilation",
            "extractor",
            "cooling",
            "air conditioning",
        ],
        ProductCategory.SECURITY_FIRE: [
            "alarm",
            "smoke",
            "fire",
            "co alarm",
            "detector",
            "sensor",
            "cctv",
            "camera",
        ],
        ProductCategory.WIRING_ACCESSORIES: [
            "terminal",
            "wago",
            "connector",
            "junction box",
            "gland",
            "trunking accessory",
        ],
        ProductCategory.DISTRIBUTION: [
            "switchgear",
            "contactor",
            "relay",
            "isolator",
            "transformer",
            "inverter",
        ],
        ProductCategory.TOOLS: [
            "drill",
            "driver",
            "saw",
            "plier",
            "screwdriver",
            "tool",
            "cutter",
            "crimper",
        ],
        ProductCategory.FIXINGS: [
            "screw",
            "plug",
            "anchor",
            "clip",
            "saddle",
            "bracket",
            "cable tie",
            "strap",
        ],
    }

    def __init__(self):
        self.normalization_stats = {
            "total_processed": 0,
            "by_supplier": {},
            "category_distribution": {},
        }

    def infer_category(
        self, name: str, description: str = "", supplier_category: str = ""
    ) -> ProductCategory:
        """
        Infer standard product category from text fields.
        Uses keyword matching across product name, description, and supplier category.
        """
        text = f"{name} {description} {supplier_category}".lower()

        scores = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[category] = score

        if scores:
            return max(scores, key=scores.get)
        return ProductCategory.GENERAL

    def from_screwfix(self, screwfix_product) -> UnifiedProduct:
        """Convert Screwfix product to unified format."""
        p = screwfix_product

        category = self.infer_category(p.name, p.description, p.category)

        unified = UnifiedProduct(
            supplier=Supplier.SCREWFIX,
            supplier_product_id=p.product_id,
            sku=p.sku,
            name=p.name,
            brand=p.brand,
            description=p.description,
            category=category,
            subcategory=p.subcategory,
            current_price=p.price_gbp,
            was_price=p.original_price,
            discount_percent=p.discount_percent,
            stock_status=p.stock_status,
            rating=p.rating,
            review_count=p.review_count,
            image_url=p.image_url,
            product_url=p.product_url,
            specifications=p.specifications if p.specifications else {},
            scraped_at=p.scraped_at,
            data_quality_score=0.85,  # High quality from major retailer
        )

        self._update_stats(Supplier.SCREWFIX, category)
        return unified

    def from_toolstation(self, toolstation_product) -> UnifiedProduct:
        """Convert Toolstation product to unified format."""
        p = toolstation_product

        category = self.infer_category(p.name, p.description)

        # Map stock boolean to status string
        stock_status = "In Stock" if p.in_stock else "Out of Stock"

        unified = UnifiedProduct(
            supplier=Supplier.TOOLSTATION,
            supplier_product_id=p.product_id,
            sku=p.sku,
            name=p.name,
            brand=p.brand,
            description=p.description,
            category=category,
            current_price=p.price_gbp,
            was_price=p.original_price,
            discount_percent=p.discount_percent,
            stock_status=stock_status,
            rating=p.rating,
            review_count=p.review_count,
            image_url=p.image_url,
            product_url=p.product_url,
            scraped_at=p.scraped_at,
            data_quality_score=0.85,
        )

        self._update_stats(Supplier.TOOLSTATION, category)
        return unified

    def from_edata(self, edata_record: dict) -> UnifiedProduct:
        """Convert EDATA record to unified format."""
        # EDATA provides rich technical data but no pricing
        category = self.infer_category(
            edata_record.get("productName", ""), edata_record.get("description", "")
        )

        return UnifiedProduct(
            supplier=Supplier.EDATA,
            supplier_product_id=edata_record.get("productId", ""),
            sku=edata_record.get("manufacturerPartNumber", ""),
            mpn=edata_record.get("manufacturerPartNumber", ""),
            gtin=edata_record.get("gtin", ""),
            name=edata_record.get("productName", ""),
            brand=edata_record.get("brand", ""),
            description=edata_record.get("description", ""),
            category=category,
            specifications=edata_record.get("technicalAttributes", {}),
            image_url=edata_record.get("imageUrl", ""),
            datasheet_url=edata_record.get("datasheetUrl", ""),
            data_quality_score=0.95,  # Manufacturer-approved data
            scraped_at=datetime.utcnow().isoformat(),
        )

    def from_schneider_api(self, api_record: dict) -> UnifiedProduct:
        """Convert Schneider Electric API response to unified format."""
        product = api_record.get("product", {})
        pricing = api_record.get("pricing", {})

        category = self.infer_category(product.get("name", ""), product.get("shortDescription", ""))

        return UnifiedProduct(
            supplier=Supplier.SCHNEIDER_ELECTRIC,
            supplier_product_id=product.get("commercialReference", ""),
            mpn=product.get("commercialReference", ""),
            gtin=product.get("gtin", ""),
            name=product.get("name", ""),
            brand="Schneider Electric",
            description=product.get("longDescription", ""),
            category=category,
            current_price=pricing.get("publicListPrice", 0.0),
            trade_price=pricing.get("netPrice", 0.0),
            stock_status=api_record.get("stockStatus", ""),
            stock_quantity=api_record.get("stockQuantity"),
            image_url=product.get("mainImageUrl", ""),
            datasheet_url=product.get("datasheetUrl", ""),
            specifications=product.get("technicalAttributes", {}),
            data_quality_score=0.98,
            scraped_at=datetime.utcnow().isoformat(),
        )

    def from_pricelynx(self, pricelynx_record: dict) -> UnifiedProduct:
        """Convert PriceLynx record to unified format."""
        category = self.infer_category(
            pricelynx_record.get("description", ""),
            supplier_category=pricelynx_record.get("category", ""),
        )

        return UnifiedProduct(
            supplier=Supplier.PRICELYNX,
            supplier_product_id=pricelynx_record.get("productCode", ""),
            sku=pricelynx_record.get("productCode", ""),
            mpn=pricelynx_record.get("manufacturerCode", ""),
            name=pricelynx_record.get("description", ""),
            brand=pricelynx_record.get("manufacturer", ""),
            category=category,
            current_price=pricelynx_record.get("tradePrice", 0.0),
            trade_price=pricelynx_record.get("tradePrice", 0.0),
            unit_of_measure=pricelynx_record.get("unit", "each"),
            specifications=pricelynx_record.get("specifications", {}),
            data_quality_score=0.90,
            scraped_at=datetime.utcnow().isoformat(),
        )

    def _update_stats(self, supplier: Supplier, category: ProductCategory):
        """Track normalization statistics."""
        self.normalization_stats["total_processed"] += 1

        sup_key = supplier.value
        self.normalization_stats["by_supplier"][sup_key] = (
            self.normalization_stats["by_supplier"].get(sup_key, 0) + 1
        )

        cat_key = category.value
        self.normalization_stats["category_distribution"][cat_key] = (
            self.normalization_stats["category_distribution"].get(cat_key, 0) + 1
        )

    def get_stats(self) -> dict:
        """Get normalization statistics."""
        return self.normalization_stats.copy()

    def reset_stats(self):
        """Reset statistics counters."""
        self.normalization_stats = {
            "total_processed": 0,
            "by_supplier": {},
            "category_distribution": {},
        }


# Utility functions for batch processing
def normalize_batch(
    products: list[Any], source_type: str, normalizer: ProductNormalizer
) -> list[UnifiedProduct]:
    """
    Batch normalize products from a specific source.

    Args:
        products: List of supplier-specific product objects
        source_type: One of 'screwfix', 'toolstation', 'edata', etc.
        normalizer: ProductNormalizer instance

    Returns:
        List of UnifiedProduct records
    """
    mapper = {
        "screwfix": normalizer.from_screwfix,
        "toolstation": normalizer.from_toolstation,
        "edata": normalizer.from_edata,
        "schneider": normalizer.from_schneider_api,
        "pricelynx": normalizer.from_pricelynx,
    }

    convert = mapper.get(source_type.lower())
    if not convert:
        raise ValueError(f"Unknown source type: {source_type}")

    return [convert(p) for p in products]


def merge_duplicate_products(
    products: list[UnifiedProduct], match_fields: list[str] | None = None
) -> list[UnifiedProduct]:
    """
    Merge duplicate products from different suppliers.
    Keeps the cheapest price and richest data.

    Args:
        products: List of UnifiedProduct records
        match_fields: Fields to use for deduplication (default: name + brand)

    Returns:
        Deduplicated list with merged supplier data
    """
    if match_fields is None:
        match_fields = ["name", "brand"]

    groups = {}

    for p in products:
        key = "|".join([getattr(p, f, "").lower().strip() for f in match_fields])

        if key not in groups:
            groups[key] = []
        groups[key].append(p)

    merged = []
    for _key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue

        # Merge: cheapest price, all supplier URLs, combined specs
        best = min(group, key=lambda x: x.current_price if x.current_price > 0 else float("inf"))

        # Collect all supplier product URLs
        all_urls = {p.supplier.value: p.product_url for p in group if p.product_url}

        # Merge specifications
        merged_specs = {}
        for p in group:
            merged_specs.update(p.specifications)

        best.product_url = json.dumps(all_urls) if len(all_urls) > 1 else best.product_url
        best.specifications = merged_specs
        best.data_quality_score = max(p.data_quality_score for p in group)

        merged.append(best)

    return merged


# Standalone test
if __name__ == "__main__":
    normalizer = ProductNormalizer()

    # Test category inference
    test_names = [
        ("Prysmian 6242Y Twin & Earth Cable 2.5mm²", ProductCategory.CABLE),
        ("Hager 32A Type B MCB Single Pole", ProductCategory.MCB_RCD_RCBO),
        ("LAP LED GU10 Lamp 5W Warm White", ProductCategory.LIGHTING),
        ("Wylex 10-Way Dual RCD Consumer Unit", ProductCategory.CONSUMER_UNITS),
        ("Fluke 1653B Installation Tester", ProductCategory.TEST_EQUIPMENT),
    ]

    print("=" * 60)
    print("CATEGORY INFERENCE TEST")
    print("=" * 60)

    for name, expected in test_names:
        inferred = normalizer.infer_category(name)
        status = "PASS" if inferred == expected else "FAIL"
        print(f"  [{status}] '{name[:40]}...' -> {inferred.value}")

    print(f"\nTotal tests: {len(test_names)}")
