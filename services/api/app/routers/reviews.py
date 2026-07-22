"""Review endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import TenantDep
from app.models import Contact, Review
from app.rls import set_tenant_in_session
from app.schemas import ReviewCreate, ReviewRead, ReviewStats

router = APIRouter(prefix="/reviews", tags=["Reviews"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_review(db: AsyncSession, tenant_id: UUID, review_id: UUID) -> Review:
    await set_tenant_in_session(db, tenant_id)
    review = await db.get(Review, review_id)
    if review is None or review.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return review


@router.get("")
async def list_reviews(tenant: TenantDep, db: DbDep) -> list[ReviewRead]:
    """List reviews for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(
        select(Review).where(Review.tenant_id == tenant.id).order_by(Review.created_at.desc())
    )
    return [ReviewRead.model_validate(r) for r in result.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_review(data: ReviewCreate, tenant: TenantDep, db: DbDep) -> ReviewRead:
    """Create a review for a contact."""
    await set_tenant_in_session(db, tenant.id)

    contact = await db.get(Contact, data.contact_id)
    if contact is None or contact.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    review = Review(tenant_id=tenant.id, **data.model_dump())
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return ReviewRead.model_validate(review)


@router.get("/stats")
async def review_stats(tenant: TenantDep, db: DbDep) -> ReviewStats:
    """Return review aggregate statistics."""
    await set_tenant_in_session(db, tenant.id)

    result = await db.execute(
        select(
            func.avg(Review.rating).label("average"),
            func.count(Review.id).label("total"),
        ).where(Review.tenant_id == tenant.id)
    )
    row = result.one()

    status_counts: dict[str, int] = dict.fromkeys({"pending", "approved", "rejected"}, 0)
    status_result = await db.execute(
        select(Review.status, func.count(Review.id))
        .where(Review.tenant_id == tenant.id)
        .group_by(Review.status)
    )
    for status_value, count in status_result.all():
        status_counts[status_value] = count

    average = float(row.average) if row.average is not None else 0.0
    return ReviewStats(
        average_rating=round(average, 2),
        total_count=row.total or 0,
        pending_count=status_counts.get("pending", 0),
        approved_count=status_counts.get("approved", 0),
        rejected_count=status_counts.get("rejected", 0),
    )
