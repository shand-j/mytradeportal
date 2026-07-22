"""Tests for file upload endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_presigned_upload_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/files/presigned-upload", json={"filename": "test.pdf"})
    assert response.status_code == 401


async def test_presigned_upload_returns_key_and_url(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/files/presigned-upload",
        json={"filename": "quote.pdf", "content_type": "application/pdf"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"]
    assert data["fields"]
    assert data["key"].startswith(f"tenants/{admin_client.headers['X-Tenant-ID']}/")
    assert data["key"].endswith("quote.pdf")
