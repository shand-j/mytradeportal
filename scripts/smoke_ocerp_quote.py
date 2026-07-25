"""Smoke test the OCERP quote generation path and clean up afterwards."""

import asyncio
import os
import sys
from uuid import uuid4

import httpx

BASE_URL = "https://api-production-8c41.up.railway.app"
SETUP_TOKEN = os.environ.get("SETUP_TOKEN", "")


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, timeout=350.0, follow_redirects=True)


async def run() -> int:
    if not SETUP_TOKEN:
        print("SETUP_TOKEN env var is required", file=sys.stderr)
        return 1

    slug = f"ocerp-smoke-{uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "Smoke-test-password-123"
    tenant_id: str | None = None

    async with client() as c:
        r = await c.post(
            "/tenants",
            headers={"x-setup-token": SETUP_TOKEN},
            json={
                "slug": slug,
                "name": "OCERP Smoke Test Tenant",
                "admin_email": email,
                "admin_password": password,
                "admin_name": "Smoke Admin",
            },
        )
        print(f"Create tenant: {r.status_code}")
        if r.status_code != 201:
            print(r.text)
            return 1
        tenant_id = r.json()["id"]

        r = await c.post(
            "/auth/login",
            json={"email": email, "password": password, "tenant_slug": slug},
        )
        print(f"Login: {r.status_code}")
        if r.status_code != 200:
            print(r.text)
            return 1

        c.headers["X-Tenant-ID"] = tenant_id

        r = await c.post(
            "/contacts",
            json={"name": "Smoke Customer", "email": "customer@example.com"},
        )
        print(f"Create contact: {r.status_code}")
        if r.status_code != 201:
            print(r.text)
            return 1
        contact_id = r.json()["id"]

        r = await c.post(
            "/quotes/generate",
            json={
                "contact_id": contact_id,
                "description": "Install a new double socket and replace a broken light switch in a 2 bedroom flat",
                "property_type": "flat",
                "use_ocerp": True,
            },
        )
        print(f"Generate OCERP quote: {r.status_code}")
        print(r.text[:2000])
        if r.status_code != 201:
            return 1
        quote = r.json()
        print(
            f"Quote id: {quote['id']}, total: {quote['total']}, line_items: {len(quote['line_items'])}"
        )
        if quote.get("bill_of_quantities"):
            print(f"BoQ confidence: {quote['bill_of_quantities']['confidence']}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
