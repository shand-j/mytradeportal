"""Resend webhook endpoint (bounce/delivery-failure → staff alerts).

Resend delivers webhook events signed with Svix: the ``svix-id``,
``svix-timestamp`` and ``svix-signature`` headers authenticate the raw body
as HMAC-SHA256 of ``"{svix-id}.{svix-timestamp}.{body}"`` keyed by the
endpoint secret (``whsec_…`` — the base64 payload after the prefix).

Only ``email.bounced`` and ``email.failed`` are handled: the ``mtp_tenant`` /
``mtp_contact`` tags stamped by :func:`app.email.send_customer_email` at send
time resolve the recipient back to a tenant contact, and staff get the same
phone-directive alert as a send-time failure (same per-day dedupe, so a
bounce following a send-time failure does not page twice). For bounces the
payload's ``bounce.type`` / ``bounce.reason`` (e.g. ``hard_bounce`` + the
SMTP diagnostic) ride along into the structured log and the staff alert body
— that is what makes deliverability incidents (DKIM/SPF/DMARC, domain
reputation) diagnosable without opening the Resend dashboard. Untagged or
unknown events are acked with a 200 no-op so Resend stops retrying them.

An unconfigured secret answers 503 (loud, and Resend replays the event once
the secret is set); a bad signature answers 401.
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

import app.config as app_config
from app.database import engine
from app.email_alerts import alert_staff_email_failure

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = structlog.get_logger("api.resend_webhooks")

# Reject events whose svix timestamp is older than this — replay protection.
_TIMESTAMP_TOLERANCE_SECONDS = 300

_HANDLED_EVENT_TYPES = {"email.bounced", "email.failed"}


def _verify_svix_signature(
    body: bytes,
    *,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
    secret: str,
) -> None:
    """Validate the Svix signature headers against the raw body.

    Raises ``ValueError`` on any mismatch — the caller maps that to 401.
    """
    if not svix_id or not svix_timestamp or not svix_signature:
        raise ValueError("missing svix headers")
    try:
        timestamp = int(svix_timestamp)
    except ValueError:
        raise ValueError("invalid svix timestamp") from None
    if abs(time.time() - timestamp) > _TIMESTAMP_TOLERANCE_SECONDS:
        raise ValueError("svix timestamp outside tolerance")
    try:
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except binascii.Error:
        raise ValueError("malformed webhook secret") from None
    expected = hmac.new(
        key, f"{svix_id}.{svix_timestamp}.".encode() + body, hashlib.sha256
    ).digest()
    # The header may carry several space-separated "v1,<base64>" signatures
    # (key rotation); any match authenticates.
    for part in svix_signature.split(" "):
        version, _, signature = part.partition(",")
        if version != "v1" or not signature:
            continue
        try:
            given = base64.b64decode(signature)
        except binascii.Error:
            continue
        if hmac.compare_digest(expected, given):
            return
    raise ValueError("invalid svix signature")


def _extract_tags(raw_tags: Any) -> dict[str, str]:
    """Normalise Resend's tags to a plain dict.

    Webhook payloads carry them as an object (``{"mtp_tenant": "…"}``); the
    send API accepts a list of ``{"name", "value"}`` pairs — accept both so a
    shape change on Resend's side does not silently drop matching.
    """
    if isinstance(raw_tags, dict):
        return {str(k): str(v) for k, v in raw_tags.items()}
    if isinstance(raw_tags, list):
        tags: dict[str, str] = {}
        for item in raw_tags:
            if isinstance(item, dict) and "name" in item:
                tags[str(item["name"])] = str(item.get("value") or "")
        return tags
    return {}


def _parse_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _recipient(data: dict[str, Any]) -> str | None:
    to = data.get("to")
    if isinstance(to, list) and to:
        return str(to[0])
    if isinstance(to, str):
        return to
    return None


# Cap the free-text SMTP reason we log/store so a hostile or runaway payload
# cannot blow up log lines or alert bodies.
_MAX_BOUNCE_REASON_LENGTH = 300


def _bounce_details(data: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract ``(bounce.type, bounce.reason)`` from an email.bounced payload.

    Both are free-text/absent on most events; ``None`` either way. The reason
    (raw SMTP diagnostic) is truncated to ``_MAX_BOUNCE_REASON_LENGTH``.
    """
    raw_bounce = data.get("bounce")
    if not isinstance(raw_bounce, dict):
        return None, None
    bounce_type = raw_bounce.get("type")
    bounce_reason = raw_bounce.get("reason")
    return (
        str(bounce_type) if bounce_type else None,
        str(bounce_reason)[:_MAX_BOUNCE_REASON_LENGTH] if bounce_reason else None,
    )


@router.post("/resend")
async def resend_webhook(request: Request) -> dict[str, str]:
    """Receive and verify Resend webhook events."""
    secret = app_config.RESEND_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="resend_webhook_not_configured",
        )
    body = await request.body()
    try:
        _verify_svix_signature(
            body,
            svix_id=request.headers.get("svix-id"),
            svix_timestamp=request.headers.get("svix-timestamp"),
            svix_signature=request.headers.get("svix-signature"),
            secret=secret,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        ) from exc

    try:
        event = json.loads(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body"
        ) from exc

    event_type = str(event.get("type") or "")
    if event_type not in _HANDLED_EVENT_TYPES:
        logger.info("resend_webhook_ignored", event_type=event_type or None)
        return {"status": "ignored"}

    raw_data = event.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    tags = _extract_tags(data.get("tags"))
    tenant_id = _parse_uuid(tags.get("mtp_tenant"))
    contact_id = _parse_uuid(tags.get("mtp_contact"))
    if tenant_id is None or contact_id is None:
        # Not one of our tagged customer emails (platform mail, sends from
        # before tagging) — nothing to match, ack and move on.
        logger.info("resend_webhook_untagged", event_type=event_type)
        return {"status": "ignored"}

    bounce_type, bounce_reason = _bounce_details(data)
    detail = None
    if bounce_type or bounce_reason:
        detail = f"type={bounce_type or 'unknown'}, reason={bounce_reason or 'unknown'}"

    async with AsyncSession(engine) as session:
        alerted = await alert_staff_email_failure(
            session,
            tenant_id=tenant_id,
            contact_id=contact_id,
            recipient_email=_recipient(data),
            purpose="customer",
            error_class="bounce" if event_type == "email.bounced" else "delivery failure",
            source="bounce",
            detail=detail,
        )
        await session.commit()
    logger.info(
        "resend_webhook_processed",
        event_type=event_type,
        tenant_id=str(tenant_id),
        contact_id=str(contact_id),
        bounce_type=bounce_type,
        bounce_reason=bounce_reason,
        alerted=alerted,
    )
    return {"status": "ok"}
