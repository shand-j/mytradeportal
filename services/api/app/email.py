"""Async email sending helpers."""

import base64
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import aiosmtplib
import httpx

from app.config import settings


def _build_message(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> EmailMessage:
    """Build an email message for SMTP delivery."""
    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = to_email
    message["Subject"] = subject

    if text_body:
        message.set_content(text_body, subtype="plain")
        message.add_alternative(html_body, subtype="html")
    else:
        message.set_content(html_body, subtype="html")

    for filename, content_type, data in attachments or []:
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )

    return message


async def _send_via_resend(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> dict[str, Any]:
    """Send an email through the Resend API."""
    payload: dict[str, Any] = {
        "from": formataddr((settings.smtp_from_name, settings.smtp_from_email)),
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body
    if attachments:
        payload["attachments"] = [
            {
                "filename": filename,
                "content": base64.b64encode(data).decode("ascii"),
                "content_type": content_type,
            }
            for filename, content_type, data in attachments
        ]

    async with httpx.AsyncClient(
        base_url=settings.resend_api_base_url,
        headers={
            "Authorization": "Bearer " + settings.resend_api_key,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    ) as client:
        response = await client.post("/emails", json=payload)
        response.raise_for_status()

    result = response.json()
    return {
        "recipient": to_email,
        "subject": subject,
        "provider": "resend",
        "id": result.get("id"),
    }


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> dict[str, Any]:
    """Send an email with optional HTML/text bodies and attachments.

    Attachments are tuples of (filename, content_type, data).
    """
    if settings.resend_api_key:
        return await _send_via_resend(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
        )

    message = _build_message(
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        attachments=attachments,
    )

    client_kwargs: dict[str, Any] = {
        "hostname": settings.smtp_host,
        "port": settings.smtp_port,
    }
    if settings.smtp_use_tls:
        client_kwargs["use_tls"] = True
    if settings.smtp_username:
        client_kwargs["username"] = settings.smtp_username
        client_kwargs["password"] = settings.smtp_password

    await aiosmtplib.send(message, **client_kwargs)

    return {"recipient": to_email, "subject": subject, "provider": "smtp"}
