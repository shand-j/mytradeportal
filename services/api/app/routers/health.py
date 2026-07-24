"""Health check endpoints."""

from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.qdrant import get_qdrant_client

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.environment,
    }


@router.get("/health/qdrant")
async def qdrant_health_check() -> dict[str, Any]:
    """Temporary diagnostic endpoint: return Qdrant collection counts and a sample point."""
    qdrant = get_qdrant_client()
    collections = await qdrant.get_collections()
    result: dict[str, Any] = {
        "collections": [c.name for c in collections.collections],
    }
    for name in (settings.qdrant_collection_name, settings.qdrant_knowledge_collection_name):
        try:
            count = await qdrant.count(collection_name=name)
            sample = await qdrant.query_points(
                collection_name=name,
                query=None,
                limit=1,
                with_payload=True,
            )
            result[name] = {
                "count": count.count,
                "sample_payload": sample.points[0].payload if sample.points else None,
            }
        except Exception as exc:  # pragma: no cover - diagnostic only
            result[name] = {"error": str(exc)}
    return result
