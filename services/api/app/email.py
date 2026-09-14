"""Async email sending helpers.

Prefers Resend (HTTP REST) in production when ``RESEND_API_KEY`` is set;
falls back to SMTP + Mailpit for local development. Callers do not choose
the transport — they only supply the payload.
"""

import base64
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import aiosmtplib as aiosmtplib
import httpx as httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as settings
from app.models import Contact, Customer, Tenant
from app.portal_links import magic_link_url

logger = structlog.get_logger("api.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def resolve_customer_magic_link(
    db: AsyncSession,
    tenant: Tenant | None,
    contact: Contact | None,
    next_path: str,
) -> str | None:
    """Magic portal sign-in link for a document's contact, or ``None``.

    Returns ``None`` when the contact has no active linked ``Customer``
    account — callers then fall back to the view-only document token — and
    when token issuance fails: the email must still go out with the document
    link rather than not at all. ``next_path`` is the portal path the link
    lands on after sign-in (e.g. ``/quotes/{id}``).
    """
    if tenant is None or contact is None:
        return None
    customer = await db.scalar(select(Customer).where(Customer.contact_id == contact.id))
    if customer is None and contact.email:
        customer = await db.scalar(
            select(Customer).where(
                Customer.tenant_id == tenant.id,
                Customer.email == contact.email,
            )
        )
    if customer is None or not customer.is_active:
        return None
    try:
        return await magic_link_url(db, tenant, customer, next_path)
    except Exception as exc:
        logger.warning(
            "magic_link_unavailable",
            tenant_id=str(tenant.id),
            contact_id=str(contact.id),
            error=str(exc)[:200],
        )
        return None


def _resend_from(display_name: str | None = None) -> str:
    """Build the ``From`` header for Resend.

    Branded sends (quotes/invoices) pass the tenant's business name as
    ``display_name`` and go out on ``resend_from_email`` — typically the
    shared quotes@ address — so recipients see ``Sparks & Sons <quotes@…>``
    and replies reach the tenant via ``Reply-To``.

    Transactional sends (password resets, account mail) pass no display name
    and go out on ``resend_no_reply_email`` under the platform name, so
    account security mail never impersonates a tenant and never invites a
    reply. Falls back to ``resend_from_email`` then the SMTP sender when the
    no-reply address is not configured.
    """
    if display_name:
        address = settings.resend_from_email or settings.smtp_from_email
        return formataddr((display_name, address))
    address = (
        settings.resend_no_reply_email or settings.resend_from_email or settings.smtp_from_email
    )
    return formataddr((settings.smtp_from_name, address))


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
    message["From"] = formataddr((from_name or settings.smtp_from_name, settings.smtp_from_email))
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


async def send_event_email(
    *,
    to_email: str | None,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    event: str,
    template: str,
    from_name: str | None = None,
    reply_to: str | None = None,
    attachments: list[tuple[str, str, bytes]] | None = None,
    context: dict[str, Any] | None = None,
) -> bool:
    """Send an event-triggered email with uniform logging. Never raises.

    Wraps :func:`send_email` for customer-facing triggers (quote sent, triage
    question, account created, ...) so no dispatch gap is ever silent:

    * No usable recipient address → warning log (``email_skipped_no_contact_email``)
      with the event/template plus the caller's ``context`` (quote id, customer
      id, ...), and ``False``. Callers must pass identifying context so the
      skipped customer is traceable.
    * Transport/Resend failure → error log (``email_send_failed``) with the
      recipient, template and event, and ``False``.
    * Success → info log (``email_dispatched``) and ``True``.
    """
    log_context = {"email_event": event, "template": template, **(context or {})}
    if not to_email or not to_email.strip():
        logger.warning("email_skipped_no_contact_email", **log_context)
        return False
    try:
        await send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
            from_name=from_name,
            reply_to=reply_to,
        )
    except Exception as exc:
        logger.error(
            "email_send_failed",
            recipient=to_email,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
            **log_context,
        )
        return False
    logger.info("email_dispatched", recipient=to_email, **log_context)
    return True
