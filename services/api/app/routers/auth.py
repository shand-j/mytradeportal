"""Authentication endpoints for the back-office UI and native clients."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.dependencies import ActiveUserDep, DbDep, get_current_tenant, resolve_tenant
from app.limiter import limiter
from app.models import Tenant, User
from app.rls import set_tenant_in_session
from app.schemas import TokenResponse, UserLogin, UserRead
from app.security import (
    clear_auth_cookie,
    create_access_token,
    set_auth_cookie,
    verify_password,
)
from app.supabase import is_supabase_configured, sign_in_with_password

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _authenticate(request: Request, data: UserLogin, db: DbDep) -> tuple[Tenant, User]:
    """Resolve the tenant and verify credentials, or raise 401.

    Shared by the cookie-based ``/login`` (web) and token-based ``/token``
    (native) endpoints so both apply identical tenant resolution and
    Supabase/bcrypt credential checks.
    """
    if data.tenant_slug:
        # Resolve explicitly by slug. An unknown slug is a 401, same as an
        # unknown subdomain, so tenant enumeration behaviour is unchanged.
        tenant = await resolve_tenant(db, data.tenant_slug)
        await set_tenant_in_session(db, tenant.id)
    else:
        tenant = await get_current_tenant(request, db=db)

    user_result = await db.execute(
        select(User).where(User.email == data.email, User.tenant_id == tenant.id)
    )
    user = user_result.scalar_one_or_none()

    authenticated = False
    supabase_enabled = is_supabase_configured()
    if supabase_enabled:
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

    # Local bcrypt auth is only used when Supabase auth is disabled.
    if (
        not supabase_enabled
        and not authenticated
        and user is not None
        and user.password_hash is not None
    ):
        authenticated = verify_password(data.password, user.password_hash)

    if not authenticated or user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return tenant, user


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: UserLogin,
    response: Response,
    db: DbDep,
) -> UserRead:
    """Authenticate a staff user and set an HTTP-only session cookie (web).

    Rate limited to 5 attempts per minute per source IP to slow credential
    stuffing. When ``tenant_slug`` is provided it takes precedence over
    Host-subdomain resolution, so login works on bare domains.
    """
    _, user = await _authenticate(request, data, db)
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    set_auth_cookie(response, token)
    return UserRead.model_validate(user)


@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def token(
    request: Request,
    data: UserLogin,
    db: DbDep,
) -> TokenResponse:
    """Authenticate and return a Bearer token for native (iOS) clients.

    Same credential and tenant checks as ``/login`` but returns the JWT in the
    body instead of a cookie. Clients send it as ``Authorization: Bearer`` and
    ``X-Tenant-ID`` on subsequent requests.
    """
    _, user = await _authenticate(request, data, db)
    access = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    return TokenResponse(access_token=access, user=UserRead.model_validate(user))


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Clear the session cookie."""
    clear_auth_cookie(response)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserRead)
async def me(current_user: ActiveUserDep) -> UserRead:
    """Return the currently authenticated user."""
    return UserRead.model_validate(current_user)
