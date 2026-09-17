"""Tests for the ops alerting module (Slack + email dispatch guards)."""

import httpx
import pytest
from app import alerting
from app.alerting import send_alert, send_slack_alert


@pytest.mark.asyncio
async def test_slack_alert_skipped_without_webhook() -> None:
    assert await send_slack_alert("hello", webhook_url="") is False


@pytest.mark.asyncio
async def test_send_alert_no_channels_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(alerting, "ALERT_EMAIL_TO", "")
    monkeypatch.setattr(alerting, "SLACK_ALERT_WEBHOOK_URL", "")
    assert await send_alert("subject", "body") == {}


@pytest.mark.asyncio
async def test_send_alert_email_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_send_event_email(**kwargs: object) -> bool:
        captured["to_email"] = str(kwargs.get("to_email"))
        captured["subject"] = str(kwargs.get("subject"))
        return True

    monkeypatch.setattr(alerting, "ALERT_EMAIL_TO", "ops@example.com")
    monkeypatch.setattr(alerting, "SLACK_ALERT_WEBHOOK_URL", "")
    monkeypatch.setattr(alerting, "send_event_email", fake_send_event_email)

    results = await send_alert("AI spend 80% of monthly budget", "details")
    assert results == {"email": True}
    assert captured["to_email"] == "ops@example.com"
    assert captured["subject"] == "AI spend 80% of monthly budget"


@pytest.mark.asyncio
async def test_slack_alert_never_raises_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        status_code = 500
        text = "server error"

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, json: dict[str, str]) -> _Response:
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    assert await send_slack_alert("boom", webhook_url="https://hooks.slack.com/x") is False


@pytest.mark.asyncio
async def test_fetch_usd_gbp_rate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        status_code = 200

        def json(self) -> dict:
            return {"result": "success", "rates": {"GBP": 0.7449}}

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> _Response:
            return _Response()

    monkeypatch.setattr(alerting.httpx, "AsyncClient", _Client)
    assert await alerting.fetch_usd_gbp_rate() == pytest.approx(0.7449)


@pytest.mark.asyncio
async def test_fetch_usd_gbp_rate_provider_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        status_code = 200

        def json(self) -> dict:
            return {"result": "error", "error-type": "unsupported-code"}

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> _Response:
            return _Response()

    monkeypatch.setattr(alerting.httpx, "AsyncClient", _Client)
    assert await alerting.fetch_usd_gbp_rate() is None
