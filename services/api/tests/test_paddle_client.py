"""Unit tests for the Paddle customer binding used by checkout."""

from typing import Any

import httpx
import pytest
from app import paddle_client
from app.logging import configure_logging

# Route structlog through stdlib so caplog can assert the structured fields of
# paddle_api_error events (the app only configures logging in its lifespan,
# which the test transport never enters). Must run before any test executes:
# logger proxies cache their factory on first use, which happens at import.
configure_logging("INFO")


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

    async def patch(self, url: str, json: Any = None) -> _FakeResponse:
        self.requests.append(("PATCH", json))
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


async def test_subscription_transaction_sends_single_flat_unit(
    fake_client: _FakeAsyncClient,
) -> None:
    """create_subscription_transaction always sends one unit of the tier price
    (flat subscription — no per-seat quantity)."""
    fake_client.queue.append(
        _FakeResponse(200, {"data": {"id": "txn_1", "checkout": {"url": "https://pay.x/1"}}})
    )

    result = await paddle_client.create_subscription_transaction("pri_x", "tenant", "pro")

    assert result == {"transaction_id": "txn_1", "checkout_url": "https://pay.x/1"}
    _, payload = fake_client.requests[0]
    assert payload["items"] == [{"price_id": "pri_x", "quantity": 1}]


async def test_update_subscription_sends_prorated_immediately(
    fake_client: _FakeAsyncClient,
) -> None:
    """A plan change PATCHes the subscription with a single-item replace and
    proration billed immediately (flat pricing: no seats, no quantity beyond
    the one unit of the tier price)."""
    fake_client.queue.append(_FakeResponse(200, {"data": {"id": "sub_1", "status": "active"}}))

    result = await paddle_client.update_subscription("sub_1", "pri_pro_month")

    assert result == {"id": "sub_1", "status": "active"}
    assert fake_client.urls == ["/subscriptions/sub_1"]
    method, payload = fake_client.requests[0]
    assert method == "PATCH"
    # Exact contract with Paddle: full item replacement + immediate proration.
    assert payload == {
        "items": [{"price_id": "pri_pro_month", "quantity": 1}],
        "proration_billing_mode": "prorated_immediately",
    }


async def test_update_subscription_raises_without_api_key(
    fake_client: _FakeAsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.paddle_client.settings.paddle_api_key", "")

    with pytest.raises(RuntimeError, match="not configured"):
        await paddle_client.update_subscription("sub_1", "pri_pro_month")

    assert fake_client.requests == []


async def test_get_price_returns_trial_configuration(fake_client: _FakeAsyncClient) -> None:
    fake_client.queue.append(
        _FakeResponse(
            200, {"data": {"id": "pri_x", "trial_period": {"requires_payment_method": False}}}
        )
    )

    price = await paddle_client.get_price("pri_x")

    assert price["trial_period"]["requires_payment_method"] is False
    assert fake_client.urls == ["/prices/pri_x"]


async def test_create_customer_address_sends_country_and_postcode(
    fake_client: _FakeAsyncClient,
) -> None:
    fake_client.queue.append(_FakeResponse(200, {"data": {"id": "add_1"}}))

    address_id = await paddle_client.create_customer_address(
        "ctm_1", country_code="GB", postal_code="SW1A 1AA"
    )

    assert address_id == "add_1"
    assert fake_client.urls == ["/customers/ctm_1/addresses"]
    _, payload = fake_client.requests[0]
    assert payload == {"country_code": "GB", "postal_code": "SW1A 1AA"}


async def test_cardless_trial_transaction_is_billed_and_bound(
    fake_client: _FakeAsyncClient,
) -> None:
    """A cardless-trial subscription is created server-side: the transaction is
    sent with status "billed" (Paddle auto-completes it and creates the
    trialing subscription), bound to a customer AND address, and carries our
    custom_data so webhook events can key onto the tenant."""
    fake_client.queue.append(_FakeResponse(200, {"data": {"id": "txn_trial"}}))

    transaction_id = await paddle_client.create_cardless_trial_transaction(
        price_id="pri_trial",
        tenant_id="tenant-1",
        plan_key="pro",
        customer_id="ctm_1",
        address_id="add_1",
    )

    assert transaction_id == "txn_trial"
    assert fake_client.urls == ["/transactions"]
    _, payload = fake_client.requests[0]
    assert payload == {
        "items": [{"price_id": "pri_trial", "quantity": 1}],
        "customer_id": "ctm_1",
        "address_id": "add_1",
        "collection_mode": "automatic",
        "status": "billed",
        "custom_data": {"tenant_id": "tenant-1", "plan_key": "pro"},
    }


async def test_await_transaction_subscription_id_polls_until_paddle_links(
    fake_client: _FakeAsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paddle attaches the subscription asynchronously; the helper polls."""

    async def _no_sleep(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.paddle_client.asyncio.sleep", _no_sleep)
    fake_client.queue.extend(
        [
            _FakeResponse(200, {"data": {"id": "txn_trial", "subscription_id": None}}),
            _FakeResponse(200, {"data": {"id": "txn_trial", "subscription_id": "sub_1"}}),
        ]
    )

    subscription_id = await paddle_client.await_transaction_subscription_id("txn_trial")

    assert subscription_id == "sub_1"
    assert fake_client.urls == ["/transactions/txn_trial", "/transactions/txn_trial"]


async def test_await_transaction_subscription_id_raises_when_never_linked(
    fake_client: _FakeAsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_sleep(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.paddle_client.asyncio.sleep", _no_sleep)
    fake_client.queue.extend(
        [_FakeResponse(200, {"data": {"id": "txn_trial", "subscription_id": None}})] * 2
    )

    with pytest.raises(RuntimeError, match="did not attach a subscription"):
        await paddle_client.await_transaction_subscription_id("txn_trial", attempts=2)


async def test_payment_method_update_transaction_returns_checkout_contract(
    fake_client: _FakeAsyncClient,
) -> None:
    """The cardless-trial conversion checkout is a GET on the subscription's
    update-payment-method-transaction endpoint; the return contract matches a
    standard checkout so the checkout page can open it unchanged."""
    fake_client.queue.append(
        _FakeResponse(
            200,
            {
                "data": {
                    "id": "txn_pm_update",
                    "origin": "subscription_payment_method_change",
                    "subscription_id": "sub_1",
                    "checkout": {"url": "https://pay.x/c?_ptxn=txn_pm_update"},
                }
            },
        )
    )

    result = await paddle_client.get_payment_method_update_transaction("sub_1")

    assert result == {
        "transaction_id": "txn_pm_update",
        "checkout_url": "https://pay.x/c?_ptxn=txn_pm_update",
    }
    assert fake_client.urls == ["/subscriptions/sub_1/update-payment-method-transaction"]


async def test_update_subscription_custom_data_patches_without_items(
    fake_client: _FakeAsyncClient,
) -> None:
    fake_client.queue.append(_FakeResponse(200, {"data": {"id": "sub_1"}}))

    await paddle_client.update_subscription_custom_data(
        "sub_1", {"tenant_id": "t-1", "plan_key": "pro"}
    )

    method, payload = fake_client.requests[0]
    assert method == "PATCH"
    assert fake_client.urls == ["/subscriptions/sub_1"]
    assert payload == {"custom_data": {"tenant_id": "t-1", "plan_key": "pro"}}


async def test_http_status_error_logs_paddle_response_body(
    fake_client: _FakeAsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Intermittent 502s on /billing/checkout were undiagnosable because the
    Paddle response body never reached the logs. The client must log status +
    body (Paddle error JSON carries no PII) before re-raising."""
    import logging

    fake_client.queue.append(
        _FakeResponse(400, {"error": {"code": "cardless_trial_not_supported", "detail": "nope"}})
    )

    with (
        caplog.at_level(logging.ERROR, logger="api.paddle_client"),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await paddle_client.create_subscription_transaction("pri_x", "t", "pro")

    # structlog hands the event dict to stdlib as the record message (the JSON
    # rendering happens on the root handler), so assert on the captured text.
    errors = [r for r in caplog.records if r.name == "api.paddle_client"]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "paddle_api_error" in message
    assert "create_subscription_transaction" in message
    assert "cardless_trial_not_supported" in message
