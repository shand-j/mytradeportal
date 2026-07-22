"""Document takeoff endpoints (placeholders for future implementation)."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/ocerp/v1/takeoff", tags=["OpenConstructionERP"])


@router.post("/pdf")
async def pdf_takeoff() -> dict[str, str]:
    """Extract quantities from a PDF drawing (not yet implemented)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="PDF takeoff is not yet implemented",
    )


@router.post("/cad")
async def cad_takeoff() -> dict[str, str]:
    """Extract quantities from a CAD/DWG file (not yet implemented)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="CAD takeoff is not yet implemented",
    )


@router.post("/photo")
async def photo_takeoff() -> dict[str, str]:
    """Visual assessment and quantity estimation from photos (not yet implemented)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Photo takeoff is not yet implemented",
    )
