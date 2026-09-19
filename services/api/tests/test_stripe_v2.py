"""Tests for the Accounts v2 client layer (``app.stripe_client``).

No live Stripe calls: ``_v2_request`` is mocked and asserted on, so these
tests pin the exact request/response mapping verified against the Stripe
sandbox on 2026-09-15 (see the PR description for the sanitized transcript).
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from app import stripe_client


def _v2_account_response(
    *,
    transfers_status: str | None = "restricted",
    payouts_status: str | None = "restricted",
    requirements_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal ``GET /v2/core/accounts/{id}`` response in recipient shape."""
    stripe_balance: dict[str, Any] = {}
    if transfers_status is not None:
        stripe_balance["stripe_transfers"] = {
            "status": transfers_status,
            "status_details": [],
        }
    if payouts_status is not None:
        stripe_balance["payouts"] = {"status": payouts_status, "status_details": []}
    return {
        "id": "acct_v2_test",
        "object": "v2.core.account",
        "applied_configurations": ["recipient"],
        "configuration": {
            "recipient": {
                "applied": True,
                "capabilities": {"stripe_balance": stripe_balance},
            },
        },
        "requirements": {"entries": requirements_entries or [], "summary": {}},
        "livemode": False,
    }


@pytest.mark.asyncio
async def test_create_connected_account_v2_sends_recipient_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the exact v2 create payload: recipient config, express, platform liability,
    plus the known-business-field pre-fill (#188) and the portal-URL business
    website (#222)."""
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    v2_request = AsyncMock(return_value={"id": "acct_v2_new"})
    monkeypatch.setattr("app.stripe_client._v2_request", v2_request)

    result = await stripe_client.create_connected_account_v2(
        email="sparky@example.com",
        display_name="Sparks Electrical",
        tenant_id="tenant-123",
        phone="+447700900123",
        postcode="SK8 3NJ",
        entity_type="individual",
        business_url="https://sparks.mytradeportal.co.uk",
    )

    assert result == {"id": "acct_v2_new"}
    v2_request.assert_awaited_once()
    call = v2_request.await_args
    assert call is not None
    method, path = call.args[:2]
    assert method == "POST"
    assert path == "/core/accounts"
    kwargs = call.kwargs
    assert kwargs["idempotency_key"] == "mtp-connect-tenant-123"
    assert kwargs["json_body"] == {
        "display_name": "Sparks Electrical",
        "contact_email": "sparky@example.com",
        "contact_phone": "+447700900123",
        "identity": {
            "country": "gb",
            "entity_type": "individual",
            "business_details": {
                "registered_name": "Sparks Electrical",
                "address": {"country": "gb", "postal_code": "SK8 3NJ"},
            },
        },
        "dashboard": "express",
        "defaults": {
            "responsibilities": {
                "fees_collector": "application",
                "losses_collector": "application",
            },
            # Business website lives on defaults.profile in Accounts v2
            # (identity.business_details.url was removed in 2025-09-30.clover).
            "profile": {"url": "https://sparks.mytradeportal.co.uk"},
        },
        "configuration": {
            "recipient": {
                "capabilities": {
                    "stripe_balance": {"stripe_transfers": {"requested": True}},
                },
            },
        },
        "metadata": {"tenant_id": "tenant-123"},
        "include": ["configuration.recipient", "requirements"],
    }


@pytest.mark.asyncio
async def test_create_connected_account_v2_omits_email_and_key_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    v2_request = AsyncMock(return_value={"id": "acct_v2_new"})
    monkeypatch.setattr("app.stripe_client._v2_request", v2_request)

    await stripe_client.create_connected_account_v2()

    call = v2_request.await_args
    assert call is not None
    kwargs = call.kwargs
    assert "contact_email" not in kwargs["json_body"]
    assert "contact_phone" not in kwargs["json_body"]
    # No pre-fill known → identity carries only the hard-coded country.
    assert kwargs["json_body"]["identity"] == {"country": "gb"}
    assert "profile" not in kwargs["json_body"]["defaults"]
    assert kwargs["idempotency_key"] is None


@pytest.mark.asyncio
async def test_create_connected_account_v2_503_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "")
    with pytest.raises(stripe_client.PaymentsNotConfiguredError):
        await stripe_client.create_connected_account_v2(tenant_id="t")


@pytest.mark.asyncio
async def test_retrieve_account_requests_v2_includes_and_maps_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    v2_request = AsyncMock(
        return_value=_v2_account_response(
            transfers_status="active",
            payouts_status="active",
        )
    )
    monkeypatch.setattr("app.stripe_client._v2_request", v2_request)

    flags = await stripe_client.retrieve_account("acct_v2_test")

    v2_request.assert_awaited_once()
    call = v2_request.await_args
    assert call is not None
    method, path = call.args[:2]
    assert method == "GET"
    assert path == "/core/accounts/acct_v2_test"
    assert call.kwargs["params"] == [
        ("include", "configuration.recipient"),
        ("include", "requirements"),
    ]
    assert flags == {
        "id": "acct_v2_test",
        "details_submitted": True,
        "charges_enabled": True,
        "payouts_enabled": True,
    }


@pytest.mark.parametrize(
    ("transfers_status", "payouts_status", "awaiting_user", "expected"),
    [
        ("active", "active", False, (True, True, True)),
        ("restricted", "restricted", True, (False, False, False)),
        ("pending", "active", True, (False, True, False)),
        (None, None, False, (False, False, True)),
    ],
)
def test_capability_flags_mapping(
    transfers_status: str | None,
    payouts_status: str | None,
    awaiting_user: bool,
    expected: tuple[bool, bool, bool],
) -> None:
    entries = [{"description": "external_account"}] if awaiting_user else []
    account = _v2_account_response(
        transfers_status=transfers_status,
        payouts_status=payouts_status,
        requirements_entries=entries,
    )
    for entry in entries:
        entry["awaiting_action_from"] = "user"
    flags = stripe_client._capability_flags(account)
    assert flags["charges_enabled"] is expected[0]
    assert flags["payouts_enabled"] is expected[1]
    assert flags["details_submitted"] is expected[2]


@pytest.mark.asyncio
async def test_v2_request_raises_structured_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-2xx v2 responses surface as StripeV2Error with Stripe's error code."""

    class _Response:
        status_code = 400
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "error": {
                    "code": "accounts_v2_access_blocked",
                    "message": "Accounts v2 is not enabled for your merchant.",
                }
            }

    class _Client:
        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def request(self, *args: Any, **kwargs: Any) -> _Response:
            return _Response()

    monkeypatch.setattr("app.config.STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr("app.stripe_client.httpx.AsyncClient", lambda **_: _Client())

    with pytest.raises(stripe_client.StripeV2Error) as exc_info:
        await stripe_client._v2_request("POST", "/core/accounts", json_body={})
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "accounts_v2_access_blocked"
    assert "not enabled" in exc_info.value.message


def test_is_stripe_error_classifies_v2_errors() -> None:
    assert stripe_client.is_stripe_error(stripe_client.StripeV2Error(400, "code", "message"))
    assert not stripe_client.is_stripe_error(RuntimeError("boom"))
