"""Health check endpoints."""

from typing import Any

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.environment,
    }
