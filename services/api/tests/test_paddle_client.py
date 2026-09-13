"""Unit tests for the Paddle customer binding used by checkout."""

from typing import Any

import httpx
import pytest
from app import paddle_client


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "https://x"),
                response=None,  # type: ignore[arg-type]
            )


class _FakeAsyncClient:
    """Scripted httpx.AsyncClient stand-in; pops one queued response per call."""

    def __init__(self) -> None:
        self.queue: list[_FakeResponse] = []
        self.requests: list[tuple[str, Any]] = []
        self.urls: list[str] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, params: Any = None) -> _FakeResponse:
        self.requests.append(("GET", params))
        self.urls.append(url)
        return self.queue.pop(0)

    async def post(self, url: str, json: Any = None) -> _FakeResponse:
        self.requests.append(("POST", json))
        self.urls.append(url)
        return self.queue.pop(0)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeAsyncClient:
    client = _FakeAsyncClient()
    monkeypatch.setattr("app.paddle_client.settings.paddle_api_key", "test-api-key")
    monkeypatch.setattr("app.paddle_client.settings.paddle_sandbox", True)
    monkeypatch.setattr("app.paddle_client.httpx.AsyncClient", lambda *a, **k: client)
    return client


async def test_returns_existing_customer_without_creating(fake_client: _FakeAsyncClient) -> None:
    fake_client.queue.append(_FakeResponse(200, {"data": [{"id": "ctm_existing"}]}))

    customer_id = await paddle_client.get_or_create_customer("a@b.co", name="A")

    assert customer_id == "ctm_existing"
    assert [method for method, _ in fake_client.requests] == ["GET"]


async def test_creates_customer_when_none_found(fake_client: _FakeAsyncClient) -> None:
    fake_client.queue.extend(
        [
            _FakeResponse(200, {"data": []}),
            _FakeResponse(201, {"data": {"id": "ctm_new"}}),
        ]
    )

    customer_id = await paddle_client.get_or_create_customer("a@b.co", name="A")

    assert customer_id == "ctm_new"
    assert fake_client.requests[0] == ("GET", {"email": "a@b.co"})
    assert fake_client.requests[1] == ("POST", {"email": "a@b.co", "name": "A"})


async def test_reconciles_create_race_with_second_lookup(fake_client: _FakeAsyncClient) -> None:
    fake_client.queue.extend(
        [
            _FakeResponse(200, {"data": []}),
            _FakeResponse(409, {"error": {"code": "customer_already_exists"}}),
            _FakeResponse(200, {"data": [{"id": "ctm_race"}]}),
        ]
    )

    customer_id = await paddle_client.get_or_create_customer("a@b.co")

    assert customer_id == "ctm_race"
    assert [method for method, _ in fake_client.requests] == ["GET", "POST", "GET"]


async def test_raises_when_create_fails_and_no_customer_appears(
    fake_client: _FakeAsyncClient,
) -> None:
    fake_client.queue.extend(
        [
            _FakeResponse(200, {"data": []}),
            _FakeResponse(500, {"error": {"code": "internal"}}),
            _FakeResponse(200, {"data": []}),
        ]
    )

    with pytest.raises(httpx.HTTPStatusError):
        await paddle_client.get_or_create_customer("a@b.co")


async def test_subscription_transaction_defaults_to_single_seat(
    fake_client: _FakeAsyncClient,
) -> None:
    """create_subscription_transaction keeps quantity=1 for fixed-seat plans."""
    fake_client.queue.append(
        _FakeResponse(200, {"data": {"id": "txn_1", "checkout": {"url": "https://pay.x/1"}}})
    )

    result = await paddle_client.create_subscription_transaction("pri_x", "tenant", "pro")

    assert result == {"transaction_id": "txn_1", "checkout_url": "https://pay.x/1"}
    _, payload = fake_client.requests[0]
    assert payload["items"] == [{"price_id": "pri_x", "quantity": 1}]


async def test_subscription_transaction_passes_seat_quantity(
    fake_client: _FakeAsyncClient,
) -> None:
    """Team checkouts send the seat count as the item quantity."""
    fake_client.queue.append(
        _FakeResponse(200, {"data": {"id": "txn_2", "checkout": {"url": "https://pay.x/2"}}})
    )

    await paddle_client.create_subscription_transaction(
        "pri_team_month", "tenant", "team", quantity=5
    )

    _, payload = fake_client.requests[0]
    assert payload["items"] == [{"price_id": "pri_team_month", "quantity": 5}]


async def test_subscription_transaction_rejects_zero_quantity(
    fake_client: _FakeAsyncClient,
) -> None:
    with pytest.raises(ValueError, match="quantity"):
        await paddle_client.create_subscription_transaction("pri_x", "tenant", "pro", quantity=0)
