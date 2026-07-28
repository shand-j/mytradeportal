"""
Screwfix Product Data Scraper
Extracts product information from Screwfix UK using Apify Actor.
Public prices are visible without login - no trade account required.

Usage:
    from scrapers.screwfix_scraper import ScrewfixScraper

    scraper = ScrewfixScraper(api_token="your_apify_token")
    products = scraper.scrape_category(
        category_url="https://www.screwfix.com/c/electrical-lighting/cat830699",
        max_items=100
    )
"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

import requests


@dataclass
class ScrewfixProduct:
    """Normalized Screwfix product record."""

    source: str = "screwfix"
    product_id: str = ""
    sku: str = ""
    name: str = ""
    brand: str = ""
    price_gbp: float = 0.0
    original_price: float = 0.0
    discount_percent: float = 0.0
    category: str = ""
    subcategory: str = ""
    description: str = ""
    specifications: dict = None
    stock_status: str = ""
    rating: float = 0.0
    review_count: int = 0
    image_url: str = ""
    product_url: str = ""
    scraped_at: str = ""

    def __post_init__(self):
        if self.specifications is None:
            self.specifications = {}
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
            "subcategory": self.subcategory,
            "description": self.description,
            "specifications": self.specifications,
            "stock_status": self.stock_status,
            "rating": self.rating,
            "review_count": self.review_count,
            "image_url": self.image_url,
            "product_url": self.product_url,
            "scraped_at": self.scraped_at,
        }


class ScrewfixScraper:
    """
    Screwfix scraper using Apify Actor.

    The Apify actor 'datasaurus/screwfix' extracts:
    - Product names, SKUs, brands, prices
    - Specifications, descriptions, images
    - Stock status, ratings, reviews

    Cost: ~$5 per 1,000 products on Apify
    """

    APIFY_BASE = "https://api.apify.com/v2"
    ACTOR_ID = "datasaurus~screwfix-event"

    # Key electrical categories on Screwfix
    ELECTRICAL_CATEGORIES: ClassVar[dict[str, str]] = {
        "cable": "https://www.screwfix.com/c/electrical-lighting/cable/cat830700",
        "switches_sockets": "https://www.screwfix.com/c/electrical-lighting/switches-sockets/cat830701",
        "consumer_units": "https://www.screwfix.com/c/electrical-lighting/consumer-units-circuit-breakers/cat830702",
        "lighting": "https://www.screwfix.com/c/electrical-lighting/lighting/cat830703",
        "conduit_trunking": "https://www.screwfix.com/c/electrical-lighting/conduit-trunking-cable-management/cat830705",
        "test_equipment": "https://www.screwfix.com/c/electrical-lighting/electrical-testers-meters/cat830706",
        "heaters": "https://www.screwfix.com/c/electrical-lighting/heaters/cat830707",
        "security_fire": "https://www.screwfix.com/c/electrical-lighting/security-fire-safety/cat830708",
        "doorbells": "https://www.screwfix.com/c/electrical-lighting/doorbells-chimes/cat830709",
        "batteries": "https://www.screwfix.com/c/electrical-lighting/batteries/cat830710",
    }

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def scrape_category(
        self,
        category_url: str,
        max_items: int = 100,
        scrape_details: bool = True,
        scrape_reviews: bool = False,
        max_total_charge_usd: float = 50.0,
        wait_for_completion: bool = True,
        timeout_seconds: int = 300,
    ) -> list[ScrewfixProduct]:
        """
        Scrape products from a Screwfix category page.

        Args:
            category_url: Full URL of the category page
            max_items: Maximum products to scrape (default 100)
            scrape_details: Whether to scrape individual product pages (slower but more data)
            scrape_reviews: Whether to scrape reviews (requires scrape_details=True)
            max_total_charge_usd: Maximum Apify charge for this run
            wait_for_completion: Whether to wait for the actor to finish
            timeout_seconds: Maximum time to wait for results

        Returns:
            List of ScrewfixProduct records
        """
        if not self.api_token:
            from data_pipeline.config import settings

            if settings.pipeline_demo_mode:
                print("WARNING: No Apify API token provided. Using demo mode with sample data.")
                return self._get_demo_data(category_url, max_items)
            print(
                "WARNING: No Apify API token provided and demo mode is disabled. Skipping scrape."
            )
            return []

        # Build the actor input for datasaurus/screwfix-event
        # Note: this actor's input schema uses snake_case keys.
        run_input = {
            "start_urls": [{"url": category_url}],
            "scrape_product_page": scrape_details,
            "scrape_reviews": scrape_reviews and scrape_details,
            "scrape_question_answers": False,
            "max_categories": 1,
            "max_products_per_category": max_items,
            "max_products": max_items,
            "max_reviews": 0,
            "max_question_answers": 0,
        }

        # Start the actor run
        run_url = f"{self.APIFY_BASE}/acts/{self.ACTOR_ID}/runs"

        try:
            response = self.session.post(
                run_url,
                params={
                    "token": self.api_token,
                    "maxTotalChargeUsd": max_total_charge_usd,
                    "maxItems": max_items,
                },
                json=run_input,
                timeout=30,
            )
            response.raise_for_status()
            run_data = response.json()
            run_id = run_data["data"]["id"]

            print(f"Started Screwfix scraper run: {run_id}")

            if wait_for_completion:
                return self._wait_and_fetch_results(run_id, timeout_seconds)
            else:
                return []

        except requests.exceptions.HTTPError as e:
            body = ""
            if e.response is not None:
                try:
                    body = e.response.text
                except Exception:
                    body = "<unreadable>"
            print(f"Error starting scraper: {e} — response body: {body}")
            return []
        except requests.exceptions.RequestException as e:
            print(f"Error starting scraper: {e}")
            return []

    def _wait_and_fetch_results(self, run_id: str, timeout_seconds: int) -> list[ScrewfixProduct]:
        """Wait for actor completion and fetch results."""
        dataset_id: str | None = None
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
                elif status == "FAILED":
                    print(f"Scraper run failed with status: {status}")
                    return []
                elif status in ["ABORTED", "TIMED-OUT"]:
                    # Cost-capped or platform-timed runs can still contain useful data.
                    print(f"Scraper run ended with status: {status}; fetching partial results")
                    dataset_id = status_data["data"]["defaultDatasetId"]
                    break

                print(f"Scraper status: {status}... waiting")
                time.sleep(5)

            except requests.exceptions.RequestException as e:
                print(f"Error checking status: {e}")
                time.sleep(5)

        if not dataset_id:
            print("Local timeout reached; checking final status for partial dataset")
            try:
                status_url = f"{self.APIFY_BASE}/acts/{self.ACTOR_ID}/runs/{run_id}"
                response = self.session.get(
                    status_url, params={"token": self.api_token}, timeout=10
                )
                response.raise_for_status()
                status_data = response.json()
                dataset_id = status_data["data"].get("defaultDatasetId")
            except requests.exceptions.RequestException as e:
                print(f"Error fetching final status: {e}")
                return []

        if not dataset_id:
            print("Timeout waiting for scraper results")
            return []

        # Fetch results from dataset
        return self._fetch_dataset(dataset_id)

    def fetch_dataset(self, dataset_id: str) -> list[ScrewfixProduct]:
        """Fetch all items from an existing Apify dataset by its ID."""
        items_url = f"{self.APIFY_BASE}/datasets/{dataset_id}/items"

        try:
            response = self.session.get(
                items_url,
                params={"token": self.api_token, "format": "json", "clean": "true"},
                timeout=60,
            )
            response.raise_for_status()
            raw_items = response.json()

            print(f"Retrieved {len(raw_items)} products from dataset {dataset_id}")
            return [self._normalize_item(item) for item in raw_items]

        except requests.exceptions.RequestException as e:
            print(f"Error fetching dataset {dataset_id}: {e}")
            return []

    def _fetch_dataset(self, dataset_id: str) -> list[ScrewfixProduct]:
        """Fetch all items from an Apify dataset after a run completes."""
        return self.fetch_dataset(dataset_id)

    def _normalize_item(self, raw_item: dict) -> ScrewfixProduct:
        """Convert raw scraper output to normalized ScrewfixProduct."""
        # Extract price - handle various formats
        price = 0.0
        raw_price = raw_item.get("price", raw_item.get("currentPrice", "0"))
        if isinstance(raw_price, str):
            price = float(raw_price.replace("£", "").replace(",", ""))
        elif isinstance(raw_price, int | float):
            price = float(raw_price)

        # Extract original price (rrp / wasPrice / originalPrice)
        original_price = 0.0
        raw_orig = raw_item.get("rrp", raw_item.get("originalPrice", raw_item.get("wasPrice", "0")))
        if isinstance(raw_orig, str):
            original_price = float(raw_orig.replace("£", "").replace(",", "")) if raw_orig else 0.0
        elif isinstance(raw_orig, int | float):
            original_price = float(raw_orig)

        # Calculate discount
        discount = 0.0
        if original_price > 0 and price > 0:
            discount = round((1 - price / original_price) * 100, 1)

        sku = str(raw_item.get("sku", raw_item.get("productCode", "")))

        # Build specifications dict from either a dict or a technicalSpecifications list
        specs: dict[str, Any] = {}
        if "specifications" in raw_item and isinstance(raw_item["specifications"], dict):
            specs = raw_item["specifications"]
        elif "technicalSpecifications" in raw_item and isinstance(
            raw_item["technicalSpecifications"], list
        ):
            specs = {
                str(entry.get("name", "")): str(entry.get("value", ""))
                for entry in raw_item["technicalSpecifications"]
                if entry.get("name")
            }
        elif "techSpecs" in raw_item and isinstance(raw_item["techSpecs"], dict):
            specs = raw_item["techSpecs"]

        # Derive product URL if not provided (Screwfix product pages are /p/<sku>)
        product_url = raw_item.get("url", "")
        if not product_url and sku:
            product_url = f"https://www.screwfix.com/p/{sku}"

        # Pick the first image when a list is returned
        image_url = raw_item.get("imageUrl", raw_item.get("image", ""))
        if isinstance(image_url, list) and image_url:
            image_url = image_url[0]

        return ScrewfixProduct(
            product_id=str(raw_item.get("id", raw_item.get("productId", sku))),
            sku=sku,
            name=raw_item.get("name", raw_item.get("title", "")),
            brand=raw_item.get("brand", ""),
            price_gbp=price,
            original_price=original_price,
            discount_percent=discount,
            category=raw_item.get("category", ""),
            subcategory=raw_item.get("subcategory", ""),
            description=raw_item.get("description", ""),
            specifications=specs,
            stock_status=raw_item.get("availability", raw_item.get("stockStatus", "")),
            rating=raw_item.get("starRating", raw_item.get("rating", 0.0)),
            review_count=raw_item.get("reviewCount", 0),
            image_url=image_url,
            product_url=product_url,
        )

    def _get_demo_data(self, category_url: str, max_items: int) -> list[ScrewfixProduct]:
        """Generate realistic demo data when no API token is available."""
        demo_products = [
            ScrewfixProduct(
                product_id="SF_001",
                sku="8947P",
                name="British General 13A 2-Gang DP Switched Socket",
                brand="British General",
                price_gbp=4.99,
                category="Switches & Sockets",
                subcategory="Socket Outlets",
                description="Double pole switched socket outlet with twin earth terminals",
                stock_status="In Stock",
                rating=4.7,
                review_count=328,
                product_url="https://www.screwfix.com/p/8947P",
            ),
            ScrewfixProduct(
                product_id="SF_002",
                sku="7265P",
                name="Wylex 10-Way Dual RCD Metal Consumer Unit",
                brand="Wylex",
                price_gbp=89.99,
                original_price=110.00,
                discount_percent=18.2,
                category="Consumer Units",
                subcategory="Metal Consumer Units",
                description="10-way dual RCD metal consumer unit with 100A main switch",
                stock_status="In Stock",
                rating=4.8,
                review_count=156,
                product_url="https://www.screwfix.com/p/7265P",
            ),
            ScrewfixProduct(
                product_id="SF_003",
                sku="1985P",
                name="Prysmian 6242Y Twin & Earth Cable 2.5mm² x 50m",
                brand="Prysmian",
                price_gbp=42.99,
                category="Cable",
                subcategory="Twin & Earth",
                description="6242Y twin and earth cable, 2.5mm², 50m drum",
                stock_status="In Stock",
                rating=4.9,
                review_count=512,
                product_url="https://www.screwfix.com/p/1985P",
            ),
            ScrewfixProduct(
                product_id="SF_004",
                sku="3456P",
                name="LAP LED GU10 Lamp 5W Warm White",
                brand="LAP",
                price_gbp=3.49,
                original_price=4.99,
                discount_percent=30.1,
                category="Lighting",
                subcategory="LED Lamps",
                description="5W LED GU10 lamp, warm white 3000K, 450 lumens",
                stock_status="In Stock",
                rating=4.5,
                review_count=892,
                product_url="https://www.screwfix.com/p/3456P",
            ),
            ScrewfixProduct(
                product_id="SF_005",
                sku="5621P",
                name="DETA 20A 2-Gang 2-Way Light Switch",
                brand="DETA",
                price_gbp=3.29,
                category="Switches & Sockets",
                subcategory="Light Switches",
                description="20A 2-gang 2-way light switch, white moulded",
                stock_status="In Stock",
                rating=4.6,
                review_count=245,
                product_url="https://www.screwfix.com/p/5621P",
            ),
            ScrewfixProduct(
                product_id="SF_006",
                sku="7894P",
                name="Fluke 1653B Multifunction Installation Tester",
                brand="Fluke",
                price_gbp=849.99,
                category="Test Equipment",
                subcategory="Installation Testers",
                description="Multifunction installation tester for electrical safety testing",
                stock_status="In Stock",
                rating=4.9,
                review_count=67,
                product_url="https://www.screwfix.com/p/7894P",
            ),
            ScrewfixProduct(
                product_id="SF_007",
                sku="9012P",
                name="Hager 32A Type B MCB 6kA",
                brand="Hager",
                price_gbp=8.99,
                category="Consumer Units",
                subcategory="MCBs",
                description="32A single pole type B miniature circuit breaker, 6kA",
                stock_status="In Stock",
                rating=4.8,
                review_count=189,
                product_url="https://www.screwfix.com/p/9012P",
            ),
            ScrewfixProduct(
                product_id="SF_008",
                sku="2345P",
                name="Marshall-Tufflex PVC Mini Trunking 16x16mm x 3m",
                brand="Marshall-Tufflex",
                price_gbp=5.49,
                category="Conduit & Trunking",
                subcategory="Mini Trunking",
                description="PVC mini trunking 16x16mm, 3m length, white",
                stock_status="In Stock",
                rating=4.4,
                review_count=78,
                product_url="https://www.screwfix.com/p/2345P",
            ),
        ]

        return demo_products[:max_items]

    def search_products(self, query: str, max_items: int = 50) -> list[ScrewfixProduct]:
        """
        Search Screwfix products by keyword.
        Uses the search page as the starting URL.
        """
        search_url = f"https://www.screwfix.com/search?search={query.replace(' ', '+')}"
        return self.scrape_category(search_url, max_items)


# Standalone execution for testing
if __name__ == "__main__":
    scraper = ScrewfixScraper()

    print("=" * 60)
    print("SCREWFIX PRODUCT DATA EXTRACTOR - DEMO MODE")
    print("=" * 60)
    print("\nAvailable electrical categories:")
    for key, url in scraper.ELECTRICAL_CATEGORIES.items():
        print(f"  - {key}: {url}")

    print("\n--- Demo: Scraping Switches & Sockets ---")
    products = scraper.scrape_category(
        scraper.ELECTRICAL_CATEGORIES["switches_sockets"], max_items=5
    )

    print(f"\nRetrieved {len(products)} products:\n")
    for p in products:
        print(f"  {p.name}")
        print(f"    Brand: {p.brand} | Price: £{p.price_gbp}")
        print(f"    SKU: {p.sku} | Stock: {p.stock_status}")
        print()
