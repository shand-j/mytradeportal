"""Shared async Redis client for the API.

The demo endpoints use Redis as a durable "already used" flag so a visitor
without cookies (or who cleared them) still gets one generate per browser
fingerprint. Redis is a best-effort dependency: callers must treat any
connection failure as "feature unavailable, allow the request" so the demo
never breaks because the cache is down.

A single lazy module-level client is shared across requests. Its pooled
connections are bound to the event loop that first used them, so the client
is transparently recreated when the running loop changes (pytest runs each
test on a fresh loop; production serves on one loop and never recreates).
Close it in the application lifespan shutdown.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from app.config import settings

_client: aioredis.Redis | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client, creating it on first use."""
    global _client, _client_loop
    try:
        loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _client is None or _client_loop is not loop:
        # The stale client belongs to a loop that is typically already closed
        # (each pytest test gets a fresh loop); dropping the reference lets it
        # be garbage-collected rather than awaiting aclose on a dead loop.
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
        _client_loop = loop
    return _client


async def close_redis() -> None:
    """Close the shared client (idempotent); called on lifespan shutdown."""
    global _client, _client_loop
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None
            _client_loop = None
