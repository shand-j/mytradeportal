"""Authentication endpoints for the back-office UI."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.dependencies import ActiveUserDep, DbDep, get_current_tenant, resolve_tenant
from app.limiter import limiter
from app.models import User
from app.rls import set_tenant_in_session
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
) -> UserRead:
    """Authenticate a staff user and set an HTTP-only session cookie.

    Rate limited to 5 attempts per minute per source IP to slow credential
    stuffing. The limit is enforced regardless of which tenant is targeted.

    When ``tenant_slug`` is provided it takes precedence over Host-subdomain
    resolution, so login works on bare domains (e.g. Railway's
    ``*.up.railway.app``) where every tenant shares one hostname. When
    omitted, the tenant is resolved from the Host header as before.
    """
    if data.tenant_slug:
        # Resolve explicitly by slug. An unknown slug is a 401, same as an
        # unknown subdomain, so tenant enumeration behaviour is unchanged.
        # A stale session cookie for another tenant must not block logging
        # in to this one — the new cookie simply overwrites it.
        tenant = await resolve_tenant(db, data.tenant_slug)
        await set_tenant_in_session(db, tenant.id)
    else:
        tenant = await get_current_tenant(request, db=db)
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
                    select(User).where(User.supabase_uid == sb_uid, User.tenant_id == tenant.id)
                )
                user = user_result.scalar_one_or_none()
            authenticated = True

    # Support local bcrypt-auth users even when Supabase is configured.
    # This keeps admin-created tenant users and setup-token users able to
    # log in in preview/local environments where Supabase accounts may not
    # exist for those synthetic test identities.
    if not authenticated and user is not None and user.password_hash is not None:
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
