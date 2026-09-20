"""Telnyx webhook endpoint (SMS delivery receipts + inbound STOP opt-outs).

Telnyx signs every webhook with Ed25519: the ``telnyx-timestamp`` and
``telnyx-signature-ed25519`` headers authenticate the raw body as an Ed25519
signature (base64) of ``"{timestamp}|{body}"`` against the account's public
key (Mission Control → Keys & Credentials, configured as
``TELNYX_PUBLIC_KEY``). An unconfigured key answers 503 (loud, and Telnyx
replays the event once the key is set); a bad signature answers 401.

Two messaging event families are handled:

* **Delivery receipts** (``message.sent`` / ``message.finalized``) — matched
  back to the appointment-reminder row via ``payload.telnyx_message_id``
  (stamped by ``app.appointment_reminders`` at send time). The status
  transition is recorded on the reminder payload (``delivery_status`` +
  ``delivery_events`` history), and a permanent failure (``sending_failed`` /
  ``delivery_failed``) on a CUSTOMER reminder pages staff once via
  :func:`app.sms_alerts.alert_staff_sms_failure` — the same deduped
  phone-directive-style alert as an email bounce (shared per-day ledger).
* **Inbound messages** (``message.received``) — CTIA keyword handling: STOP
  (and the other standard opt-out keywords, case-insensitive) sets
  ``sms_opt_out`` on every contact we have texted at that number, so the
  appointment-reminder sweep skips SMS for them and falls back to email;
  START/UNSTOP clears the flag again.

Delivery is at-least-once, so every event id (``data.id``) is deduped via the
shared ``processed_webhooks`` ledger (``provider="telnyx"``) before any side
effect runs — the same pattern as the Stripe webhook. Unknown event types and
receipts for messages we never sent (portal test sends, sends from before
this feature) are acked with a 200 no-op so Telnyx stops retrying them.
"""

import base64
import binascii
import json
import time
from typing import Any

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
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
logger = structlog.get_logger("api.telnyx_webhooks")

# Reject events whose telnyx-timestamp is older than this — replay protection
# (Telnyx's own SDK default tolerance is five minutes too).
_TIMESTAMP_TOLERANCE_SECONDS = 300

_HANDLED_EVENT_TYPES = {"message.received", "message.sent", "message.finalized"}

# to[].status values from message.finalized (see Telnyx messaging webhook
# docs). Terminal statuses may not be downgraded by a late interim receipt
# (out-of-order delivery is expected); the permanent-failure subset pages
# staff.
_TERMINAL_STATUSES = {"delivered", "sending_failed", "delivery_failed", "delivery_unconfirmed"}
_PERMANENT_FAILURE_STATUSES = {"sending_failed", "delivery_failed"}

# CTIA-mandated keyword sets, matched case-insensitively on the stripped
# message body. STOPSTART rides along with the opt-ins (some carriers relay
# the legacy double-keyword form).
_OPT_OUT_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
_OPT_IN_KEYWORDS = {"START", "STOPSTART", "UNSTOP", "YES"}

# Cap the free-text Telnyx error detail we log/store so a hostile or runaway
# payload cannot blow up log lines or alert bodies.
_MAX_ERROR_DETAIL_LENGTH = 300


def _verify_telnyx_signature(
    body: bytes,
    *,
    timestamp: str | None,
    signature: str | None,
    public_key_b64: str,
) -> None:
    """Validate the Telnyx Ed25519 signature headers against the raw body.

    Raises ``ValueError`` on any mismatch — the caller maps that to 401.
    """
    if not timestamp or not signature:
        raise ValueError("missing telnyx signature headers")
    try:
        signed_at = int(timestamp)
    except ValueError:
        raise ValueError("invalid telnyx timestamp") from None
    if abs(time.time() - signed_at) > _TIMESTAMP_TOLERANCE_SECONDS:
        raise ValueError("telnyx timestamp outside tolerance")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        given = base64.b64decode(signature)
    except (binascii.Error, ValueError):
        raise ValueError("malformed telnyx signature or public key") from None
    try:
        public_key.verify(given, f"{timestamp}|".encode() + body)
    except InvalidSignature:
        raise ValueError("invalid telnyx signature") from None


async def _mark_event_seen(event_id: str, event_type: str) -> bool:
    """Insert into the dedupe ledger. Returns False if already seen."""
    async with AsyncSession(engine) as session:
        session.add(ProcessedWebhook(provider="telnyx", event_id=event_id, event_type=event_type))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
    return True


def _to_status(payload: dict[str, Any], event_type: str) -> str | None:
    """Recipient delivery status from a receipt payload.

    ``to[].status`` carries the outcome (``delivered``, ``delivery_failed``,
    …); ``message.sent`` events fall back to the bare ``sent`` marker when
    the array is absent.
    """
    to = payload.get("to")
    if isinstance(to, list) and to and isinstance(to[0], dict):
        raw = to[0].get("status")
        if raw:
            return str(raw)
    return "sent" if event_type == "message.sent" else None


def _error_detail(payload: dict[str, Any]) -> str | None:
    """First Telnyx error (``code title``) from a failed receipt, truncated."""
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors or not isinstance(errors[0], dict):
        return None
    first = errors[0]
    code = str(first.get("code") or "").strip()
    title = str(first.get("title") or "").strip()
    detail = f"{code} {title}".strip()
    return detail[:_MAX_ERROR_DETAIL_LENGTH] if detail else None


async def _handle_delivery_receipt(
    event_type: str, payload: dict[str, Any], occurred_at: str
) -> dict[str, str]:
    """Record a delivery status transition on the matching reminder row."""
    message_id = str(payload.get("id") or "")
    receipt_status = _to_status(payload, event_type)
    if not message_id or receipt_status is None:
        logger.info("telnyx_receipt_unusable", event_type=event_type, message_id=message_id or None)
        return {"status": "ignored"}

    async with AsyncSession(engine) as session:
        # The message id — not a tenant — is the lookup key, and the webhook
        # session has no tenant GUC: bypass RLS for this transaction only,
        # then re-scope to the matched row's tenant before writing.
        await bypass_rls_for_transaction(session)
        reminder = await session.scalar(
            select(Reminder).where(
                Reminder.entity_type == "appointment",
                Reminder.channel == "sms",
                Reminder.payload["telnyx_message_id"].astext == message_id,
            )
        )
        if reminder is None:
            # Not one of our appointment-reminder sends (portal test send,
            # pre-feature send) — ack so Telnyx stops retrying.
            logger.info("telnyx_receipt_unmatched", event_type=event_type, message_id=message_id)
            return {"status": "ignored"}

        new_payload = dict(reminder.payload or {})
        history = list(new_payload.get("delivery_events") or [])
        history.append({"status": receipt_status, "event_type": event_type, "at": occurred_at})
        new_payload["delivery_events"] = history
        current = str(new_payload.get("delivery_status") or "")
        # Out-of-order delivery must not downgrade a terminal outcome.
        if not (current in _TERMINAL_STATUSES and receipt_status not in _TERMINAL_STATUSES):
            new_payload["delivery_status"] = receipt_status
        reminder.payload = new_payload
        tenant_id = reminder.tenant_id

        alerted = False
        role = str(new_payload.get("role") or "")
        if receipt_status in _PERMANENT_FAILURE_STATUSES and role == "customer":
            appointment = await session.get(Appointment, reminder.entity_id)
            contact = (
                await session.get(Contact, appointment.contact_id)
                if appointment is not None
                else None
            )
            alerted = await alert_staff_sms_failure(
                session,
                tenant_id=tenant_id,
                contact_id=contact.id if contact is not None else None,
                recipient_phone=str(new_payload.get("to") or "") or None,
                purpose="appointment reminder",
                error_class="delivery failure",
                detail=_error_detail(payload),
            )
        await session.commit()
    logger.info(
        "telnyx_receipt_processed",
        event_type=event_type,
        message_id=message_id,
        delivery_status=receipt_status,
        tenant_id=str(tenant_id),
        alerted=alerted,
    )
    return {"status": "ok"}


async def _set_sms_opt_out(session: AsyncSession, from_number: str, *, opted_out: bool) -> int:
    """Flag every contact we have texted at ``from_number``. Returns the count.

    The number — not a tenant — is the lookup key: appointment-reminder SMS
    rows carry the normalised recipient in ``payload.to``, and CTIA opt-outs
    are per phone number, so every matching contact (any tenant) is flagged.
    Rows for the STAFF role are excluded — an electrician texting STOP must
    not opt their customer out. A contact whose stored number no longer
    normalises to the sender's number is skipped (stale reminder row).
    """
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
                    continue  # already flagged
                preferences["sms_opt_out"] = True
            else:
                if not preferences.get("sms_opt_out"):
                    continue  # nothing to clear
                preferences.pop("sms_opt_out", None)
            contact.reminder_preferences = preferences
            flagged += 1
    return flagged


async def _handle_inbound(payload: dict[str, Any]) -> dict[str, str]:
    """CTIA keyword handling for inbound messages (STOP / START)."""
    raw_from = payload.get("from")
    from_number = normalize_phone(
        raw_from.get("phone_number") if isinstance(raw_from, dict) else None
    )
    keyword = str(payload.get("text") or "").strip().upper()
    if from_number is None or keyword not in _OPT_OUT_KEYWORDS | _OPT_IN_KEYWORDS:
        # Not an opt-out/opt-in keyword (or an un-normalisable sender) —
        # nothing to act on; inbound chat is not a feature.
        logger.info("telnyx_inbound_ignored", from_number=from_number)
        return {"status": "ignored"}
    opted_out = keyword in _OPT_OUT_KEYWORDS
    async with AsyncSession(engine) as session:
        flagged = await _set_sms_opt_out(session, from_number, opted_out=opted_out)
        await session.commit()
    logger.info(
        "telnyx_opt_out_processed" if opted_out else "telnyx_opt_in_processed",
        from_number=from_number,
        keyword=keyword,
        contacts_flagged=flagged,
    )
    return {"status": "ok"}


@router.post("/telnyx")
async def telnyx_webhook(request: Request) -> dict[str, str]:
    """Receive and verify Telnyx messaging webhook events."""
    public_key = settings.telnyx_public_key
    if not public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telnyx_webhook_not_configured",
        )
    body = await request.body()
    try:
        _verify_telnyx_signature(
            body,
            timestamp=request.headers.get("telnyx-timestamp"),
            signature=request.headers.get("telnyx-signature-ed25519"),
            public_key_b64=public_key,
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

    raw_data = event.get("data") if isinstance(event, dict) else None
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    event_type = str(data.get("event_type") or "")
    if event_type not in _HANDLED_EVENT_TYPES:
        logger.info("telnyx_webhook_ignored", event_type=event_type or None)
        return {"status": "ignored"}

    event_id = str(data.get("id") or "")
    if event_id and not await _mark_event_seen(event_id, event_type):
        logger.info("telnyx_webhook_duplicate", event_id=event_id, event_type=event_type)
        return {"status": "duplicate"}

    raw_payload = data.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    occurred_at = str(data.get("occurred_at") or "")
    if event_type == "message.received":
        return await _handle_inbound(payload)
    return await _handle_delivery_receipt(event_type, payload, occurred_at)
