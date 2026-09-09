"""Client-side diagnostic log ingestion.

Mobile apps report device-side failures here — most importantly push-token
registration errors, which happen on the handset and never surface in server
logs. Lines land in the standard structured log pipeline with the caller's
tenant and (when available) authenticated subject.
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import TenantDep, _extract_token
from app.security import decode_access_token

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = structlog.get_logger("api.diagnostics")


class ClientLogIn(BaseModel):
    message: str = Field(max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)


@router.post("/client-log", status_code=204)
async def client_log(
    data: ClientLogIn,
    tenant: TenantDep,
    request: Request,
    db: DbDep,
) -> None:
    """Record a client-side diagnostic line. Any valid tenant + optional token."""
    token = _extract_token(request)
    claims = decode_access_token(token) if token else None
    logger.info(
        "client_log",
        tenant_id=str(tenant.id),
        subject=claims.get("sub") if claims else None,
        subject_type=claims.get("subject_type") if claims else None,
        message=data.message,
        context=data.context,
    )
