"""Payment / Paddle checkout endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import TenantDep
from app.paddle_client import create_checkout
from app.routers.invoices import _get_invoice
from app.schemas import PaddleCheckoutCreate, PaddleCheckoutRead, PaymentRead

router = APIRouter(prefix="/payments", tags=["Payments"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/checkout")
async def create_paddle_checkout(
    data: PaddleCheckoutCreate,
    tenant: TenantDep,
    db: DbDep,
) -> PaddleCheckoutRead:
    """Create a Paddle checkout URL for an invoice."""
    invoice = await _get_invoice(db, tenant.id, data.invoice_id)

    if invoice.status in {"paid", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is not available for payment",
        )

    try:
        checkout = await create_checkout(
            invoice,
            success_url=data.success_url,
            customer_email=data.customer_email,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Paddle checkout creation failed: {exc!s}",
        ) from exc

    invoice.paddle_checkout_id = checkout["checkout_id"]
    await db.commit()

    return PaddleCheckoutRead(**checkout)


@router.get("/invoice/{invoice_id}")
async def list_invoice_payments(
    invoice_id: UUID,
    tenant: TenantDep,
    db: DbDep,
) -> list[PaymentRead]:
    """List payments for an invoice."""
    invoice = await _get_invoice(db, tenant.id, invoice_id)
    return [PaymentRead.model_validate(p) for p in invoice.payments]
