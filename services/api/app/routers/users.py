"""Staff user management endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    ActiveUserDep,
    DbDep,
    RequireAdminDep,
    RequireManagerDep,
)
from app.models import User
from app.rls import set_tenant_in_session
from app.schemas import UserCreate, UserRead, UserUpdate
from app.security import get_password_hash
from app.supabase import admin_create_user, is_supabase_configured

router = APIRouter(prefix="/users", tags=["Users"])
logger = structlog.get_logger("api.users")


async def _set_user_tenant(db: AsyncSession, user: User) -> None:
    """Configure RLS for the authenticated user's tenant."""
    await set_tenant_in_session(db, user.tenant_id)


@router.get("", response_model=list[UserRead])
async def list_users(
    current_user: ActiveUserDep,
    db: DbDep,
) -> list[UserRead]:
    """List staff users for the current tenant."""
    await _set_user_tenant(db, current_user)
    result = await db.execute(select(User).order_by(User.full_name))
    return [UserRead.model_validate(u) for u in result.scalars().all()]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    current_user: RequireAdminDep,
    db: DbDep,
) -> UserRead:
    """Create a new staff user for the current tenant (admin only)."""
    await _set_user_tenant(db, current_user)

    existing = await db.execute(
        select(User).where(User.email == data.email, User.tenant_id == current_user.tenant_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    password_hash: str | None = None
    supabase_uid: str | None = None
    if is_supabase_configured():
        # Same provisioning as tenant bootstrap: the hosted account is created
        # with the password the admin set, so the invitee can sign in at once.
        # Supabase emails are global per project — if this email already has a
        # hosted account (e.g. another tenant), fall back to local auth; the
        # login-time migration will link them when possible.
        try:
            sb_user = admin_create_user(
                data.email,
                data.password,
                full_name=data.full_name,
                role=data.role,
                tenant_id=str(current_user.tenant_id),
            )
            supabase_uid = sb_user.get("id")
        except Exception:
            logger.warning("supabase_invite_provision_failed")
            password_hash = get_password_hash(data.password)
    else:
        password_hash = get_password_hash(data.password)

    user = User(
        tenant_id=current_user.tenant_id,
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        phone=data.phone,
        password_hash=password_hash,
        supabase_uid=supabase_uid,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    current_user: ActiveUserDep,
    db: DbDep,
) -> UserRead:
    """Get a single staff user in the current tenant."""
    await _set_user_tenant(db, current_user)
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: RequireManagerDep,
    db: DbDep,
) -> UserRead:
    """Update a staff user (admin or manager)."""
    await _set_user_tenant(db, current_user)
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if current_user.role != "admin" and user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update admin users",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    current_user: RequireAdminDep,
    db: DbDep,
) -> None:
    """Delete a staff user (admin only)."""
    await _set_user_tenant(db, current_user)
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    await db.delete(user)
    await db.commit()
