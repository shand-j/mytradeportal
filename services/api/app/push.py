"""Best-effort Expo push delivery.

Fire-and-forget helper for sending push notifications to registered device
tokens via Expo's push API. Every failure is logged and swallowed — push is
a nice-to-have on top of the persistent in-app notifications and must never
break the calling workflow (e.g. background quote generation).
"""

from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("api.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_expo_push(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> None:
    """POST a batch of push messages to the Expo push API. Never raises."""
    if not tokens:
        return
    messages = [{"to": token, "title": title, "body": body, "data": data or {}} for token in tokens]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(EXPO_PUSH_URL, json=messages)
        logger.info("expo_push_sent", count=len(tokens), status=response.status_code)
    except Exception as exc:
        logger.warning(
            "expo_push_failed",
            count=len(tokens),
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def notify_staff(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    kind: str,
    title: str,
    body: str,
    link: str,
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
    await send_expo_push(list(tokens), title, body, data={"link": link})


async def notify_customer(
    db: AsyncSession,
    tenant_id: UUID,
    customer_id: UUID,
    *,
    kind: str,
    title: str,
    body: str,
    link: str,
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
    await send_expo_push(list(tokens), title, body, data={"link": link})
