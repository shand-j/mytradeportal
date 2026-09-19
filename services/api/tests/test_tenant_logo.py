"""Tests for tenant logo upload, public serving, and removal.

MinIO is private-network-only, so tests substitute an in-memory boto3
stand-in — the same pattern as tests/test_files.py.
"""

from unittest.mock import MagicMock, patch

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


def _fake_s3(store: dict[str, bytes], content_type: str = "image/png") -> MagicMock:
    """In-memory stand-in for the boto3 MinIO client."""
    client = MagicMock()

    def put_object(**kwargs: object) -> None:
        store[kwargs["Key"]] = kwargs["Body"]  # type: ignore[index, assignment]

    def get_object(**kwargs: object) -> dict[str, object]:
        body = MagicMock()
        body.iter_chunks.return_value = iter([store[kwargs["Key"]]])  # type: ignore[index]
        return {"Body": body, "ContentType": content_type}

    def delete_object(**kwargs: object) -> None:
        store.pop(str(kwargs["Key"]), None)

    client.put_object.side_effect = put_object
    client.get_object.side_effect = get_object
    client.delete_object.side_effect = delete_object
    return client


_PNG = b"\x89PNG\r\n\x1a\n-fake-image-bytes"


@pytest.mark.asyncio
async def test_logo_upload_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/tenants/me/logo", files={"file": ("logo.png", _PNG, "image/png")}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logo_upload_sets_settings_and_serves_publicly(
    admin_client: AsyncClient,
) -> None:
    store: dict[str, bytes] = {}
    with patch("app.routers.files.s3_client", return_value=_fake_s3(store)):
        upload = await admin_client.post(
            "/tenants/me/logo", files={"file": ("logo.png", _PNG, "image/png")}
        )
        assert upload.status_code == 200, upload.text
        data = upload.json()
        assert data["logoUrl"]
        slug = data["slug"]
        logo_url = data["logoUrl"]
        assert logo_url.endswith(f"/businesses/{slug}/logo")
        # Absolute URL: portal/landing pages render it from other origins.
        assert logo_url.startswith("http")

        # Settings round-trip via GET /tenants/me.
        me = await admin_client.get("/tenants/me")
        assert me.json()["logoUrl"] == logo_url

        # Public config exposes the same URL.
        config = await admin_client.get(f"/businesses/{slug}/public-config")
        assert config.status_code == 200
        assert config.json()["logoUrl"] == logo_url

        # The public route streams the stored bytes with no auth at all —
        # a bare client proves no Authorization/X-Tenant-ID header is needed.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
            served = await anon.get(logo_url.replace("http://test", ""))
        assert served.status_code == 200
        assert served.content == _PNG
        assert served.headers["content-type"].startswith("image/png")
        assert "max-age" in served.headers["cache-control"]


@pytest.mark.asyncio
async def test_logo_upload_rejects_wrong_type(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/tenants/me/logo", files={"file": ("logo.gif", b"GIF89a", "image/gif")}
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_logo_upload_rejects_oversize(admin_client: AsyncClient) -> None:
    big = b"\x00" * (2 * 1024 * 1024 + 1)
    response = await admin_client.post(
        "/tenants/me/logo", files={"file": ("logo.png", big, "image/png")}
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_logo_public_route_404s_without_logo(admin_client: AsyncClient) -> None:
    me = await admin_client.get("/tenants/me")
    slug = me.json()["slug"]
    response = await admin_client.get(f"/businesses/{slug}/logo")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_logo_delete_clears_settings_and_public_route(
    admin_client: AsyncClient,
) -> None:
    store: dict[str, bytes] = {}
    fake = _fake_s3(store)
    with patch("app.routers.files.s3_client", return_value=fake):
        upload = await admin_client.post(
            "/tenants/me/logo", files={"file": ("logo.png", _PNG, "image/png")}
        )
        assert upload.status_code == 200, upload.text
        slug = upload.json()["slug"]

        deleted = await admin_client.delete("/tenants/me/logo")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["logoUrl"] is None
        fake.delete_object.assert_called_once()

        assert (await admin_client.get(f"/businesses/{slug}/logo")).status_code == 404
        me = await admin_client.get("/tenants/me")
        assert "logo_url" not in me.json()["settings"]
        assert "logo_key" not in me.json()["settings"]


@pytest.mark.asyncio
async def test_logo_reupload_replaces_object(admin_client: AsyncClient) -> None:
    store: dict[str, bytes] = {}
    fake = _fake_s3(store)
    with patch("app.routers.files.s3_client", return_value=fake):
        first = await admin_client.post(
            "/tenants/me/logo", files={"file": ("logo.png", _PNG, "image/png")}
        )
        assert first.status_code == 200
        second = await admin_client.post(
            "/tenants/me/logo", files={"file": ("logo.jpg", b"jpeg-bytes", "image/jpeg")}
        )
        assert second.status_code == 200
        # The previous object is deleted so storage does not accumulate orphans.
        fake.delete_object.assert_called_once()
        assert len(store) == 1

        slug = second.json()["slug"]
        served = await admin_client.get(f"/businesses/{slug}/logo")
        assert served.status_code == 200
        assert served.content == b"jpeg-bytes"
