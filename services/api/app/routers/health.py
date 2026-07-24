"""Health check endpoints."""

from typing import Any

import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.environment,
    }


@router.get("/health/qdrant")
async def qdrant_diagnostic() -> dict[str, Any]:
    """Temporary diagnostic: proxy to OCERP Qdrant diagnostic endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{settings.ocerp_url}/health/diagnostic")
        response.raise_for_status()
        return response.json()
