"""Validation and redaction for client-originated product analytics."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.analytics import track

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas import ClientAnalyticsBatch

ALLOWED_PROPERTIES = frozenset(
    {
        "app_version",
        "build_number",
        "component",
        "connection",
        "device_class",
        "duration_ms",
        "entity_id",
        "entity_type",
        "error_code",
        "error_type",
        "has_preferred_dates",
        "http_status",
        "interactive_ms",
        "load_kind",
        "method",
        "network",
        "os_version",
        "outcome",
        "path",
        "platform",
        "previous_route",
        "reason",
        "resource_type",
        "route",
        "sampled",
        "source",
        "status",
        "target",
        "value",
    }
)
_NUMERIC_PROPERTIES = frozenset({"duration_ms", "http_status", "interactive_ms", "value"})
_PATH_PROPERTIES = frozenset({"path", "previous_route", "route"})
_UUID_SEGMENT = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_LONG_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{16,}$")


def normalise_route(value: str) -> str:
    path = value.split("?", 1)[0].split("#", 1)[0] or "/"
    segments = []
    for segment in path.split("/"):
        if (
            segment.isdigit()
            or _UUID_SEGMENT.fullmatch(segment)
            or _LONG_SEGMENT.fullmatch(segment)
        ):
            segments.append(":id")
        else:
            segments.append(segment)
    return "/".join(segments)[:200]


def clean_client_properties(
    properties: dict[str, Any],
) -> dict[str, str | int | float | bool | None]:
    unknown = set(properties) - ALLOWED_PROPERTIES
    if unknown:
        raise ValueError(f"Unsupported analytics properties: {', '.join(sorted(unknown))}")

    cleaned: dict[str, str | int | float | bool | None] = {}
    for key, value in properties.items():
        if key in _NUMERIC_PROPERTIES:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be numeric")
            if not math.isfinite(value):
                raise ValueError(f"{key} must be finite")
            if key == "duration_ms" and not 0 <= value <= 86_400_000:
                raise ValueError("duration_ms is outside the accepted range")
            if key == "http_status" and not 100 <= value <= 599:
                raise ValueError("http_status is outside the accepted range")
            cleaned[key] = value
            continue
        if value is None or isinstance(value, (bool, int, float)):
            cleaned[key] = value
            continue
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a scalar value")
        text = value.strip()[:200]
        if key == "entity_id":
            try:
                UUID(text)
            except ValueError as exc:
                raise ValueError("entity_id must be a UUID") from exc
        cleaned[key] = normalise_route(text) if key in _PATH_PROPERTIES else text

    return cleaned


async def record_client_batch(
    batch: ClientAnalyticsBatch,
    *,
    tenant_id: UUID,
    actor_id: UUID | None,
    actor_type: str,
    db: AsyncSession,
    entity_type: str = "tenant",
    entity_id: UUID | None = None,
) -> int:
    now = datetime.utcnow()
    for index, event in enumerate(batch.events):
        if event.occurred_at > now + timedelta(minutes=5):
            raise ValueError(f"events[{index}].occurred_at is too far in the future")
        if event.occurred_at < now - timedelta(days=30):
            raise ValueError(f"events[{index}].occurred_at is older than 30 days")
        try:
            properties = clean_client_properties(event.properties)
        except ValueError as exc:
            raise ValueError(f"events[{index}].properties: {exc}") from exc
        event_entity_id = properties.pop("entity_id", None) or entity_id or tenant_id
        event_entity_type = properties.pop("entity_type", None) or entity_type
        await track(
            event.category,
            tenant_id=tenant_id,
            user_id=actor_id,
            db=db,
            actor_type=actor_type,
            entity_type=str(event_entity_type),
            entity_id=UUID(str(event_entity_id)),
            name=event.name,
            session_id=str(event.session_id),
            occurred_at=f"{event.occurred_at.isoformat()}Z",
            client=True,
            **properties,
        )
    return len(batch.events)


__all__ = [
    "ALLOWED_PROPERTIES",
    "clean_client_properties",
    "normalise_route",
    "record_client_batch",
]
