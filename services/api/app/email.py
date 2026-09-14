"""Async email sending helpers.

Prefers Resend (HTTP REST) in production when ``RESEND_API_KEY`` is set;
falls back to SMTP + Mailpit for local development. Callers do not choose
the transport — they only supply the payload.
"""

import base64
from collections.abc import Awaitable, Callable
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any
from uuid import UUID

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
    tags: dict[str, str] | None = None,
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
    if tags:
        # Resend tags ride along to the bounce/failed webhooks, letting us
        # match a non-delivery back to the tenant contact it was sent to.
        payload["tags"] = [{"name": name, "value": value} for name, value in tags.items()]
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
    tags: dict[str, str] | None = None,
) -> dict[str, Any]:
    """SMTP fallback used by the local Mailpit dev stack.

    ``tags`` is accepted for signature parity with the Resend transport and
    ignored — SMTP has no webhook channel to correlate bounces through.
    """
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
    tags: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Send an email via Resend (preferred) or SMTP (dev fallback).

    Attachments are tuples of ``(filename, content_type, data)``. The
    Resend transport base64-encodes the bytes; the SMTP transport uses
    :class:`~email.message.EmailMessage` MIME parts.

    ``from_name`` overrides the friendly display name on the ``From`` header
    (e.g. tenant business name for white-label sends). ``reply_to`` sets a
    single reply address so recipients replying land with the tenant, not the
    shared platform inbox. ``tags`` are Resend message tags (no-op on the
    SMTP path) echoed back on bounce/failed webhooks.
    """
    if settings.resend_api_key:
        return await _send_via_resend(
            to_email, subject, html_body, text_body, attachments, from_name, reply_to, tags
        )
    return await _send_via_smtp(
        to_email, subject, html_body, text_body, attachments, from_name, reply_to, tags
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
    tags: dict[str, str] | None = None,
    on_failure: Callable[[str], Awaitable[None]] | None = None,
) -> bool:
    """Send an event-triggered email with uniform logging. Never raises.

    Wraps :func:`send_email` for customer-facing triggers (quote sent, triage
    question, account created, ...) so no dispatch gap is ever silent:

    * No usable recipient address → warning log (``email_skipped_no_contact_email``)
      with the event/template plus the caller's ``context`` (quote id, customer
      id, ...), and ``False``. Callers must pass identifying context so the
      skipped customer is traceable.
    * Transport/Resend failure → error log (``email_send_failed``) with the
      recipient, template and event, and ``False``. When ``on_failure`` is
      given it is awaited with the exception class name (never the raw
      payload) — the hook's own errors are logged and swallowed so the
      never-raises contract holds.
    * Success → info log (``email_dispatched``) and ``True``.

    ``tags`` are passed through to the Resend transport (see
    :func:`send_email`); customer-facing callers should go through
    :func:`send_customer_email`, which sets the ``mtp_*`` correlation tags
    and the staff-alert failure hook for them.
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
            tags=tags,
        )
    except Exception as exc:
        logger.error(
            "email_send_failed",
            recipient=to_email,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
            **log_context,
        )
        if on_failure is not None:
            try:
                await on_failure(type(exc).__name__)
            except Exception as hook_exc:
                logger.error(
                    "email_failure_hook_failed",
                    recipient=to_email,
                    error_type=type(hook_exc).__name__,
                    error=str(hook_exc)[:300],
                    **log_context,
                )
        return False
    logger.info("email_dispatched", recipient=to_email, **log_context)
    return True


async def send_customer_email(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID | None,
    purpose: str,
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
    """Send a customer-facing email with failure alerting. Never raises.

    Wrapper around :func:`send_event_email` for mail addressed to a tenant's
    customer (quote, invoice, reminder, chat, ...):

    * Stamps Resend tags ``mtp_tenant``/``mtp_contact`` so the
      ``/webhooks/resend`` bounce handler can match a non-delivery back to
      the contact it was sent to (no-op on the SMTP fallback path).
    * On transport failure, pages tenant staff via
      :func:`app.email_alerts.alert_staff_email_failure` — one in-app
      notification per (tenant, contact, day) directing them to phone the
      customer instead. Staff-facing mail must keep using
      :func:`send_event_email` directly so a failing staff alert can never
      trigger another alert (no alert loops).

    The caller's session is used for the alert writes and the caller commits
    (same convention as :func:`app.push.notify_staff`).
    """
    from app.email_alerts import alert_staff_email_failure

    tags = {"mtp_tenant": str(tenant_id)}
    if contact_id is not None:
        tags["mtp_contact"] = str(contact_id)

    async def _alert(error_class: str) -> None:
        await alert_staff_email_failure(
            db,
            tenant_id=tenant_id,
            contact_id=contact_id,
            recipient_email=to_email,
            purpose=purpose,
            error_class=error_class,
            source="send",
        )

    return await send_event_email(
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        event=event,
        template=template,
        from_name=from_name,
        reply_to=reply_to,
        attachments=attachments,
        context=context,
        tags=tags,
        on_failure=_alert,
    )
