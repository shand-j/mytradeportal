"""Bill of Quantities generation endpoint."""

from fastapi import APIRouter, HTTPException, status
from mtp_shared import BoQGenerateRequest, BoQGenerateResponse

from ocerp.services.boq_engine import get_backend

router = APIRouter(prefix="/ocerp/v1/boq", tags=["OpenConstructionERP"])


@router.post("/generate", response_model=BoQGenerateResponse)
async def generate_boq(request: BoQGenerateRequest) -> BoQGenerateResponse:
    """Generate a detailed Bill of Quantities from a job description."""
    try:
        backend = get_backend("ddc_llm")
        return await backend.generate(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
