"""Best-effort Expo push delivery.

Fire-and-forget helper for sending push notifications to registered device
tokens via Expo's push API. Every failure is logged and swallowed — push is
a nice-to-have on top of the persistent in-app notifications and must never
break the calling workflow (e.g. background quote generation). Failures are
logged LOUDLY (error level) and per-ticket ``DeviceNotRegistered`` tokens are
cleaned up, so a broken production push path is visible in the logs instead
of failing silently.
"""

import re
from uuid import UUID

import httpx
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("api.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Trailing path segment of a notification link, e.g. "/quotes/{uuid}".
_UUID_TAIL = re.compile(r"/([0-9a-fA-F]{8}-[0-9a-fA-F-]{27,})(?:/)?$")


def _entity_id_from_link(link: str | None) -> str:
    """Extract the entity id (trailing UUID) from a notification link."""
    if not link:
        return ""
    match = _UUID_TAIL.search(link)
    return match.group(1) if match else ""


def _push_data(kind: str, link: str | None) -> dict[str, str]:
    """Deep-link payload: ``type`` + ``id`` for tap routing, ``link`` for the
    mobile clients that already route on the link field."""
    return {"type": kind, "id": _entity_id_from_link(link), "link": link or ""}


async def send_expo_push(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    db: AsyncSession | None = None,
) -> None:
    """POST a batch of push messages to the Expo push API. Never raises.

    The Expo push API answers HTTP 200 even when individual messages fail,
    so the per-ticket statuses in the response body are inspected: every
    error ticket is logged at error level and tokens reported as
    ``DeviceNotRegistered`` are deleted (when ``db`` is provided) so dead
    devices stop being targeted on subsequent sends.
    """
    if not tokens:
        return
    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            # iOS delivers without sound/banner emphasis when these are
            # omitted — the alert fields below make the push user-visible.
            "sound": "default",
            "priority": "high",
            "data": data or {},
        }
        for token in tokens
    ]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(EXPO_PUSH_URL, json=messages)
    except Exception as exc:
        logger.warning(
            "expo_push_failed",
            count=len(tokens),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return

    if response.status_code != 200:
        logger.error(
            "expo_push_http_error",
            count=len(tokens),
            status=response.status_code,
            body=response.text[:500],
        )
        return

    try:
        tickets = response.json().get("data") or []
    except ValueError:
        logger.error("expo_push_bad_response", count=len(tokens), body=response.text[:500])
        return

    dead_tokens: list[str] = []
    failed = 0
    for token, ticket in zip(tokens, tickets, strict=False):
        if not isinstance(ticket, dict) or ticket.get("status") != "error":
            continue
        failed += 1
        details = ticket.get("details") or {}
        error = details.get("error", "unknown")
        logger.error(
            "expo_push_ticket_error",
            token=token,
            error=error,
            message=ticket.get("message"),
        )
        if error == "DeviceNotRegistered":
            dead_tokens.append(token)

    if dead_tokens:
        if db is not None:
            from app.models import PushToken

            await db.execute(delete(PushToken).where(PushToken.token.in_(dead_tokens)))
            logger.info("expo_push_dead_tokens_removed", count=len(dead_tokens))
        else:
            logger.warning("expo_push_dead_tokens", tokens=dead_tokens)

    logger.info("expo_push_sent", count=len(tokens), delivered=len(tokens) - failed)


async def notify_staff(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    kind: str,
    title: str,
    body: str,
    link: str | None,
) -> None:
    """Record a tenant-wide staff notification and fire an Expo push (best-effort).

    Assumes the caller has already scoped the session to ``tenant_id`` via
    :func:`app.rls.set_tenant_in_session` and will commit. ``kind`` is stored
    as ``notifications.type`` and is used by the mobile UI to route taps.
    """
    from app.models import Notification, PushToken

    db.add(
        Notification(
            tenant_id=tenant_id,
            recipient_type="staff",
            recipient_id=None,
            type=kind,
            title=title,
            body=body,
            link=link,
        )
    )
    tokens = (
        (
            await db.execute(
                select(PushToken.token).where(
                    PushToken.tenant_id == tenant_id,
                    PushToken.owner_type == "staff",
                )
            )
        )
        .scalars()
        .all()
    )
    await send_expo_push(list(tokens), title, body, data=_push_data(kind, link), db=db)


async def notify_customer(
    db: AsyncSession,
    tenant_id: UUID,
    customer_id: UUID,
    *,
    kind: str,
    title: str,
    body: str,
    link: str | None,
) -> None:
    """Record a customer-scoped notification and fire an Expo push (best-effort)."""
    from app.models import Notification, PushToken

    db.add(
        Notification(
            tenant_id=tenant_id,
            recipient_type="customer",
            recipient_id=customer_id,
            type=kind,
            title=title,
            body=body,
            link=link,
        )
    )
    tokens = (
        (
            await db.execute(
                select(PushToken.token).where(
                    PushToken.tenant_id == tenant_id,
                    PushToken.owner_type == "customer",
                    PushToken.owner_id == customer_id,
                )
            )
        )
        .scalars()
        .all()
    )
    await send_expo_push(list(tokens), title, body, data=_push_data(kind, link), db=db)
