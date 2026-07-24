"""Health and readiness endpoints for the OpenConstructionERP service."""

from typing import Annotated, Any

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


@router.get("/diagnostic")
async def qdrant_diagnostic() -> dict[str, Any]:
    """Temporary diagnostic: show Qdrant cost_items collection state.

    Returns the point count and a sample search for a consumer unit so we can
    verify why catalogue resolution is failing in production.
    """
    qdrant = get_qdrant_client()
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    # Count all points
    count = await qdrant.count(
        collection_name="cost_items",
        count_filter=Filter(must=[FieldCondition(key="is_active", match=MatchValue(value=True))]),
    )
    total_count = await qdrant.count(collection_name="cost_items")

    # Search for consumer unit from curated_seed
    from ocerp.retrieval import search_cost_items

    sample = await search_cost_items(
        query="consumer unit",
        sources=["curated_seed"],
        category="Consumer Units",
        top_k=5,
    )

    return {
        "active_points": count.count,
        "total_points": total_count.count,
        "sample_consumer_unit_search": sample,
    }
