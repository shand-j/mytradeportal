"""Runtime feature flags backed by Railway project Signals.

The flag registry lives in the Railway project (Project Settings → Feature
Flags) and is read at runtime through Railway's public GraphQL API using a
project-scoped access token. Reads are cached in-process for 60 seconds.

The module never raises: when ``RAILWAY_TOKEN`` / ``RAILWAY_PROJECT_ID`` are
unset (local dev) or the Railway API is unreachable, the registry resolves to
an empty dict and every known flag falls back to its default (``False``), so
unreleased features stay off.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RAILWAY_GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
CACHE_TTL_SECONDS = 60.0
_REQUEST_TIMEOUT = httpx.Timeout(5.0, connect=2.0)

# Failure alerting: with a 60s cache TTL, 5 consecutive failures means the
# flags have been silently stuck on defaults (unreleased features off) for
# ~5 minutes — historically a stale RAILWAY_TOKEN. Alert once per outage
# streak; the flag resets when a fetch succeeds again.
_FAILURE_ALERT_THRESHOLD = 5

# Flags the platform knows about, with their defaults. Anything missing from
# the Railway Signals registry resolves to the default — fail closed for
# unreleased features.
KNOWN_FLAGS: dict[str, bool] = {
    "voice_ai_insights": False,
    "demand_forecasting": False,
    "external_integrations": False,
    "paddle_billing": False,
}

_SIGNALS_QUERY = """
query FeatureFlags($owner: String!) {
  signals(owner: $owner) {
    key
    value
  }
}
"""

_cache: dict[str, bool] | None = None
_cache_expires_at: float = 0.0
_consecutive_failures: int = 0
_failure_alert_sent: bool = False


def _to_bool(value: Any) -> bool | None:
    """Coerce a registry value to bool; return ``None`` for non-boolean flags."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"true", "1", "yes", "on"}:
            return True
        if normalised in {"false", "0", "no", "off"}:
            return False
    return None


def _parse_signals(payload: dict[str, Any]) -> dict[str, bool]:
    """Extract boolean flags from a GraphQL ``signals`` response payload."""
    signals = payload.get("data", {}).get("signals")
    entries: list[Any]
    if isinstance(signals, dict):
        entries = [{"key": key, "value": value} for key, value in signals.items()]
    elif isinstance(signals, list):
        entries = signals
    else:
        return {}

    flags: dict[str, bool] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key") or entry.get("name")
        parsed = _to_bool(entry.get("value"))
        if isinstance(key, str) and parsed is not None:
            flags[key] = parsed
    return flags


async def fetch_registry_flags() -> dict[str, bool]:
    """Fetch raw bool flags from Railway Signals, cached for 60 seconds.

    Returns ``{}`` when Railway is not configured (local dev) or the call
    fails — callers apply defaults on top. Consecutive fetch failures are
    counted and, past ``_FAILURE_ALERT_THRESHOLD``, fire one ops alert per
    outage streak (reset on the next successful fetch).
    """
    global _cache, _cache_expires_at, _consecutive_failures, _failure_alert_sent

    now = time.monotonic()
    if _cache is not None and now < _cache_expires_at:
        return _cache

    if not settings.railway_token or not settings.railway_project_id:
        return {}

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                RAILWAY_GRAPHQL_URL,
                headers={"project-access-token": settings.railway_token},
                json={
                    "query": _SIGNALS_QUERY,
                    "variables": {"owner": f"project:{settings.railway_project_id}"},
                },
            )
            response.raise_for_status()
            flags = _parse_signals(response.json())
    except Exception:
        logger.warning("Failed to fetch feature flags from Railway Signals", exc_info=True)
        _consecutive_failures += 1
        if _consecutive_failures >= _FAILURE_ALERT_THRESHOLD and not _failure_alert_sent:
            _failure_alert_sent = True
            from app.alerting import send_alert

            await send_alert(
                "Feature flags fetch failing",
                f"Railway Signals fetches have failed {_consecutive_failures} times "
                "in a row; all known flags are stuck on their defaults. Check the "
                "RAILWAY_TOKEN / RAILWAY_PROJECT_ID variables on the api service — "
                "a stale project token is the usual cause.",
            )
        return {}

    _consecutive_failures = 0
    _failure_alert_sent = False
    _cache = flags
    _cache_expires_at = now + CACHE_TTL_SECONDS
    return flags


async def get_feature_flags() -> dict[str, bool]:
    """Return the flag registry with defaults applied for every known flag."""
    registry = await fetch_registry_flags()
    return {**KNOWN_FLAGS, **registry}


async def is_flag_enabled(flag_name: str) -> bool:
    """Return ``True`` when the named feature flag is enabled."""
    flags = await get_feature_flags()
    return bool(flags.get(flag_name, KNOWN_FLAGS.get(flag_name, False)))


async def paddle_billing_enabled() -> bool:
    """Gate all Paddle billing entry points behind ``paddle_billing``."""
    return await is_flag_enabled("paddle_billing")


def reset_cache() -> None:
    """Clear the in-process cache and failure streak (used by tests)."""
    global _cache, _cache_expires_at, _consecutive_failures, _failure_alert_sent
    _cache = None
    _cache_expires_at = 0.0
    _consecutive_failures = 0
    _failure_alert_sent = False
