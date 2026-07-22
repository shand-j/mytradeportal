"""
Toolstation Product Data Scraper
Extracts product information from Toolstation UK using Apify Actor.
Public prices visible without login - no trade account required.

Usage:
    from scrapers.toolstation_scraper import ToolstationScraper

    scraper = ToolstationScraper(api_token="your_apify_token")
    products = scraper.search_products(query="consumer unit", max_items=50)
"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

import requests


@dataclass
class ToolstationProduct:
    """Normalized Toolstation product record."""

    source: str = "toolstation"
    product_id: str = ""
    sku: str = ""
    name: str = ""
    brand: str = ""
    price_gbp: float = 0.0
    original_price: float = 0.0
    discount_percent: float = 0.0
    category: str = ""
    description: str = ""
    in_stock: bool = True
    rating: float = 0.0
    review_count: int = 0
    image_url: str = ""
    product_url: str = ""
    scraped_at: str = ""

    def __post_init__(self):
        if not self.scraped_at:
            self.scraped_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "product_id": self.product_id,
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "price_gbp": self.price_gbp,
            "original_price": self.original_price,
            "discount_percent": self.discount_percent,
            "category": self.category,
            "description": self.description,
            "in_stock": self.in_stock,
            "rating": self.rating,
            "review_count": self.review_count,
            "image_url": self.image_url,
            "product_url": self.product_url,
            "scraped_at": self.scraped_at,
        }


class ToolstationScraper:
    """
    Toolstation scraper using Apify Actor (crawlergang/toolstation-scraper).

    The Apify actor extracts:
    - productId, sku, name, brand, price, originalPrice
    - discountPercent, rating, reviewCount, inStock
    - description, imageUrl, url

    Cost: Included in Apify subscription (free tier: 500 products/run max)
    """

    APIFY_BASE = "https://api.apify.com/v2"
    ACTOR_ID = "crawlergang/toolstation-scraper"

    # Key electrical categories on Toolstation
    ELECTRICAL_CATEGORIES: ClassVar[dict[str, str]] = {
        "cable": "https://www.toolstation.com/electrical/cable/cat1006",
        "switches_sockets": "https://www.toolstation.com/electrical/switches-sockets/cat1007",
        "consumer_units": "https://www.toolstation.com/electrical/consumer-units-mcb-rcbo/cat1008",
        "lighting": "https://www.toolstation.com/electrical/lighting/cat1009",
        "conduit_trunking": "https://www.toolstation.com/electrical/conduit-trunking/cat1010",
        "test_equipment": "https://www.toolstation.com/electrical/test-meters/cat1011",
        "heating_cooling": "https://www.toolstation.com/electrical/heating-cooling/cat1012",
        "security_fire": "https://www.toolstation.com/electrical/security-fire/cat1013",
    }

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def search_products(self, query: str, max_items: int = 50) -> list[ToolstationProduct]:
        """
        Search Toolstation products by keyword using Bloomreach Discovery API.

        Args:
            query: Search term (e.g., "consumer unit", "cable 2.5mm")
            max_items: Maximum products to return (max 500 per Apify run)

        Returns:
            List of ToolstationProduct records
        """
        if not self.api_token:
            print("WARNING: No Apify API token. Using demo mode.")
            return self._get_demo_data(query, max_items)

        run_input = {"mode": "searchProducts", "query": query, "maxItems": min(max_items, 500)}

        return self._run_actor(run_input)

    def browse_category(self, category_url: str, max_items: int = 100) -> list[ToolstationProduct]:
        """
        Browse all products in a specific category.

        Args:
            category_url: Category URL path (e.g., "/electrical/cable/cat1006")
                         or full URL
            max_items: Maximum products to return
        """
        if not self.api_token:
            return self._get_demo_data(category_url, max_items)

        # Ensure it's a path, not full URL
        if category_url.startswith("http"):
            from urllib.parse import urlparse

            parsed = urlparse(category_url)
            category_url = parsed.path

        run_input = {
            "mode": "browseCategory",
            "categoryUrl": category_url,
            "maxItems": min(max_items, 500),
        }

        return self._run_actor(run_input)

    def get_product_details(self, product_url: str) -> ToolstationProduct | None:
        """Get detailed information for a specific product."""
        if not self.api_token:
            return None

        run_input = {"mode": "getProductDetails", "productUrl": product_url, "maxItems": 1}

        results = self._run_actor(run_input)
        return results[0] if results else None

    def _run_actor(self, run_input: dict) -> list[ToolstationProduct]:
        """Execute the Apify actor and return normalized products."""
        run_url = f"{self.APIFY_BASE}/acts/{self.ACTOR_ID}/runs"

        try:
            # Start the run
            response = self.session.post(
                run_url, params={"token": self.api_token}, json=run_input, timeout=30
            )
            response.raise_for_status()
            run_data = response.json()
            run_id = run_data["data"]["id"]

            print(f"Started Toolstation scraper run: {run_id}")

            # Wait for completion
            return self._wait_and_fetch_results(run_id)

        except requests.exceptions.RequestException as e:
            print(f"Error running Toolstation scraper: {e}")
            return []

    def _wait_and_fetch_results(
        self, run_id: str, timeout_seconds: int = 300
    ) -> list[ToolstationProduct]:
        """Wait for actor completion and fetch results."""
        dataset_id = None
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            status_url = f"{self.APIFY_BASE}/acts/{self.ACTOR_ID}/runs/{run_id}"

            try:
                response = self.session.get(
                    status_url, params={"token": self.api_token}, timeout=10
                )
                response.raise_for_status()
                status_data = response.json()
                status = status_data["data"]["status"]

                if status == "SUCCEEDED":
                    dataset_id = status_data["data"]["defaultDatasetId"]
                    break
                elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    print(f"Toolstation scraper failed: {status}")
                    return []

                time.sleep(5)

            except requests.exceptions.RequestException:
                time.sleep(5)

        if not dataset_id:
            return []

        # Fetch results
        items_url = f"{self.APIFY_BASE}/datasets/{dataset_id}/items"

        try:
            response = self.session.get(
                items_url, params={"token": self.api_token, "format": "json"}, timeout=60
            )
            response.raise_for_status()
            raw_items = response.json()

            print(f"Retrieved {len(raw_items)} products from Toolstation")
            return [self._normalize_item(item) for item in raw_items]

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Toolstation results: {e}")
            return []

    def _normalize_item(self, raw_item: dict) -> ToolstationProduct:
        """Convert raw scraper output to normalized ToolstationProduct."""
        price = raw_item.get("price", 0)
        if isinstance(price, str):
            price = float(price.replace("£", "").replace(",", ""))

        original = raw_item.get("originalPrice", 0)
        if isinstance(original, str):
            original = float(original.replace("£", "").replace(",", "")) if original else 0.0

        discount = raw_item.get("discountPercent", 0)
        if not discount and original > 0 and price > 0:
            discount = round((1 - price / original) * 100, 1)

        return ToolstationProduct(
            product_id=str(raw_item.get("productId", "")),
            sku=raw_item.get("sku", raw_item.get("productId", "")),
            name=raw_item.get("name", ""),
            brand=raw_item.get("brand", ""),
            price_gbp=float(price) if price else 0.0,
            original_price=float(original) if original else 0.0,
            discount_percent=discount,
            description=raw_item.get("description", ""),
            in_stock=raw_item.get("inStock", True),
            rating=raw_item.get("rating", 0.0),
            review_count=raw_item.get("reviewCount", 0),
            image_url=raw_item.get("imageUrl", ""),
            product_url=raw_item.get("url", ""),
        )

    def _get_demo_data(self, query: str, max_items: int) -> list[ToolstationProduct]:
        """Generate realistic demo data."""
        demo_products = [
            ToolstationProduct(
                product_id="13036",
                sku="13036",
                name="Dewalt DCD778D2 18V XR Brushless Combi Drill",
                brand="Dewalt",
                price_gbp=149.98,
                original_price=199.99,
                discount_percent=25.0,
                description="18V brushless combi drill with 2 x 2Ah batteries",
                in_stock=True,
                rating=4.8,
                review_count=1245,
                product_url="https://www.toolstation.com/dewalt-combi-drill/p13036",
            ),
            ToolstationProduct(
                product_id="28941",
                sku="28941",
                name="Wylex 10-Way Dual RCD Metal Consumer Unit + 10 MCBs",
                brand="Wylex",
                price_gbp=94.98,
                original_price=120.00,
                discount_percent=20.9,
                description="Complete 10-way consumer unit package with MCBs included",
                in_stock=True,
                rating=4.7,
                review_count=432,
                product_url="https://www.toolstation.com/wylex-consumer-unit/p28941",
            ),
            ToolstationProduct(
                product_id="15672",
                sku="15672",
                name="Prysmian 6242Y Twin & Earth Cable 2.5mm² x 100m",
                brand="Prysmian",
                price_gbp=78.98,
                description="Twin and earth cable grey 2.5mm², 100m drum",
                in_stock=True,
                rating=4.9,
                review_count=678,
                product_url="https://www.toolstation.com/prysmian-cable/p15672",
            ),
            ToolstationProduct(
                product_id="38471",
                sku="38471",
                name="LAP 13A Switched Fused Connection Unit",
                brand="LAP",
                price_gbp=3.78,
                description="Switched fused connection unit with neon indicator",
                in_stock=True,
                rating=4.5,
                review_count=234,
                product_url="https://www.toolstation.com/lap-fused-connection-unit/p38471",
            ),
            ToolstationProduct(
                product_id="51293",
                sku="51293",
                name="Hager 32A Type B MCB Single Pole 6kA",
                brand="Hager",
                price_gbp=7.49,
                description="32A single pole MCB type B 6kA breaking capacity",
                in_stock=True,
                rating=4.8,
                review_count=156,
                product_url="https://www.toolstation.com/hager-mcb/p51293",
            ),
            ToolstationProduct(
                product_id="64782",
                sku="64782",
                name="Knightsbridge LED GU10 Lamp 5W Warm White Pack of 10",
                brand="Knightsbridge",
                price_gbp=12.98,
                original_price=16.99,
                discount_percent=23.6,
                description="5W LED GU10 lamps warm white 3000K, pack of 10",
                in_stock=True,
                rating=4.6,
                review_count=892,
                product_url="https://www.toolstation.com/knightsbridge-led-gu10/p64782",
            ),
        ]

        return demo_products[:max_items]


# Standalone execution
if __name__ == "__main__":
    scraper = ToolstationScraper()

    print("=" * 60)
    print("TOOLSTATION PRODUCT DATA EXTRACTOR - DEMO MODE")
    print("=" * 60)

    print("\n--- Searching for 'consumer unit' ---")
    products = scraper.search_products("consumer unit", max_items=5)

    print(f"\nFound {len(products)} products:\n")
    for p in products:
        print(f"  {p.name}")
        print(f"    Brand: {p.brand} | Price: £{p.price_gbp}")
        print(f"    SKU: {p.sku} | In Stock: {p.in_stock}")
        print()
