"""Staff user management endpoints."""

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import config as app_config
from app.dependencies import (
    ActiveUserDep,
    DbDep,
    RequireAdminDep,
    RequireManagerDep,
    _tenant_plan,
)
from app.email import send_event_email, tenant_reply_to
from app.email_templates import staff_invite as staff_invite_template
from app.limiter import limiter
from app.models import Tenant, User, UserInviteToken
from app.plans import Plan, next_plan_with_more_seats
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.schemas import (
    UserCreate,
    UserInviteAccept,
    UserInviteCreate,
    UserInviteLinkRequest,
    UserRead,
    UserUpdate,
)
from app.security import get_password_hash
from app.supabase import admin_create_user, is_supabase_configured

router = APIRouter(prefix="/users", tags=["Users"])
logger = structlog.get_logger("api.users")

_INVITE_TOKEN_BYTES = 32


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
    # Explicit tenant filter on top of RLS: environments connecting as a
    # superuser (e.g. e2e compose) bypass RLS entirely.
    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id).order_by(User.full_name)
    )
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


# --- Team invites (seats-per-plan gated, passwordless acceptance) -------------


def _hash_invite_token(token: str) -> str:
    """SHA-256 the raw token; the DB only ever stores this hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def _build_invite_url(request: Request, raw_token: str) -> str:
    """Build the emailed set-password link against the public landing site.

    Same base resolution as ``auth._build_reset_url`` — the landing site
    serves ``/accept-invite`` next to ``/reset-password``.
    """
    from app.config import settings as _settings

    base = (
        os.environ.get("PASSWORD_RESET_BASE_URL", "").strip()
        or _settings.app_public_url
        or str(request.base_url).rstrip("/")
    ).rstrip("/")
    return f"{base}/accept-invite?token={raw_token}"


async def _issue_invite_token(db: AsyncSession, user: User) -> str:
    """Mint an invite token and return the raw value for the email link.

    Revokes any still-valid earlier tokens for the same user so only the
    newest emailed link works. The caller commits with the rest of the
    surrounding transaction.
    """
    await db.execute(
        update(UserInviteToken)
        .where(
            UserInviteToken.user_id == user.id,
            UserInviteToken.used_at.is_(None),
            UserInviteToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    raw = secrets.token_urlsafe(_INVITE_TOKEN_BYTES)
    db.add(
        UserInviteToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=_hash_invite_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=app_config.INVITE_TOKEN_TTL_DAYS),
        )
    )
    await db.flush()
    return raw


async def _send_invite_email(request: Request, tenant: Tenant, user: User, raw_token: str) -> None:
    """Email the invite (business name, app link, set-password link). Never raises."""
    invite_url = _build_invite_url(request, raw_token)
    subject, html, text = staff_invite_template(
        business_name=tenant.name,
        invitee_name=user.full_name.split()[0] if user.full_name else None,
        invite_url=invite_url,
        testflight_url=app_config.TESTFLIGHT_URL or None,
        ttl_days=app_config.INVITE_TOKEN_TTL_DAYS,
    )
    # Account mail goes out platform-branded from the no-reply sender (see
    # ``_resend_from``), but replies should reach the inviter's inbox, not the
    # platform's — unlike password resets, an invitee replying with a question
    # is expected and useful.
    await send_event_email(
        to_email=user.email,
        subject=subject,
        html_body=html,
        text_body=text,
        event="staff_invite",
        template="staff_invite",
        reply_to=tenant_reply_to(tenant, email_event="staff_invite"),
        context={"tenant_id": str(tenant.id), "user_id": str(user.id)},
    )


async def _seats_in_use(db: AsyncSession, tenant_id: UUID) -> int:
    """Active users plus pending invites — the count the plan seat cap applies to."""
    used = await db.scalar(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            # A pending invite holds a seat; a deactivated account does not.
            (User.is_active.is_(True)) | (User.invited_at.isnot(None)),
        )
    )
    return used or 0


def _seat_limit_error(plan: Plan) -> HTTPException:
    """Structured 403 mirroring ``require_tier_feature``'s payload shape."""
    upgrade = next_plan_with_more_seats(plan)
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "detail": "seat_limit_reached",
            "current_plan": plan.key,
            "seats": plan.seats,
            "upgrade_hint": (
                f"Upgrade to {upgrade.name} for up to {upgrade.seats} users."
                if upgrade is not None
                else "Your plan already includes the most users we offer."
            ),
        },
    )


@router.post("/invite", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def invite_user(
    request: Request,
    data: UserInviteCreate,
    current_user: RequireManagerDep,
    db: DbDep,
) -> UserRead:
    """Invite a team member (admin or manager), gated on the plan's seat count.

    Creates an unactivated user (``is_active=False``, ``invited_at`` set, no
    password) in the caller's tenant and emails a single-use set-password
    link. Active users plus pending invites must stay below the plan's
    ``seats``; a tenant without a subscription counts as ``sole_trader``.
    """
    await _set_user_tenant(db, current_user)
    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:  # pragma: no cover - the caller's tenant always exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    existing = await db.execute(
        select(User).where(
            func.lower(User.email) == data.email.strip().lower(),
            User.tenant_id == current_user.tenant_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    plan = await _tenant_plan(tenant, db)
    if await _seats_in_use(db, tenant.id) >= plan.seats:
        raise _seat_limit_error(plan)

    user = User(
        tenant_id=tenant.id,
        email=data.email.strip(),
        full_name=data.full_name.strip(),
        role=data.role,
        phone=data.phone,
        password_hash=None,
        is_active=False,
        invited_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()
    raw = await _issue_invite_token(db, user)
    # Commit before emailing so the invite survives a transport failure — the
    # invitee can always fetch a fresh link from the app's login screen.
    await db.commit()
    await _send_invite_email(request, tenant, user, raw)
    logger.info(
        "staff_invite_created",
        tenant_id=str(tenant.id),
        user_id=str(user.id),
        plan=plan.key,
    )
    return UserRead.model_validate(user)


@router.post("/invite/magic-link")
@limiter.limit("5/hour")
async def request_invite_magic_link(
    request: Request,
    data: UserInviteLinkRequest,
    db: DbDep,
) -> dict[str, str]:
    """Email a fresh invite set-password link to a pending invitee.

    Pre-auth endpoint called from the app's login screen ("Been invited?").
    Responds with the same generic message whether or not a pending invite
    exists, so it cannot be used to enumerate accounts. Re-issuing revokes
    the user's earlier invite tokens.
    """
    generic = {"detail": "If that email has a pending invite, a new link is on its way."}

    email = data.email.strip().lower()
    # The lookup runs before any tenant context exists (the invitee does not
    # know their tenant), so it must bypass RLS — same pattern as the
    # bare-domain login email lookup. Only pending invites match and the
    # response is generic either way, so nothing is disclosed.
    await bypass_rls_for_transaction(db)
    result = await db.execute(
        select(User)
        .where(
            func.lower(User.email) == email,
            User.is_active.is_(False),
            User.invited_at.isnot(None),
        )
        .order_by(User.created_at.desc())
    )
    user = result.scalars().first()
    if user is None:
        return generic
    tenant = await db.get(Tenant, user.tenant_id)
    if tenant is None or not tenant.is_active:
        return generic

    raw = await _issue_invite_token(db, user)
    await db.commit()
    await _send_invite_email(request, tenant, user, raw)
    logger.info("staff_invite_link_resent", tenant_id=str(tenant.id), user_id=str(user.id))
    return generic


_INVITE_INVALID_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired invite link"
)


@router.post("/accept-invite")
@limiter.limit("10/hour")
async def accept_invite(
    request: Request,
    data: UserInviteAccept,
    db: DbDep,
) -> dict[str, str]:
    """Set a password and activate an invited account (single-use token).

    Pre-auth endpoint: unknown, expired, revoked and already-used tokens all
    fail with the same 401 so the endpoint never confirms a token exists. On
    success the invitee logs in with email + password (no session is issued
    here — the client returns to the login screen with the email pre-filled).
    """
    await bypass_rls_for_transaction(db)
    record = await db.scalar(
        select(UserInviteToken).where(UserInviteToken.token_hash == _hash_invite_token(data.token))
    )
    if (
        record is None
        or record.used_at is not None
        or record.revoked_at is not None
        or record.expires_at < datetime.now(UTC)
    ):
        raise _INVITE_INVALID_401

    user = await db.get(User, record.user_id)
    if user is None or user.is_active or user.invited_at is None:
        raise _INVITE_INVALID_401

    user.password_hash = get_password_hash(data.password)
    if data.full_name:
        user.full_name = data.full_name.strip()
    user.is_active = True
    user.invited_at = None
    record.used_at = datetime.now(UTC)
    # Defence in depth: retire any other outstanding tokens for the account.
    await db.execute(
        update(UserInviteToken)
        .where(
            UserInviteToken.user_id == user.id,
            UserInviteToken.used_at.is_(None),
            UserInviteToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()
    logger.info("staff_invite_accepted", tenant_id=str(record.tenant_id), user_id=str(user.id))
    return {"detail": "Invite accepted", "email": user.email}
