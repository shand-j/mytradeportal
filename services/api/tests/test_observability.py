"""Tests for request IDs, structured access logging, and the readiness probe."""

import uuid

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


async def test_request_id_generated_when_absent() -> None:
    """Every response carries an X-Request-ID; a fresh UUID4 when not provided."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id
    # Must be a parseable UUID when generated server-side.
    uuid.UUID(request_id)


async def test_request_id_propagated_when_present() -> None:
    """A caller-supplied X-Request-ID is echoed back unchanged."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "req-abc-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-abc-123"


async def test_readiness_reports_dependencies(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/ready returns 200 with Postgres + storage healthy; soft deps are reported either way."""
    # The local test stack has no object-storage container; simulate a healthy
    # storage probe here (the real round-trip is covered in test_health.py).
    monkeypatch.setattr("app.routers.health._storage_ok", lambda: _true())
    response = await client.get("/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["storage"] == "ok"
    assert body["checks"]["qdrant"] in {"ok", "error"}
    assert body["checks"]["redis"] in {"ok", "error"}
    degraded = any(body["checks"][dep] == "error" for dep in ("qdrant", "redis"))
    assert body["status"] == ("degraded" if degraded else "ready")


async def _true() -> bool:
    return True


async def test_readiness_503_when_db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Postgres failure must fail the readiness probe with 503."""

    class _BrokenEngine:
        def connect(self) -> None:
            raise ConnectionError("simulated outage")

    monkeypatch.setattr("app.routers.health.engine", _BrokenEngine())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"] == "error"
