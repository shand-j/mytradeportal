"""Health check endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.environment,
    }


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return 200 only when the API is safe to receive production traffic.

    A ready API must be able to reach Postgres and see a populated
    ``cost_items`` catalogue. Legacy ``DOM-SEED-*`` bootstrap rows are
    excluded because they no longer count as a real catalogue. The threshold
    is configured via ``MIN_ACTIVE_COST_ITEMS`` (default 0 = gate disabled).
    """
    threshold = settings.min_active_cost_items
    try:
        row = await db.execute(
            text(
                "SELECT COUNT(*) FROM cost_items "
                "WHERE is_active = TRUE AND code NOT LIKE 'DOM-SEED-%'"
            )
        )
        active_items = int(row.scalar_one())
    except Exception as exc:  # database unreachable / not migrated yet
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unavailable",
                "reason": "database_unreachable",
                "error": f"{type(exc).__name__}",
            },
        ) from exc

    if active_items < threshold:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "reason": "catalogue_below_minimum",
                "active_cost_items": active_items,
                "min_active_cost_items": threshold,
            },
        )

    return {
        "status": "ready",
        "active_cost_items": active_items,
        "min_active_cost_items": threshold,
        "environment": settings.environment,
    }
