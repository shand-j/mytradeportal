"""Product analytics shim.

One entry point — :func:`track` — for funnel/activation events
(``tenant_signup``, ``first_ai_draft``, ``first_quote_sent``, ...). Every call:

* writes a row to the existing tenant-scoped ``events`` table with the
  ``event_type`` prefixed ``analytics.`` (``actor_type`` is ``user`` when a
  ``user_id`` is supplied, otherwise ``system``), and
* optionally mirrors the event to PostHog when ``POSTHOG_API_KEY`` is set.

Design choices (mirroring ``app.audit.write_audit_log`` discipline):

* Fail-open everywhere: analytics must never abort a business transaction,
  so every failure is logged at ``warning`` level and swallowed.
* The PostHog import is guarded (``try: import posthog``) so the dependency is
  optional; the empty-string settings idiom (as with Resend) disables the
  passthrough when no key is configured.
* Callers may pass their request-scoped session via ``db=``; otherwise the
  shim opens and commits its own session so it is safe to call from
  background tasks and schedulers. The ``events`` table is tenant-scoped, so
  a ``tenant_id`` is required for the DB row — calls without one skip the
  insert (PostHog, if configured, still receives the event).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Event
from app.rls import set_tenant_in_session

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

try:  # Optional dependency — the shim works without it installed.
    import posthog as _posthog
except ImportError:  # pragma: no cover - depends on environment
    _posthog = None

_posthog_client: Any = None


def _get_posthog_client() -> Any:
    """Return a cached PostHog client, or ``None`` when not configured."""
    global _posthog_client
    if _posthog is None or not settings.posthog_api_key:
        return None
    if _posthog_client is None:
        _posthog_client = _posthog.Posthog(
            settings.posthog_api_key,
            host=settings.posthog_host,
        )
    return _posthog_client


async def _write_event(
    db: AsyncSession,
    event_type: str,
    tenant_id: UUID,
    user_id: UUID | None,
    props: dict[str, Any],
) -> None:
    """Insert the analytics row, setting the RLS tenant GUC first."""
    await set_tenant_in_session(db, tenant_id)
    entity_type = str(props.pop("entity_type", "tenant"))
    entity_id = props.pop("entity_id", None) or tenant_id
    db.add(
        Event(
            tenant_id=tenant_id,
            actor_type="user" if user_id is not None else "system",
            actor_id=user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=props,
        )
    )
    await db.flush()


async def track(
    event: str,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    db: AsyncSession | None = None,
    **props: Any,
) -> None:
    """Record a product analytics event. Never raises.

    ``event`` is the bare event name (e.g. ``"first_quote_sent"``); the DB row
    is stored as ``analytics.<event>``. Extra keyword arguments become the
    event payload; ``entity_type``/``entity_id`` may be passed to point the
    row at a specific entity (defaults to the tenant itself).
    """
    event_type = f"analytics.{event}"

    if tenant_id is None:
        # The events table is tenant-scoped (NOT NULL tenant_id + RLS), so
        # there is nowhere to put an untenanted row.
        logger.debug("analytics.track_skipped_no_tenant", extra={"event": event_type})
    else:
        try:
            if db is not None:
                await _write_event(db, event_type, tenant_id, user_id, props)
            else:
                async with AsyncSessionLocal() as session:
                    await _write_event(session, event_type, tenant_id, user_id, props)
                    await session.commit()
        except Exception as exc:
            logger.warning(
                "analytics.track_failed",
                extra={
                    "event": event_type,
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id) if user_id is not None else None,
                    "error": str(exc),
                },
            )

    client = _get_posthog_client()
    if client is not None:
        try:
            client.capture(
                distinct_id=str(user_id or tenant_id or "anonymous"),
                event=event,
                properties={
                    "tenant_id": str(tenant_id) if tenant_id is not None else None,
                    **props,
                },
            )
        except Exception as exc:
            logger.warning(
                "analytics.posthog_failed",
                extra={"event": event_type, "error": str(exc)},
            )


__all__ = ["track"]
