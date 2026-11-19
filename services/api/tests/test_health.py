"""Readiness endpoint status logic tests.

The probes themselves are thin wrappers around live dependencies; these tests
patch the four probe coroutines and assert the aggregated status/code mapping:
hard dependencies (postgres, storage) drive 503, soft ones (qdrant, redis)
only degrade.
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.main import app
from app.routers import health
from httpx import ASGITransport, AsyncClient

_PROBES = ("_postgres_ok", "_storage_ok", "_qdrant_ok", "_redis_ok")


def _patch_probes(monkeypatch: pytest.MonkeyPatch, **states: bool) -> None:
    for name in _PROBES:
        monkeypatch.setattr(
            health, name, AsyncMock(return_value=states[name.strip("_").removesuffix("_ok")])
        )


async def _get_ready() -> tuple[int, dict[str, Any]]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_ready_when_all_probes_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_probes(monkeypatch, postgres=True, storage=True, qdrant=True, redis=True)
    status_code, body = await _get_ready()
    assert status_code == 200
    assert body["status"] == "ready"
    assert body["checks"] == {
        "postgres": "ok",
        "storage": "ok",
        "qdrant": "ok",
        "redis": "ok",
    }


@pytest.mark.asyncio
async def test_not_ready_when_postgres_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_probes(monkeypatch, postgres=False, storage=True, qdrant=True, redis=True)
    status_code, body = await _get_ready()
    assert status_code == 503
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"] == "error"


@pytest.mark.asyncio
async def test_not_ready_when_storage_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_probes(monkeypatch, postgres=True, storage=False, qdrant=True, redis=True)
    status_code, body = await _get_ready()
    assert status_code == 503
    assert body["status"] == "not_ready"
    assert body["checks"]["storage"] == "error"


@pytest.mark.asyncio
async def test_degraded_when_qdrant_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_probes(monkeypatch, postgres=True, storage=True, qdrant=False, redis=True)
    status_code, body = await _get_ready()
    assert status_code == 200
    assert body["status"] == "degraded"
    assert body["checks"]["qdrant"] == "error"


@pytest.mark.asyncio
async def test_degraded_when_redis_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_probes(monkeypatch, postgres=True, storage=True, qdrant=True, redis=False)
    status_code, body = await _get_ready()
    assert status_code == 200
    assert body["status"] == "degraded"
    assert body["checks"]["redis"] == "error"


@pytest.mark.asyncio
async def test_storage_probe_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The storage probe must fail when the read-back bytes differ."""
    written: dict[str, bytes] = {}

    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3:
        def put_object(self, **kwargs: Any) -> None:
            written[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            return {"Body": FakeBody(written[kwargs["Key"]] + b"corrupted")}

        def delete_object(self, **kwargs: Any) -> None:
            written.pop(kwargs["Key"], None)

    monkeypatch.setattr(health, "s3_client", lambda: FakeS3())
    assert await health._storage_ok() is False
    assert written == {}  # probe object is always cleaned up
