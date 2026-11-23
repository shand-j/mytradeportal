"""The SMS Works delivery-report and inbound-message webhooks.

The provider posts one flat JSON object. Delivery reports carry ``messageid``
and ``status``; inbound replies use ``messagetype="incoming"``. Optional HTTP
Basic credentials are validated when configured. Events are deduplicated by
``messageid`` and matched to appointment reminders by ``smsworks_message_id``.
"""

import base64
import binascii
import hmac
import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine
from app.models import Appointment, Contact, ProcessedWebhook, Reminder
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.sms import normalize_phone
from app.sms_alerts import alert_staff_sms_failure

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = structlog.get_logger("api.smsworks_webhooks")

_STATUS_MAP = {
    "REJECTED": "delivery_failed",
    "EXPIRED": "sending_failed",
    "UNDELIVERED": "delivery_unconfirmed",
}
_TERMINAL_STATUSES = {"delivered", "sending_failed", "delivery_failed", "delivery_unconfirmed"}
_PERMANENT_FAILURE_STATUSES = {"sending_failed", "delivery_failed"}
_OPT_OUT_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
_OPT_IN_KEYWORDS = {"START", "STOPSTART", "UNSTOP", "YES"}
_MAX_ERROR_DETAIL_LENGTH = 300


def _verify_basic_auth(header: str | None) -> None:
    username = settings.smsworks_webhook_username
    password = settings.smsworks_webhook_password
    if not username and not password:
        return
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="smsworks_webhook_not_configured",
        )
    expected = f"{username}:{password}"
    if not header or not header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook credentials"
        )
    try:
        given = base64.b64decode(header.removeprefix("Basic ")).decode()
    except (binascii.Error, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook credentials"
        ) from None
    if not hmac.compare_digest(given, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook credentials"
        )


def _error_detail(event: dict[str, Any]) -> str | None:
    reason = event.get("failurereason")
    if not isinstance(reason, dict):
        return None
    code = str(reason.get("code") or "").strip()
    details = str(reason.get("details") or "").strip()
    detail = f"{code} {details}".strip()
    return detail[:_MAX_ERROR_DETAIL_LENGTH] if detail else None


async def _handle_delivery_report(
    session: AsyncSession,
    event: dict[str, Any],
) -> dict[str, str]:
    message_id = str(event.get("messageid") or "")
    raw_status = str(event.get("status") or "").upper()
    receipt_status = _STATUS_MAP.get(raw_status, raw_status.lower())
    if not message_id or not receipt_status:
        logger.info("smsworks_receipt_unusable", message_id=message_id or None)
        return {"status": "ignored"}

    await bypass_rls_for_transaction(session)
    reminder = await session.scalar(
        select(Reminder).where(
            Reminder.entity_type == "appointment",
            Reminder.channel == "sms",
            Reminder.payload["smsworks_message_id"].astext == message_id,
        )
    )
    if reminder is None:
        logger.info("smsworks_receipt_unmatched", message_id=message_id)
        return {"status": "ignored"}

    new_payload = dict(reminder.payload or {})
    history = list(new_payload.get("delivery_events") or [])
    occurred_at = str(event.get("modified") or event.get("created") or "")
    history.append({"status": receipt_status, "event_type": "delivery_report", "at": occurred_at})
    new_payload["delivery_events"] = history
    current = str(new_payload.get("delivery_status") or "")
    if not (current in _TERMINAL_STATUSES and receipt_status not in _TERMINAL_STATUSES):
        new_payload["delivery_status"] = receipt_status
    reminder.payload = new_payload
    tenant_id = reminder.tenant_id

    alerted = False
    role = str(new_payload.get("role") or "")
    if receipt_status in _PERMANENT_FAILURE_STATUSES and role == "customer":
        appointment = await session.get(Appointment, reminder.entity_id)
        contact = (
            await session.get(Contact, appointment.contact_id) if appointment is not None else None
        )
        alerted = await alert_staff_sms_failure(
            session,
            tenant_id=tenant_id,
            contact_id=contact.id if contact is not None else None,
            recipient_phone=str(new_payload.get("to") or "") or None,
            purpose="appointment reminder",
            error_class="delivery failure",
            detail=_error_detail(event),
        )
    logger.info(
        "smsworks_receipt_processed",
        message_id=message_id,
        delivery_status=receipt_status,
        tenant_id=str(tenant_id),
        alerted=alerted,
    )
    return {"status": "ok"}


async def _set_sms_opt_out(session: AsyncSession, from_number: str, *, opted_out: bool) -> int:
    await bypass_rls_for_transaction(session)
    rows = (
        (
            await session.execute(
                select(Reminder).where(
                    Reminder.entity_type == "appointment",
                    Reminder.channel == "sms",
                    Reminder.payload["role"].astext == "customer",
                    Reminder.payload["to"].astext == from_number,
                )
            )
        )
        .scalars()
        .all()
    )
    pairs = {(row.tenant_id, row.entity_id) for row in rows}
    flagged = 0
    for tenant_id in {pair[0] for pair in pairs}:
        await set_tenant_in_session(session, tenant_id)
        for pair_tenant, appointment_id in pairs:
            if pair_tenant != tenant_id:
                continue
            appointment = await session.get(Appointment, appointment_id)
            if appointment is None:
                continue
            contact = await session.get(Contact, appointment.contact_id)
            if contact is None or normalize_phone(contact.phone) != from_number:
                continue
            preferences = dict(contact.reminder_preferences or {})
            if opted_out:
                if preferences.get("sms_opt_out"):
                    continue
                preferences["sms_opt_out"] = True
            else:
                if not preferences.get("sms_opt_out"):
                    continue
                preferences.pop("sms_opt_out", None)
            contact.reminder_preferences = preferences
            flagged += 1
    return flagged


async def _handle_inbound(session: AsyncSession, event: dict[str, Any]) -> dict[str, str]:
    from_number = normalize_phone(str(event.get("from") or ""))
    keyword = str(event.get("content") or "").strip().upper()
    if from_number is None or keyword not in _OPT_OUT_KEYWORDS | _OPT_IN_KEYWORDS:
        logger.info("smsworks_inbound_ignored", from_number=from_number)
        return {"status": "ignored"}
    opted_out = keyword in _OPT_OUT_KEYWORDS
    flagged = await _set_sms_opt_out(session, from_number, opted_out=opted_out)
    logger.info(
        "smsworks_opt_out_processed" if opted_out else "smsworks_opt_in_processed",
        from_number=from_number,
        keyword=keyword,
        contacts_flagged=flagged,
    )
    return {"status": "ok"}


@router.post("/smsworks")
async def smsworks_webhook(request: Request) -> dict[str, str]:
    """Receive and verify SMS Works delivery reports and inbound replies."""
    _verify_basic_auth(request.headers.get("authorization"))
    body = await request.body()
    try:
        event = json.loads(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body"
        ) from exc
    if not isinstance(event, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    message_id = str(event.get("messageid") or "")
    async with AsyncSession(engine) as session:
        if message_id:
            event_key = f"{message_id}:{event.get('status') or event.get('messagetype') or ''}"
            session.add(ProcessedWebhook(provider="smsworks", event_id=event_key, event_type="sms"))
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                logger.info("smsworks_webhook_duplicate", event_key=event_key)
                return {"status": "duplicate"}

        if str(event.get("messagetype") or "").lower() == "incoming":
            result = await _handle_inbound(session, event)
        else:
            result = await _handle_delivery_report(session, event)
        await session.commit()
        return result
