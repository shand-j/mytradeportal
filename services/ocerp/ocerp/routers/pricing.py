"""Regional price lookup endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from mtp_shared import PriceLookupRequest, PriceLookupResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ocerp.database import get_db
from ocerp.services.pricing import lookup_price

router = APIRouter(prefix="/ocerp/v1/price", tags=["OpenConstructionERP"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/lookup", response_model=PriceLookupResponse)
async def price_lookup(request: PriceLookupRequest, db: DbDep) -> PriceLookupResponse:
    """Look up a cost item price by code and region."""
    return await lookup_price(db, request.code, request.region)
