"""Tests for direct email delivery helpers."""

import base64
from unittest.mock import AsyncMock, Mock, patch

import pytest
from app import email as email_module

pytestmark = pytest.mark.asyncio


class _FakeAsyncClient:
    def __init__(self, response: Mock) -> None:
        self.post = AsyncMock(return_value=response)

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


async def test_send_email_uses_resend_when_api_key_configured() -> None:
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {"id": "email_123"}
    fake_client = _FakeAsyncClient(response)

    with (
        patch.object(email_module.settings, "resend_api_key", "re_test_key"),
        patch.object(email_module.settings, "resend_api_base_url", "https://api.resend.com"),
        patch("app.email.httpx.AsyncClient", return_value=fake_client) as mock_client,
    ):
        result = await email_module.send_email(
            to_email="customer@example.com",
            subject="Your quote",
            html_body="<p>Hello</p>",
            text_body="Hello",
            attachments=[("quote.pdf", "application/pdf", b"pdf-data")],
        )

    assert result["provider"] == "resend"
    assert result["id"] == "email_123"
    assert mock_client.call_args.kwargs["base_url"] == "https://api.resend.com"
    auth_header = mock_client.call_args.kwargs["headers"]["Authorization"]
    assert auth_header.startswith("Bearer ")
    assert auth_header.removeprefix("Bearer ") == "re_test_key"

    payload = fake_client.post.call_args.kwargs["json"]
    assert payload["from"] == "My Trade Portal <quotes@mytradeportal.local>"
    assert payload["to"] == ["customer@example.com"]
    assert payload["subject"] == "Your quote"
    assert payload["html"] == "<p>Hello</p>"
    assert payload["text"] == "Hello"
    assert payload["attachments"] == [
        {
            "filename": "quote.pdf",
            "content": base64.b64encode(b"pdf-data").decode("ascii"),
            "content_type": "application/pdf",
        }
    ]


async def test_send_email_falls_back_to_smtp_without_resend_key() -> None:
    with (
        patch.object(email_module.settings, "resend_api_key", ""),
        patch.object(email_module.settings, "smtp_host", "mailpit"),
        patch.object(email_module.settings, "smtp_port", 1025),
        patch.object(email_module.settings, "smtp_use_tls", False),
        patch.object(email_module.settings, "smtp_username", ""),
        patch.object(email_module.settings, "smtp_password", ""),
        patch("app.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send,
    ):
        result = await email_module.send_email(
            to_email="customer@example.com",
            subject="Your invoice",
            html_body="<p>Hello</p>",
            text_body="Hello",
        )

    assert result["provider"] == "smtp"
    assert mock_send.await_count == 1
    message = mock_send.call_args.args[0]
    assert message["To"] == "customer@example.com"
    assert message["Subject"] == "Your invoice"
    assert mock_send.call_args.kwargs == {"hostname": "mailpit", "port": 1025}
