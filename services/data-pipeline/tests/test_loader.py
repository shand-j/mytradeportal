"""Tests for the domestic electrical data pipeline loader."""

from decimal import Decimal

from data_pipeline.loader import (
    _category_to_cost_category,
    _extract_metre_length,
    deduplicate_products,
    unified_product_to_cost_item,
)
from data_pipeline.normalizer.unified_product import ProductCategory, Supplier, UnifiedProduct


def test_extract_metre_length() -> None:
    assert _extract_metre_length("Prysmian 6242Y Twin & Earth Cable 2.5mm² x 50m") == 50
    assert _extract_metre_length("Cable 100m drum") == 100
    assert _extract_metre_length("13A Socket") is None


def test_category_to_cost_category() -> None:
    assert _category_to_cost_category(ProductCategory.CABLE) == "Cable"
    assert _category_to_cost_category(ProductCategory.SWITCHES_SOCKETS) == "Switches & Sockets"
    assert _category_to_cost_category(ProductCategory.GENERAL) == "General"


def test_unified_product_to_cost_item_ex_vat() -> None:
    product = UnifiedProduct(
        supplier=Supplier.SCREWFIX,
        supplier_product_id="123",
        sku="456",
        name="British General 13A 2-Gang DP Switched Socket",
        brand="British General",
        category=ProductCategory.SWITCHES_SOCKETS,
        current_price=4.99,
        vat_included=True,
    )
    item = unified_product_to_cost_item(product)
    assert item is not None
    assert item["code"] == "DOM-screwfix-456"
    assert item["unit_price"] == Decimal("4.1583")  # 4.99 / 1.20 rounded to 4 dp
    assert item["unit"] == "each"
    assert item["source"] == "domestic_pipeline"
    assert item["extra_data"]["supplier"] == "screwfix"
    assert item["extra_data"]["brand"] == "British General"


def test_unified_product_to_cost_item_cable_per_metre() -> None:
    product = UnifiedProduct(
        supplier=Supplier.TOOLSTATION,
        supplier_product_id="789",
        sku="789",
        name="Prysmian 6242Y Twin & Earth Cable 2.5mm² x 50m",
        brand="Prysmian",
        category=ProductCategory.CABLE,
        current_price=42.99,
        vat_included=True,
    )
    item = unified_product_to_cost_item(product)
    assert item is not None
    assert item["unit"] == "m"
    # 42.99 / 1.20 = 35.825; / 50 = 0.7165 -> kept at 4 dp
    assert item["unit_price"] == Decimal("0.7165")


def test_deduplicate_products_keeps_first() -> None:
    products = [
        UnifiedProduct(
            supplier=Supplier.SCREWFIX, sku="A", name="A", current_price=1.0
        ),
        UnifiedProduct(
            supplier=Supplier.SCREWFIX, sku="A", name="A2", current_price=2.0
        ),
        UnifiedProduct(
            supplier=Supplier.TOOLSTATION, sku="A", name="A3", current_price=3.0
        ),
    ]
    unique = deduplicate_products(products)
    assert len(unique) == 2
    assert unique[0].supplier == Supplier.SCREWFIX
    assert unique[1].supplier == Supplier.TOOLSTATION
