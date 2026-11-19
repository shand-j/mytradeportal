"""SMS dispatch via the Telnyx Messaging API.

Used by the appointment-reminder sweep to text customers and the assigned
electrician before a booked visit. Mirrors the fail-open contract of
:func:`app.email.send_event_email`: :func:`send_sms` NEVER raises — transport
errors and provider rejections are logged and reported as ``None`` so a flaky
Telnyx can never hold up the reminder sweep. Callers fall back to email/push
when ``None`` comes back.

Phone numbers are free text in the CRM (``Contact.phone`` / ``User.phone``,
no validation anywhere), so every send goes through :func:`normalize_phone`
to get a UK-aware E.164 number; un-normalisable numbers are skipped by the
caller (customer → email fallback, staff → push only).

Sender identity: the tenant's business name is preferred, sent as a Telnyx
alphanumeric sender ID (see :func:`normalize_sender`); it falls back to the
configured ``TELNYX_FROM_NUMBER`` / messaging profile. Cost model note: the
fair-use guardrail assumes exactly ONE SMS segment per reminder, so callers
must keep bodies within :func:`sms_segment_limit` — :func:`fit_single_segment`
truncates to a word boundary when needed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.config import settings

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger("api.sms")

TELNYX_MESSAGES_ENDPOINT = "https://api.telnyx.com/v2/messages"

_STRIP_CHARS = re.compile(r"[\s\-\.\(\)]")
_SENDER_STRIP = re.compile(r"[^A-Z0-9]")

# GSM 03.38 basic character table + the extension table (escaped) chars.
# Extension chars (e.g. £ ^ { } [ ] ~ | €) still encode as GSM-7, so they
# keep the 160-char segment budget; any character outside this set forces
# UCS-2 and the 70-char limit.
_GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?¡"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
    "abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_EXTENSION = "^{}\\[~]|€"
GSM7_CHARSET: frozenset[str] = frozenset(_GSM7_BASIC + _GSM7_EXTENSION)


def sms_segment_limit(text: str) -> int:
    """Max characters of ``text`` that fit one SMS segment.

    160 for GSM-7-encodable text, 70 when any character needs UCS-2.
    Concatenated multi-segment messages are never acceptable here — the
    fair-use cost model assumes one segment per reminder.
    """
    return 160 if all(c in GSM7_CHARSET for c in text) else 70


def fit_single_segment(text: str) -> str:
    """Hard-truncate ``text`` to one SMS segment at a word boundary.

    Last resort after the compact body forms have been tried: cut at the
    last word boundary that fits (with an ellipsis), verifying the result
    against the limit for the characters actually used — "…" is not GSM-7,
    so a GSM-7 body fitted with "…" drops to the 70-char UCS-2 budget.
    """
    if len(text) <= sms_segment_limit(text):
        return text
    for ellipsis in ("…", "..."):
        limit = sms_segment_limit(ellipsis)
        body = text[: limit - len(ellipsis)].rstrip()
        space = body.rfind(" ")
        if space > 0:
            body = body[:space].rstrip()
        if not body:
            continue
        fitted = f"{body}{ellipsis}"
        if len(fitted) <= sms_segment_limit(fitted):
            return fitted
    return text[:70]


def normalize_phone(raw: str | None) -> str | None:
    """Normalise a free-text phone number to E.164, UK-aware.

    Accepted inputs (after stripping spaces/dashes/dots/brackets):

    * ``+E.164`` (7-15 digits) → returned as-is.
    * ``00…`` international prefix → ``+…``.
    * ``44…`` without a prefix → ``+44…``.
    * ``0…`` 11-digit UK national format → ``+44`` + the rest.

    Anything else (too short/long, letters, unknown shapes) → ``None``.
    """
    if not raw:
        return None
    digits = _STRIP_CHARS.sub("", raw.strip())
    if not digits:
        return None
    if digits.startswith("+"):
        number = digits[1:]
        if number.isdigit() and 7 <= len(number) <= 15:
            return f"+{number}"
        return None
    if digits.startswith("00"):
        number = digits[2:]
        if number.isdigit() and 7 <= len(number) <= 15:
            return f"+{number}"
        return None
    if not digits.isdigit():
        return None
    if digits.startswith("44") and 7 <= len(digits) <= 15:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+44{digits[1:]}"
    return None


def normalize_sender(name: str | None) -> str | None:
    """Tenant business name → Telnyx alphanumeric sender id.

    Uppercased, everything outside A-Z0-9 stripped, truncated to 11 chars
    (the alphanumeric-sender limit). Returns ``None`` when nothing usable
    remains or the result is all digits — a digit string would be read as a
    phone number, not a sender name.
    """
    if not name:
        return None
    cleaned = _SENDER_STRIP.sub("", name.upper())[:11]
    if not cleaned or not any(c.isalpha() for c in cleaned):
        return None
    return cleaned


def sms_configured() -> bool:
    """True when Telnyx credentials are present enough to attempt a send.

    Requires the API key plus at least one sender identity: a from-number or
    a messaging profile id (the profile can supply the sender pool).
    """
    return bool(
        settings.telnyx_api_key
        and (settings.telnyx_from_number or settings.telnyx_messaging_profile_id)
    )


async def send_sms(
    *,
    to_phone: str,
    text: str,
    tenant_name: str | None = None,
    tenant_id: UUID | None = None,
) -> str | None:
    """Send one SMS via Telnyx. Never raises.

    ``to_phone`` is normalised here; an un-normalisable number is a loud
    warning and ``None`` (the caller then degrades to its fallback channel).
    The sender is resolved per message: the tenant's business name as an
    alphanumeric sender ID when it normalises, else the configured
    ``TELNYX_FROM_NUMBER`` / messaging profile. Returns the Telnyx message
    id on success, ``None`` on any failure.
    """
    to = normalize_phone(to_phone)
    if to is None:
        logger.warning("sms_skipped_unusable_number", raw=to_phone, tenant_id=str(tenant_id or ""))
        return None
    payload: dict[str, Any] = {"to": to, "text": text}
    sender = normalize_sender(tenant_name)
    if sender:
        payload["from"] = sender
    elif settings.telnyx_from_number:
        payload["from"] = settings.telnyx_from_number
    if settings.telnyx_messaging_profile_id:
        payload["messaging_profile_id"] = settings.telnyx_messaging_profile_id
    headers = {
        "Authorization": f"Bearer {settings.telnyx_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(TELNYX_MESSAGES_ENDPOINT, json=payload, headers=headers)
        if response.status_code >= 400:
            logger.error(
                "sms_send_failed",
                status=response.status_code,
                recipient=to,
                tenant_id=str(tenant_id or ""),
                body=response.text[:500],
            )
            return None
        data = response.json()
        message_id = (data.get("data") or {}).get("id")
        logger.info("sms_dispatched", recipient=to, message_id=message_id)
        return message_id
    except Exception as exc:
        logger.error(
            "sms_send_failed",
            recipient=to,
            tenant_id=str(tenant_id or ""),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return None
