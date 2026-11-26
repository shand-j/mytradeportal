"""Beta-scale aggregation of product analytics events for platform staff."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from uuid import UUID

    from app.models import Event, Tenant

FUNNEL_EVENTS = (
    "tenant_signup",
    "staff_login",
    "ai_draft_generated",
    "quote_sent",
    "quote_accepted",
    "job_created",
    "invoice_paid",
)
_CLIENT_CATEGORIES = frozenset({"screen_view", "action", "error", "performance", "session"})


def _timestamp(value: datetime) -> str:
    return f"{value.isoformat()}Z"


def _event_name(event: Event) -> str:
    category = event.event_type.removeprefix("analytics.")
    if category in _CLIENT_CATEGORIES:
        return str(event.payload.get("name") or category)
    return category


def _actor_key(event: Event) -> str | None:
    if event.actor_id is None:
        return None
    return f"{event.actor_type}:{event.actor_id}"


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, round(len(ordered) * percentile / 100))
    return ordered[min(rank, len(ordered)) - 1]


def summarise_beta_events(
    events: Sequence[Event],
    tenants: dict[UUID, Tenant],
    *,
    days: int,
    since: datetime,
    generated_at: datetime,
) -> dict[str, Any]:
    actors: set[str] = set()
    sessions: set[str] = set()
    event_counts: Counter[str] = Counter()
    daily: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"events": 0, "actors": set(), "organisations": set()}
    )
    organisations: dict[UUID, dict[str, Any]] = defaultdict(
        lambda: {
            "events": 0,
            "actors": set(),
            "sessions": set(),
            "screen_views": 0,
            "errors": 0,
            "last_active_at": None,
            "funnel": set(),
        }
    )
    screens: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "actors": set()})
    actions: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "actors": set()})
    errors: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "organisations": set(), "latest_at": None}
    )
    performance: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    funnel_tenants: dict[str, set[UUID]] = {name: set() for name in FUNNEL_EVENTS}

    for event in events:
        category = event.event_type.removeprefix("analytics.")
        name = _event_name(event)
        payload = event.payload or {}
        actor = _actor_key(event)
        session_id = payload.get("session_id")
        day = event.created_at.date().isoformat()
        organisation = organisations[event.tenant_id]
        daily_entry = daily[day]

        event_counts[f"{category}:{name}"] += 1
        organisation["events"] += 1
        organisation["last_active_at"] = max(
            organisation["last_active_at"] or event.created_at, event.created_at
        )
        daily_entry["events"] += 1
        daily_entry["organisations"].add(event.tenant_id)
        if actor is not None:
            actors.add(actor)
            organisation["actors"].add(actor)
            daily_entry["actors"].add(actor)
        if session_id is not None:
            session = str(session_id)
            sessions.add(session)
            organisation["sessions"].add(session)
        if name in funnel_tenants:
            funnel_tenants[name].add(event.tenant_id)
            organisation["funnel"].add(name)

        if category == "screen_view":
            screen_key = str(payload.get("route") or name)
            screens[screen_key]["count"] += 1
            if actor is not None:
                screens[screen_key]["actors"].add(actor)
            organisation["screen_views"] += 1
        elif category == "action":
            actions[name]["count"] += 1
            if actor is not None:
                actions[name]["actors"].add(actor)
        elif category == "error":
            error_key = (
                name,
                str(payload.get("error_type") or "unknown"),
                str(payload.get("error_code") or payload.get("http_status") or ""),
                str(payload.get("route") or payload.get("path") or ""),
            )
            errors[error_key]["count"] += 1
            errors[error_key]["organisations"].add(event.tenant_id)
            errors[error_key]["latest_at"] = max(
                errors[error_key]["latest_at"] or event.created_at, event.created_at
            )
            organisation["errors"] += 1
        elif category == "performance":
            duration = payload.get("duration_ms")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                performance_key = (
                    name,
                    str(payload.get("method") or ""),
                    str(payload.get("path") or ""),
                )
                performance[performance_key].append(float(duration))

    signup_count = len(funnel_tenants["tenant_signup"])
    funnel = []
    for name in FUNNEL_EVENTS:
        count = len(funnel_tenants[name])
        funnel.append(
            {
                "event": name,
                "organisations": count,
                "conversion_from_signup_pct": round(count / signup_count * 100, 1)
                if signup_count
                else None,
            }
        )

    organisation_rows = []
    for tenant_id, stats in organisations.items():
        tenant = tenants.get(tenant_id)
        organisation_rows.append(
            {
                "tenant_id": str(tenant_id),
                "slug": tenant.slug if tenant else None,
                "name": tenant.name if tenant else None,
                "events": stats["events"],
                "active_users": len(stats["actors"]),
                "sessions": len(stats["sessions"]),
                "screen_views": stats["screen_views"],
                "errors": stats["errors"],
                "last_active_at": _timestamp(stats["last_active_at"]),
                "funnel": {name: name in stats["funnel"] for name in FUNNEL_EVENTS},
            }
        )
    organisation_rows.sort(key=lambda row: row["last_active_at"], reverse=True)

    return {
        "generated_at": _timestamp(generated_at),
        "window": {"days": days, "since": _timestamp(since)},
        "totals": {
            "events": len(events),
            "active_organisations": len(organisations),
            "active_users": len(actors),
            "sessions": len(sessions),
            "screen_views": sum(item["count"] for item in screens.values()),
            "actions": sum(item["count"] for item in actions.values()),
            "errors": sum(item["count"] for item in errors.values()),
        },
        "funnel": funnel,
        "daily": [
            {
                "date": day,
                "events": stats["events"],
                "active_users": len(stats["actors"]),
                "active_organisations": len(stats["organisations"]),
            }
            for day, stats in sorted(daily.items())
        ],
        "events": [
            {"event": name, "count": count} for name, count in event_counts.most_common(100)
        ],
        "screens": [
            {"screen": name, "views": stats["count"], "unique_users": len(stats["actors"])}
            for name, stats in sorted(
                screens.items(), key=lambda item: item[1]["count"], reverse=True
            )[:100]
        ],
        "actions": [
            {"action": name, "count": stats["count"], "unique_users": len(stats["actors"])}
            for name, stats in sorted(
                actions.items(), key=lambda item: item[1]["count"], reverse=True
            )[:100]
        ],
        "errors": [
            {
                "error": name,
                "error_type": key[1],
                "error_code": key[2] or None,
                "route": key[3] or None,
                "count": stats["count"],
                "affected_organisations": len(stats["organisations"]),
                "latest_at": _timestamp(stats["latest_at"]),
            }
            for key, stats in sorted(
                errors.items(), key=lambda item: item[1]["latest_at"], reverse=True
            )[:100]
            for name in [key[0]]
        ],
        "performance": [
            {
                "metric": name,
                "method": key[1] or None,
                "path": key[2] or None,
                "samples": len(durations),
                "average_ms": round(sum(durations) / len(durations), 2),
                "p50_ms": _percentile(durations, 50),
                "p95_ms": _percentile(durations, 95),
            }
            for key, durations in sorted(
                performance.items(), key=lambda item: len(item[1]), reverse=True
            )[:100]
            for name in [key[0]]
        ],
        "organisations": organisation_rows[:200],
    }


__all__ = ["FUNNEL_EVENTS", "summarise_beta_events"]
