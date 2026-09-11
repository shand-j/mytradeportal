"""Tests for file upload/download endpoints (API-proxied; MinIO is private)."""

from unittest.mock import MagicMock, patch

import pytest
from app.config import settings
from app.routers.files import _minio_endpoint_url
from botocore.exceptions import EndpointConnectionError
from httpx import AsyncClient


def _fake_s3(store: dict[str, bytes]) -> MagicMock:
    """In-memory stand-in for the boto3 MinIO client."""
    client = MagicMock()

    def put_object(**kwargs: object) -> None:
        store[kwargs["Key"]] = kwargs["Body"]  # type: ignore[index, assignment]

    def get_object(**kwargs: object) -> dict[str, object]:
        body = MagicMock()
        body.iter_chunks.return_value = iter([store[kwargs["Key"]]])  # type: ignore[index]
        return {"Body": body, "ContentType": "text/plain"}

    client.put_object.side_effect = put_object
    client.get_object.side_effect = get_object
    return client


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/files/upload", files={"file": ("test.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_download_rejects_other_tenant_keys(admin_client: AsyncClient) -> None:
    store: dict[str, bytes] = {}
    with patch("app.routers.files.s3_client", return_value=_fake_s3(store)):
        response = await admin_client.get("/files/download", params={"key": "tenants/other/x.txt"})
        assert response.status_code == 404


def test_endpoint_url_bare_private_host_gets_default_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Railway's private DNS name has no implied port; MinIO serves on 9000."""
    monkeypatch.setattr(settings, "minio_endpoint", "minio.railway.internal")
    monkeypatch.setattr(settings, "minio_use_ssl", False)
    assert _minio_endpoint_url() == "http://minio.railway.internal:9000"


def test_endpoint_url_keeps_explicit_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "minio_endpoint", "minio.railway.internal:9000")
    monkeypatch.setattr(settings, "minio_use_ssl", False)
    assert _minio_endpoint_url() == "http://minio.railway.internal:9000"


def test_endpoint_url_ssl_scheme_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "minio_endpoint", "minio.railway.internal:9000")
    monkeypatch.setattr(settings, "minio_use_ssl", True)
    assert _minio_endpoint_url() == "https://minio.railway.internal:9000"


def test_endpoint_url_full_url_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "minio_endpoint", "http://minio:9000/")
    assert _minio_endpoint_url() == "http://minio:9000"


@pytest.mark.asyncio
async def test_upload_with_railway_private_endpoint_config(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The private-networking config (bare host, no SSL) must reach port 9000."""
    monkeypatch.setattr(settings, "minio_endpoint", "minio.railway.internal")
    monkeypatch.setattr(settings, "minio_use_ssl", False)
    store: dict[str, bytes] = {}
    with patch("app.routers.files.boto3.client", return_value=_fake_s3(store)) as mock_boto:
        upload = await admin_client.post(
            "/files/upload", files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")}
        )
        assert upload.status_code == 200, upload.text
        assert mock_boto.call_args.kwargs["endpoint_url"] == "http://minio.railway.internal:9000"
        assert len(store) == 1


@pytest.mark.asyncio
async def test_upload_returns_503_when_storage_unreachable(admin_client: AsyncClient) -> None:
    """A MinIO connection failure surfaces as 503, not a 500 traceback."""
    failing = MagicMock()
    failing.put_object.side_effect = EndpointConnectionError(
        endpoint_url="http://minio.railway.internal:80"
    )
    with patch("app.routers.files.s3_client", return_value=failing):
        response = await admin_client.post(
            "/files/upload", files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")}
        )
        assert response.status_code == 503
