"""Health check endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.qdrant import get_qdrant_client

router = APIRouter(tags=["Health"])

# Dependency probes must not hang the readiness endpoint when a service is
# down-but-slow (connection blackholes are common in container networking).
_PROBE_TIMEOUT_SECONDS = 2.0


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


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe for Railway healthchecks.

    Postgres is a hard dependency: when it is unreachable the service returns
    503 so the platform stops routing traffic. Qdrant reachability is reported
    in the body but only degrades the AI quote pipeline, so it does not fail
    the probe on its own (status becomes ``degraded``).
    """
    db_ok, qdrant_ok = await asyncio.gather(_postgres_ok(), _qdrant_ok())
    checks = {
        "postgres": "ok" if db_ok else "error",
        "qdrant": "ok" if qdrant_ok else "error",
    }
    if not db_ok:
        status = "not_ready"
        status_code = 503
    elif not qdrant_ok:
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
