"""Public feature-flag endpoint backed by Railway project Signals."""

from fastapi import APIRouter, Request

from app import feature_flags
from app.limiter import limiter

router = APIRouter(tags=["Feature Flags"])


@router.get("/feature-flags")
@limiter.limit("60/minute")
async def get_flags(request: Request) -> dict[str, bool]:
    """Return the feature-flag registry with defaults applied.

    Public endpoint (no auth/tenant): flags are project-scoped, not
    tenant-scoped, and the UI needs them before/without a session.
    """
    return await feature_flags.get_feature_flags()
