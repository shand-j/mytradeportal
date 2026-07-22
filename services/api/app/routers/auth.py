"""Authentication endpoints for the back-office UI."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.dependencies import ActiveUserDep, DbDep, TenantDep
from app.limiter import limiter
from app.models import User
from app.schemas import UserLogin, UserRead
from app.security import (
    clear_auth_cookie,
    create_access_token,
    set_auth_cookie,
    verify_password,
)
from app.supabase import is_supabase_configured, sign_in_with_password

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: UserLogin,
    response: Response,
    db: DbDep,
    tenant: TenantDep,
) -> UserRead:
    """Authenticate a staff user and set an HTTP-only session cookie.

    Rate limited to 5 attempts per minute per source IP to slow credential
    stuffing. The limit is enforced regardless of which tenant is targeted.
    """
    user_result = await db.execute(
        select(User).where(User.email == data.email, User.tenant_id == tenant.id)
    )
    user = user_result.scalar_one_or_none()

    authenticated = False
    if is_supabase_configured():
        sb_response = await sign_in_with_password(data.email, data.password)
        if sb_response is not None:
            sb_user = sb_response.get("user", {})
            sb_uid = sb_user.get("id")
            # Prefer matching by Supabase UID; fall back to email+tenant.
            if user is None and sb_uid:
                user_result = await db.execute(
                    select(User).where(
                        User.supabase_uid == sb_uid, User.tenant_id == tenant.id
                    )
                )
                user = user_result.scalar_one_or_none()
            authenticated = True
    elif user is not None and user.password_hash is not None:
        authenticated = verify_password(data.password, user.password_hash)

    if not authenticated or user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    set_auth_cookie(response, token)
    return UserRead.model_validate(user)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Clear the session cookie."""
    clear_auth_cookie(response)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserRead)
async def me(current_user: ActiveUserDep) -> UserRead:
    """Return the currently authenticated user."""
    return UserRead.model_validate(current_user)
