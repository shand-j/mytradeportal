"""Best-effort Expo push delivery.

Fire-and-forget helper for sending push notifications to registered device
tokens via Expo's push API. Every failure is logged and swallowed — push is
a nice-to-have on top of the persistent in-app notifications and must never
break the calling workflow (e.g. background quote generation). Failures are
logged LOUDLY (error level) and per-ticket ``DeviceNotRegistered`` tokens are
cleaned up, so a broken production push path is visible in the logs instead
of failing silently.

Push TICKETS only confirm that Expo's servers accepted a message — APNs-side
delivery failures (``InvalidCredentials``, ``DeviceNotRegistered``) surface
solely in push RECEIPTS. Every send with ok tickets therefore spawns a
detached receipt check (:func:`_check_push_receipts`); without it a broken
APNs leg looks exactly like success in the logs.
"""

import asyncio
import re
from uuid import UUID

import httpx
import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import EXPO_ACCESS_TOKEN, PUSH_RECEIPT_CHECK_DELAY_SECONDS

logger = structlog.get_logger("api.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"

# Receipt checks are detached tasks that outlive the request; keep strong
# references so the event loop does not garbage-collect them mid-flight.
_background_tasks: set[asyncio.Future[None]] = set()

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


def _expo_headers() -> dict[str, str]:
    """Auth header for the Expo push API (only needed with enhanced security)."""
    if EXPO_ACCESS_TOKEN:
        return {"Authorization": f"Bearer {EXPO_ACCESS_TOKEN}"}
    return {}


async def send_expo_push(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    db: AsyncSession | None = None,
    badge: int | None = None,
    tenant_id: UUID | None = None,
) -> None:
    """POST a batch of push messages to the Expo push API. Never raises.

    The Expo push API answers HTTP 200 even when individual messages fail,
    so the per-ticket statuses in the response body are inspected: every
    error ticket is logged at error level and tokens reported as
    ``DeviceNotRegistered`` are deleted (when ``db`` is provided) so dead
    devices stop being targeted on subsequent sends. Ok tickets carry receipt
    ids — a detached receipt check (:func:`_check_push_receipts`) follows up
    on them, because APNs-side delivery failures only appear there.
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
            # App-icon badge: the recipient's unread notification count. iOS
            # only badges the icon when the payload carries a number.
            **({"badge": badge} if badge is not None else {}),
            "data": data or {},
        }
        for token in tokens
    ]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(EXPO_PUSH_URL, json=messages, headers=_expo_headers())
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

    receipt_tokens: dict[str, str] = {}
    dead_tokens: list[str] = []
    failed = 0
    for token, ticket in zip(tokens, tickets, strict=False):
        if not isinstance(ticket, dict):
            continue
        if ticket.get("status") == "ok":
            ticket_id = ticket.get("id")
            if isinstance(ticket_id, str) and ticket_id:
                receipt_tokens[ticket_id] = token
            continue
        if ticket.get("status") != "error":
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

    if receipt_tokens:
        _schedule_receipt_check(receipt_tokens, tenant_id)

    logger.info("expo_push_sent", count=len(tokens), delivered=len(tokens) - failed)


def _schedule_receipt_check(receipt_tokens: dict[str, str], tenant_id: UUID | None) -> None:
    """Spawn the detached receipt check, keeping a strong ref until it finishes."""
    task = asyncio.create_task(_check_push_receipts(receipt_tokens, tenant_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _check_push_receipts(receipt_tokens: dict[str, str], tenant_id: UUID | None) -> None:
    """Fetch Expo delivery receipts for a sent batch. Never raises.

    Runs as a detached task ``PUSH_RECEIPT_CHECK_DELAY_SECONDS`` after the
    send — receipts are not ready immediately. ``InvalidCredentials`` means
    Expo cannot authenticate to APNs (missing/revoked APNs key on the EAS
    project, or a bundle-id/environment mismatch) and is logged with a
    remediation hint; ``DeviceNotRegistered`` tokens are deleted like
    ticket-level ones, from a fresh tenant-scoped session because the request
    session that sent the push is long closed.
    """
    try:
        await asyncio.sleep(PUSH_RECEIPT_CHECK_DELAY_SECONDS)
        receipt_ids = list(receipt_tokens)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    EXPO_RECEIPTS_URL, json={"ids": receipt_ids}, headers=_expo_headers()
                )
        except Exception as exc:
            logger.warning(
                "expo_push_receipts_failed",
                count=len(receipt_ids),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return

        if response.status_code != 200:
            logger.error(
                "expo_push_receipts_http_error",
                count=len(receipt_ids),
                status=response.status_code,
                body=response.text[:500],
            )
            return

        try:
            receipts = response.json().get("data") or {}
        except ValueError:
            logger.error(
                "expo_push_receipts_bad_response",
                count=len(receipt_ids),
                body=response.text[:500],
            )
            return

        dead_tokens: list[str] = []
        for receipt_id, receipt in receipts.items():
            if not isinstance(receipt, dict) or receipt.get("status") != "error":
                continue
            details = receipt.get("details") or {}
            error = details.get("error", "unknown")
            token = receipt_tokens.get(receipt_id, "")
            if error == "InvalidCredentials":
                logger.error(
                    "expo_push_invalid_credentials",
                    message=receipt.get("message"),
                    hint=(
                        "Expo cannot authenticate to APNs — verify the APNs key on the "
                        "EAS project (eas credentials -p ios) matches the app's bundle id"
                    ),
                )
            else:
                logger.error(
                    "expo_push_receipt_error",
                    token=token,
                    error=error,
                    message=receipt.get("message"),
                )
            if error == "DeviceNotRegistered" and token:
                dead_tokens.append(token)

        if dead_tokens and tenant_id is not None:
            await _delete_dead_tokens_detached(dead_tokens, tenant_id)
        logger.info("expo_push_receipts_checked", count=len(receipt_ids), dead=len(dead_tokens))
    except Exception as exc:
        logger.warning(
            "expo_push_receipts_unexpected",
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def _delete_dead_tokens_detached(tokens: list[str], tenant_id: UUID) -> None:
    """Delete DeviceNotRegistered tokens from a fresh tenant-scoped session.

    RLS is FORCEd on the push_tokens table, so the delete needs the tenant
    context re-declared on the new session.
    """
    from app.database import get_db_session
    from app.models import PushToken
    from app.rls import set_tenant_in_session

    try:
        async with get_db_session() as db:
            await set_tenant_in_session(db, tenant_id)
            await db.execute(delete(PushToken).where(PushToken.token.in_(tokens)))
            await db.commit()
        logger.info("expo_push_dead_tokens_removed", count=len(tokens), source="receipts")
    except Exception as exc:
        logger.warning(
            "expo_push_dead_token_cleanup_failed",
            count=len(tokens),
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def _unread_count(
    db: AsyncSession,
    tenant_id: UUID,
    recipient_type: str,
    recipient_id: UUID | None,
) -> int:
    """Unread notification count for the push badge, including the pending row."""
    from app.models import Notification

    conditions = [
        Notification.tenant_id == tenant_id,
        Notification.recipient_type == recipient_type,
        Notification.read_at.is_(None),
    ]
    if recipient_id is not None:
        conditions.append(Notification.recipient_id == recipient_id)
    return int(
        await db.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0
    )


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
    badge = await _unread_count(db, tenant_id, "staff", None)
    await send_expo_push(
        list(tokens),
        title,
        body,
        data=_push_data(kind, link),
        db=db,
        badge=badge,
        tenant_id=tenant_id,
    )


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
    badge = await _unread_count(db, tenant_id, "customer", customer_id)
    await send_expo_push(
        list(tokens),
        title,
        body,
        data=_push_data(kind, link),
        db=db,
        badge=badge,
        tenant_id=tenant_id,
    )
