"""Async email sending helpers.

Prefers Resend (HTTP REST) in production when ``RESEND_API_KEY`` is set;
falls back to SMTP + Mailpit for local development. Callers do not choose
the transport — they only supply the payload.
"""

import base64
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import aiosmtplib
import httpx
import structlog

from app.config import settings

logger = structlog.get_logger("api.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _resend_from(display_name: str | None = None) -> str:
    """Build the ``From`` header for Resend.

    Prefers ``resend_from_email`` (verified sender in the Resend dashboard),
    falls back to the SMTP config so a single env override still works. When
    ``display_name`` is provided (e.g. the tenant's business name) it is used
    as the friendly name, so recipients see ``Sparks & Sons <notifications@…>``.
    """
    address = settings.resend_from_email or settings.smtp_from_email
    name = display_name or settings.smtp_from_name
    return formataddr((name, address))


async def _send_via_resend(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None,
    attachments: list[tuple[str, str, bytes]] | None,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """POST the message to Resend's REST API."""
    payload: dict[str, Any] = {
        "from": _resend_from(from_name),
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    if reply_to:
        payload["reply_to"] = [reply_to]
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
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
    if response.status_code >= 400:
        logger.error(
            "resend_send_failed",
            status=response.status_code,
            recipient=to_email,
            body=response.text[:500],
        )
        response.raise_for_status()
    data = response.json()
    logger.info("resend_send_ok", recipient=to_email, message_id=data.get("id"))
    return {"recipient": to_email, "subject": subject, "provider_message_id": data.get("id")}


async def _send_via_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None,
    attachments: list[tuple[str, str, bytes]] | None,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """SMTP fallback used by the local Mailpit dev stack."""
    message = EmailMessage()
    message["From"] = formataddr(
        (from_name or settings.smtp_from_name, settings.smtp_from_email)
    )
    message["To"] = to_email
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to
    if text_body:
        message.set_content(text_body, subtype="plain")
        message.add_alternative(html_body, subtype="html")
    else:
        message.set_content(html_body, subtype="html")
    for filename, content_type, data in attachments or []:
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

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
    logger.info("smtp_send_ok", recipient=to_email)
    return {"recipient": to_email, "subject": subject}


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachments: list[tuple[str, str, bytes]] | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Send an email via Resend (preferred) or SMTP (dev fallback).

    Attachments are tuples of ``(filename, content_type, data)``. The
    Resend transport base64-encodes the bytes; the SMTP transport uses
    :class:`~email.message.EmailMessage` MIME parts.

    ``from_name`` overrides the friendly display name on the ``From`` header
    (e.g. tenant business name for white-label sends). ``reply_to`` sets a
    single reply address so recipients replying land with the tenant, not the
    shared platform inbox.
    """
    if settings.resend_api_key:
        return await _send_via_resend(
            to_email, subject, html_body, text_body, attachments, from_name, reply_to
        )
    return await _send_via_smtp(
        to_email, subject, html_body, text_body, attachments, from_name, reply_to
    )
