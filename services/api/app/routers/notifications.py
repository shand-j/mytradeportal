"""Persistent in-app notifications for staff users and customer accounts.

Staff endpoints live under ``/notifications`` and require a staff session;
customer endpoints under ``/customer/notifications`` require a customer
token. Both audiences also register Expo push tokens here (delivery itself
is fire-and-forget via :mod:`app.push`).
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import ActiveUserDep, CurrentCustomerDep, TenantDep
from app.models import Customer, Notification, PushToken, Tenant, User
from app.schemas import NotificationRead, PushTokenCreate, PushTokenRead, UnreadCountRead

router = APIRouter(tags=["Notifications"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _staff_filter(user: User) -> list[ColumnElement[bool]]:
    """Visibility rule for staff: own notifications plus tenant-wide ones."""
    return [
        Notification.recipient_type == "staff",
        or_(Notification.recipient_id == user.id, Notification.recipient_id.is_(None)),
    ]


async def _get_staff_notification(
    db: AsyncSession, tenant: Tenant, user: User, notification_id: UUID
) -> Notification:
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == tenant.id,
            *_staff_filter(user),
        )
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


async def _get_customer_notification(
    db: AsyncSession, customer: Customer, notification_id: UUID
) -> Notification:
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == customer.tenant_id,
            Notification.recipient_type == "customer",
            Notification.recipient_id == customer.id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


async def _upsert_push_token(
    db: AsyncSession,
    tenant_id: UUID,
    owner_type: str,
    owner_id: UUID,
    data: PushTokenCreate,
) -> PushToken:
    """Register or re-point a device token (tokens are globally unique)."""
    push_token = await db.scalar(select(PushToken).where(PushToken.token == data.token))
    if push_token is None:
        push_token = PushToken(
            tenant_id=tenant_id,
            owner_type=owner_type,
            owner_id=owner_id,
            token=data.token,
            platform=data.platform,
        )
        db.add(push_token)
    else:
        # The same device may re-register under a different account/tenant.
        push_token.tenant_id = tenant_id
        push_token.owner_type = owner_type
        push_token.owner_id = owner_id
        push_token.platform = data.platform
    await db.commit()
    await db.refresh(push_token)
    return push_token


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationRead])
async def list_notifications(
    tenant: TenantDep,
    current_user: ActiveUserDep,
    db: DbDep,
) -> list[Notification]:
    """List the current staff user's notifications, newest first (max 50)."""
    result = await db.execute(
        select(Notification)
        .where(Notification.tenant_id == tenant.id, *_staff_filter(current_user))
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


@router.get("/notifications/unread-count", response_model=UnreadCountRead)
async def unread_count(
    tenant: TenantDep,
    current_user: ActiveUserDep,
    db: DbDep,
) -> UnreadCountRead:
    """Count the current staff user's unread notifications."""
    count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.tenant_id == tenant.id,
            Notification.read_at.is_(None),
            *_staff_filter(current_user),
        )
    )
    return UnreadCountRead(unread_count=count or 0)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: UUID,
    tenant: TenantDep,
    current_user: ActiveUserDep,
    db: DbDep,
) -> Notification:
    """Mark one of the current staff user's notifications as read."""
    notification = await _get_staff_notification(db, tenant, current_user, notification_id)
    if notification.read_at is None:
        notification.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(notification)
    return notification


@router.post(
    "/notifications/push-token",
    status_code=status.HTTP_201_CREATED,
    response_model=PushTokenRead,
)
async def register_push_token(
    data: PushTokenCreate,
    tenant: TenantDep,
    current_user: ActiveUserDep,
    db: DbDep,
) -> PushToken:
    """Upsert the staff user's Expo push token for later push delivery."""
    return await _upsert_push_token(db, tenant.id, "staff", current_user.id, data)


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------


@router.get("/customer/notifications", response_model=list[NotificationRead])
async def list_customer_notifications(
    customer: CurrentCustomerDep,
    db: DbDep,
) -> list[Notification]:
    """List the authenticated customer's notifications, newest first (max 50)."""
    result = await db.execute(
        select(Notification)
        .where(
            Notification.tenant_id == customer.tenant_id,
            Notification.recipient_type == "customer",
            Notification.recipient_id == customer.id,
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


@router.get("/customer/notifications/unread-count", response_model=UnreadCountRead)
async def customer_unread_count(
    customer: CurrentCustomerDep,
    db: DbDep,
) -> UnreadCountRead:
    """Count the authenticated customer's unread notifications."""
    count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.tenant_id == customer.tenant_id,
            Notification.recipient_type == "customer",
            Notification.recipient_id == customer.id,
            Notification.read_at.is_(None),
        )
    )
    return UnreadCountRead(unread_count=count or 0)


@router.patch("/customer/notifications/{notification_id}/read", response_model=NotificationRead)
async def mark_customer_notification_read(
    notification_id: UUID,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> Notification:
    """Mark one of the authenticated customer's notifications as read."""
    notification = await _get_customer_notification(db, customer, notification_id)
    if notification.read_at is None:
        notification.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(notification)
    return notification


@router.post(
    "/customer/notifications/push-token",
    status_code=status.HTTP_201_CREATED,
    response_model=PushTokenRead,
)
async def register_customer_push_token(
    data: PushTokenCreate,
    customer: CurrentCustomerDep,
    db: DbDep,
) -> PushToken:
    """Upsert the customer's Expo push token for later push delivery."""
    return await _upsert_push_token(db, customer.tenant_id, "customer", customer.id, data)
