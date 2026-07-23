"""Tests for the public /feature-flags endpoint backed by Railway Signals.

These tests deliberately avoid the Postgres-backed ``client`` fixture: the
endpoint is public and touches no database, so a bare ASGI client is enough.
The Railway GraphQL call is mocked at the ``httpx.AsyncClient.post`` layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from app import feature_flags
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_flag_cache() -> Iterator[None]:
    feature_flags.reset_cache()
    yield
    feature_flags.reset_cache()


@pytest.fixture()
def _railway_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "railway_token", "test-project-token")
    monkeypatch.setattr(settings, "railway_project_id", "test-project-id")


@pytest.fixture()
def _railway_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "railway_token", "")
    monkeypatch.setattr(settings, "railway_project_id", "")


def _graphql_payload(flags: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"signals": [{"key": key, "value": value} for key, value in flags.items()]}}


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


async def _get_flags() -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/feature-flags")


@pytest.mark.asyncio
async def test_feature_flags_default_off_when_railway_unconfigured(
    _railway_unconfigured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without RAILWAY_TOKEN/RAILWAY_PROJECT_ID no HTTP call is made and every
    known flag resolves to its default (False)."""

    async def _fail_post(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("httpx must not be called when Railway is unconfigured")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fail_post)

    response = await _get_flags()

    assert response.status_code == 200, response.text
    body = response.json()
    for flag in feature_flags.KNOWN_FLAGS:
        assert body[flag] is False


@pytest.mark.asyncio
async def test_feature_flags_maps_registry_bools(
    _railway_configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bool values from the registry are mapped; absent known flags stay off."""
    captured: dict[str, Any] = {}

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["json"] = kwargs.get("json", {})
        return _FakeResponse(
            _graphql_payload({"voice_ai_insights": True, "some_future_flag": "true"})
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    response = await _get_flags()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["voice_ai_insights"] is True
    assert body["demand_forecasting"] is False
    assert body["external_integrations"] is False
    # Unknown registry flags pass through so the UI can adopt them additively.
    assert body["some_future_flag"] is True

    # The GraphQL call went to Railway with the project token + project owner.
    assert captured["url"] == feature_flags.RAILWAY_GRAPHQL_URL
    assert captured["headers"]["project-access-token"] == "test-project-token"
    assert captured["json"]["variables"] == {"owner": "project:test-project-id"}


@pytest.mark.asyncio
async def test_feature_flags_default_off_when_railway_unreachable(
    _railway_configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed Railway call fails open to defaults — the endpoint never 5xxs."""

    async def _boom_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> None:
        raise httpx.ConnectError("railway unreachable")

    monkeypatch.setattr(httpx.AsyncClient, "post", _boom_post)

    response = await _get_flags()

    assert response.status_code == 200, response.text
    body = response.json()
    assert all(value is False for value in body.values())


@pytest.mark.asyncio
async def test_feature_flags_caches_registry(
    _railway_configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second read within the TTL is served from the in-process cache."""
    calls = 0

    async def _counting_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> _FakeResponse:
        nonlocal calls
        calls += 1
        return _FakeResponse(_graphql_payload({"voice_ai_insights": True}))

    monkeypatch.setattr(httpx.AsyncClient, "post", _counting_post)

    first = await _get_flags()
    second = await _get_flags()

    assert calls == 1
    assert first.json()["voice_ai_insights"] is True
    assert second.json()["voice_ai_insights"] is True
