"""Async email sending helpers."""

from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import aiosmtplib

from app.config import settings


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

    return {"recipient": to_email, "subject": subject}
