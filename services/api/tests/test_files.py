"""Tests for file upload/download endpoints (API-proxied; MinIO is private)."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _fake_s3(store: dict[str, bytes]) -> MagicMock:
    """In-memory stand-in for the boto3 MinIO client."""
    client = MagicMock()

    def put_object(**kwargs: object) -> None:
        store[kwargs["Key"]] = kwargs["Body"]  # type: ignore[index]

    def get_object(**kwargs: object) -> dict:
        body = MagicMock()
        body.iter_chunks.return_value = iter([store[kwargs["Key"]]])  # type: ignore[index]
        return {"Body": body, "ContentType": "text/plain"}

    client.put_object.side_effect = put_object
    client.get_object.side_effect = get_object
    return client


async def test_upload_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/files/upload", files={"file": ("test.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 401


async def test_upload_and_download_roundtrip(admin_client: AsyncClient) -> None:
    store: dict[str, bytes] = {}
    with patch("app.routers.files.s3_client", return_value=_fake_s3(store)):
        upload = await admin_client.post(
            "/files/upload", files={"file": ("quote.txt", b"hello world", "text/plain")}
        )
        assert upload.status_code == 200, upload.text
        data = upload.json()
        assert data["key"].startswith(f"tenants/{admin_client.headers['X-Tenant-ID']}/")
        assert data["key"].endswith("quote.txt")
        assert data["url"].startswith("/files/download?key=")

        download = await admin_client.get(data["url"])
        assert download.status_code == 200
        assert download.content == b"hello world"


async def test_download_rejects_other_tenant_keys(admin_client: AsyncClient) -> None:
    store: dict[str, bytes] = {}
    with patch("app.routers.files.s3_client", return_value=_fake_s3(store)):
        response = await admin_client.get("/files/download", params={"key": "tenants/other/x.txt"})
        assert response.status_code == 404
