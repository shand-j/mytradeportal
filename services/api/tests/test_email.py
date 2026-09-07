"""Tests for the email transport helper (Resend + SMTP fallback)."""

from typing import Any

import httpx
import pytest
from app.email import send_email
from pytest import MonkeyPatch


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)  # type: ignore[arg-type]


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.posts: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(
        self, url: str, json: dict[str, Any], headers: dict[str, str]
    ) -> _FakeResponse:
        self.posts.append((url, json, headers))
        return self._response


@pytest.mark.asyncio
async def test_send_email_uses_resend_when_api_key_is_set(monkeypatch: MonkeyPatch) -> None:
    """A configured Resend key routes email via ``https://api.resend.com``."""
    from app import email as email_module

    monkeypatch.setattr(email_module.settings, "resend_api_key", "re_dev_test")
    monkeypatch.setattr(email_module.settings, "resend_from_email", "noreply@test.local")
    monkeypatch.setattr(email_module.settings, "smtp_from_name", "Test Sender")

    fake_response = _FakeResponse(200, {"id": "resend-msg-123"})
    fake_client = _FakeAsyncClient(fake_response)
    monkeypatch.setattr(email_module.httpx, "AsyncClient", lambda **_: fake_client)

    result = await send_email(
        to_email="user@example.com",
        subject="Hello",
        html_body="<b>Hi</b>",
        text_body="Hi",
    )

    assert result["provider_message_id"] == "resend-msg-123"
    assert len(fake_client.posts) == 1
    url, payload, headers = fake_client.posts[0]
    assert url == email_module.RESEND_ENDPOINT
    assert payload["to"] == ["user@example.com"]
    assert payload["subject"] == "Hello"
    assert payload["html"] == "<b>Hi</b>"
    assert payload["text"] == "Hi"
    assert "Test Sender" in payload["from"]
    assert "noreply@test.local" in payload["from"]
    assert headers["Authorization"] == "Bearer re_dev_test"


@pytest.mark.asyncio
async def test_send_email_encodes_attachments_as_base64(monkeypatch: MonkeyPatch) -> None:
    """Attachments are base64-encoded in the Resend payload."""
    from app import email as email_module

    monkeypatch.setattr(email_module.settings, "resend_api_key", "re_dev_test")

    fake_response = _FakeResponse(200, {"id": "resend-att"})
    fake_client = _FakeAsyncClient(fake_response)
    monkeypatch.setattr(email_module.httpx, "AsyncClient", lambda **_: fake_client)

    await send_email(
        to_email="user@example.com",
        subject="With attachment",
        html_body="<p>see attached</p>",
        attachments=[("hello.txt", "text/plain", b"hello world")],
    )

    _, payload, _ = fake_client.posts[0]
    assert payload["attachments"][0]["filename"] == "hello.txt"
    assert payload["attachments"][0]["content_type"] == "text/plain"
    # base64("hello world") == aGVsbG8gd29ybGQ=
    assert payload["attachments"][0]["content"] == "aGVsbG8gd29ybGQ="


@pytest.mark.asyncio
async def test_send_email_falls_back_to_smtp_without_api_key(
    monkeypatch: MonkeyPatch,
) -> None:
    """No Resend key → SMTP path is used."""
    from app import email as email_module

    monkeypatch.setattr(email_module.settings, "resend_api_key", "")

    sent: list[Any] = []

    async def fake_smtp_send(message: Any, **_: Any) -> None:
        sent.append(message)

    monkeypatch.setattr(email_module.aiosmtplib, "send", fake_smtp_send)

    await send_email(
        to_email="user@example.com",
        subject="Local dev",
        html_body="<p>via Mailpit</p>",
    )
    assert len(sent) == 1
    assert sent[0]["To"] == "user@example.com"


@pytest.mark.asyncio
async def test_send_email_uses_tenant_display_name_and_reply_to(
    monkeypatch: MonkeyPatch,
) -> None:
    """``from_name`` + ``reply_to`` are stamped onto the Resend payload."""
    from app import email as email_module

    monkeypatch.setattr(email_module.settings, "resend_api_key", "re_dev_test")
    monkeypatch.setattr(email_module.settings, "resend_from_email", "noreply@test.local")
    monkeypatch.setattr(email_module.settings, "smtp_from_name", "Platform Default")

    fake_response = _FakeResponse(200, {"id": "resend-tenant"})
    fake_client = _FakeAsyncClient(fake_response)
    monkeypatch.setattr(email_module.httpx, "AsyncClient", lambda **_: fake_client)

    await send_email(
        to_email="homeowner@example.com",
        subject="Your quote",
        html_body="<p>hi</p>",
        from_name="Sparks & Sons",
        reply_to="sam@sparksandsons.co.uk",
    )

    _, payload, _ = fake_client.posts[0]
    assert "Sparks & Sons" in payload["from"] or "Sparks" in payload["from"]
    assert "Platform Default" not in payload["from"]
    assert payload["reply_to"] == ["sam@sparksandsons.co.uk"]


@pytest.mark.asyncio
async def test_send_email_smtp_honours_tenant_display_name_and_reply_to(
    monkeypatch: MonkeyPatch,
) -> None:
    """SMTP fallback stamps ``Reply-To`` and swaps the friendly name."""
    from app import email as email_module

    monkeypatch.setattr(email_module.settings, "resend_api_key", "")
    monkeypatch.setattr(email_module.settings, "smtp_from_name", "Platform Default")
    monkeypatch.setattr(email_module.settings, "smtp_from_email", "noreply@test.local")

    sent: list[Any] = []

    async def fake_smtp_send(message: Any, **_: Any) -> None:
        sent.append(message)

    monkeypatch.setattr(email_module.aiosmtplib, "send", fake_smtp_send)

    await send_email(
        to_email="homeowner@example.com",
        subject="Your quote",
        html_body="<p>hi</p>",
        from_name="Sparks & Sons",
        reply_to="sam@sparksandsons.co.uk",
    )

    assert len(sent) == 1
    assert "Sparks" in sent[0]["From"]
    assert "Platform Default" not in sent[0]["From"]
    assert sent[0]["Reply-To"] == "sam@sparksandsons.co.uk"
