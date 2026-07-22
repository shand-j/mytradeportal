"""Supported estimating standards endpoint."""

from fastapi import APIRouter
from mtp_shared import StandardsListResponse

from ocerp.services.standards import list_standards

router = APIRouter(prefix="/ocerp/v1/standards", tags=["OpenConstructionERP"])


@router.get("/list", response_model=StandardsListResponse)
async def get_standards(region: str | None = None) -> StandardsListResponse:
    """Return the list of supported estimating standards."""
    return list_standards(region)
