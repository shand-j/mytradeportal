"""Health and readiness endpoints for the OpenConstructionERP service."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ocerp.database import get_db
from ocerp.qdrant import get_qdrant_client

router = APIRouter(prefix="/health", tags=["Health"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def health_check() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok", "service": "ocerp"}


@router.get("/ready")
async def readiness_check(db: DbDep) -> dict[str, str]:
    """Verify database and Qdrant connectivity."""
    await db.execute(text("SELECT 1"))
    qdrant = get_qdrant_client()
    await qdrant.get_collections()
    return {"status": "ready"}
