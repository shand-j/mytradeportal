"""Health check endpoints."""

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.qdrant import get_qdrant_client
from app.redis_client import get_redis
from app.routers.files import s3_client

router = APIRouter(tags=["Health"])

# Dependency probes must not hang the readiness endpoint when a service is
# down-but-slow (connection blackholes are common in container networking).
_PROBE_TIMEOUT_SECONDS = 2.0

# The storage probe performs a real write/read/delete round-trip, which is
# slower than a ping — give it a more generous (still bounded) budget.
_STORAGE_PROBE_TIMEOUT_SECONDS = 5.0

# Object key prefix used exclusively by the storage readiness probe.
_PROBE_KEY_PREFIX = "_probes/"


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.environment,
    }


async def _postgres_ok() -> bool:
    """Ping Postgres with ``SELECT 1``; any failure means not ready."""
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _qdrant_ok() -> bool:
    """Report Qdrant reachability (needed by the AI quote pipeline)."""
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            client = get_qdrant_client()
            await client.get_collections()
            await client.close()
        return True
    except Exception:
        return False


async def _storage_ok() -> bool:
    """Write, read back, byte-compare, and delete a probe object in the bucket.

    A bare TCP/HEAD check would pass while credentials, bucket policy, or the
    data volume are broken (the MinIO→RustFS migration failure mode). Only a
    real round-trip proves uploads will work, so storage is treated as a hard
    dependency. boto3 is synchronous, so the round-trip runs in a thread; on
    timeout the thread is abandoned (bounded, one per probe).
    """

    def _round_trip() -> bool:
        client = s3_client()
        key = f"{_PROBE_KEY_PREFIX}readiness-{uuid.uuid4()}"
        payload = uuid.uuid4().bytes
        client.put_object(Bucket=settings.minio_bucket, Key=key, Body=payload)
        try:
            body = client.get_object(Bucket=settings.minio_bucket, Key=key)["Body"].read()
        finally:
            client.delete_object(Bucket=settings.minio_bucket, Key=key)
        return bool(body == payload)

    try:
        async with asyncio.timeout(_STORAGE_PROBE_TIMEOUT_SECONDS):
            return await asyncio.to_thread(_round_trip)
    except Exception:
        return False


async def _redis_ok() -> bool:
    """Report Redis reachability (best-effort cache, so degraded only)."""
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            await get_redis().ping()
        return True
    except Exception:
        return False


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe for Railway healthchecks and post-deploy gates.

    Hard dependencies (Postgres, object storage): when either is unreachable
    the service returns 503 so the platform stops routing traffic and
    post-deploy checks fail loudly. Soft dependencies (Qdrant, Redis) only
    degrade specific features (AI quotes, demo rate-limiting), so they flip
    the status to ``degraded`` while keeping a 200.
    """
    db_ok, storage_ok, qdrant_ok, redis_ok = await asyncio.gather(
        _postgres_ok(), _storage_ok(), _qdrant_ok(), _redis_ok()
    )
    checks = {
        "postgres": "ok" if db_ok else "error",
        "storage": "ok" if storage_ok else "error",
        "qdrant": "ok" if qdrant_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    if not db_ok or not storage_ok:
        status = "not_ready"
        status_code = 503
    elif not qdrant_ok or not redis_ok:
        status = "degraded"
        status_code = 200
    else:
        status = "ready"
        status_code = 200
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "environment": settings.environment,
            "checks": checks,
        },
    )
