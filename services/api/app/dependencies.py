"""FastAPI dependencies."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from mtp_shared import get_settings
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import config as app_config
from app.alerting import send_alert
from app.database import get_db
from app.models import AiAlertState, AiCallEvent, Customer, Subscription, Tenant, User
from app.plans import (
    DEFAULT_PLAN_KEY,
    Plan,
    current_period,
    get_plan,
    lowest_plan_with_feature,
)
from app.rls import set_tenant_in_session
from app.security import AUTH_COOKIE_NAME, decode_access_token

logger = structlog.get_logger("api.dependencies")

settings = get_settings()


def _extract_token(request: Request) -> str | None:
    """Return the auth JWT from an ``Authorization: Bearer`` header (native
    clients) or the session cookie (web). Header takes precedence."""
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
        if bearer:
            return bearer
    return request.cookies.get(AUTH_COOKIE_NAME)


def _extract_tenant_slug(host: str | None) -> str | None:
    """Return the subdomain slug from a Host header, or None for bare domains."""
    if not host:
        return None
    # Strip port if present
    host = host.split(":")[0]
    # Bare localhost / IP addresses have no subdomain
    if host in ("localhost", "127.0.0.1", "::1"):
        return None
    # Generated Railway domains (e.g. api-production.up.railway.app) are not
    # tenant subdomains — treat them as bare hosts so resolution falls back
    # to the default tenant. Real per-tenant subdomains require a custom domain.
    if host.endswith(".up.railway.app") or host.endswith(".railway.app"):
        return None
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    # e.g. demo.localhost, demo.mytradeportal.local, demo.mytradeportal.co.uk
    if len(parts) >= 2:
        return parts[0]
    return None


async def resolve_tenant(db: AsyncSession, slug: str | None) -> Tenant:
    """Look up a tenant by slug.

    Falls back to the configured default only when no subdomain was provided
    (e.g. bare localhost/127.0.0.1 in development). An explicit but unknown
    subdomain is treated as invalid.
    """
    if slug:
        result = await db.execute(select(Tenant).where(Tenant.slug == slug))
        tenant = result.scalar_one_or_none()
        if tenant is not None:
            return tenant
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive tenant",
        )
    # Fallback to default tenant for local development / bare hosts
    result = await db.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive tenant",
        )
    return tenant


async def get_current_tenant(
    request: Request,
    x_tenant_id: Annotated[UUID | None, Header(alias="X-Tenant-ID")] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
) -> Tenant:
    """Resolve tenant from X-Tenant-ID header or Host subdomain, then set RLS.

    When the request carries an authenticated session cookie, the JWT's
    ``tenant_id`` claim MUST match the resolved tenant. This prevents a user
    logged in to tenant A from accessing tenant B by flipping the X-Tenant-ID
    header.
    """
    if x_tenant_id is not None:
        tenant = await db.get(Tenant, x_tenant_id)
    else:
        slug = _extract_tenant_slug(request.headers.get("host"))
        tenant = await resolve_tenant(db, slug)
    if tenant is None or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive tenant",
        )

    # Cross-check against the auth token (Bearer header or cookie) if one was
    # provided. We deliberately only enforce when a token is present and
    # decodable so anonymous endpoints (login, health, public webhooks)
    # continue to work.
    token = _extract_token(request)
    if token:
        claims = decode_access_token(token)
        if claims is not None:
            jwt_tenant_id = claims.get("tenant_id")
            if jwt_tenant_id and str(jwt_tenant_id) != str(tenant.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Authenticated user does not belong to this tenant",
                )

    await set_tenant_in_session(db, tenant.id)
    return tenant


TenantDep = Annotated[Tenant, Depends(get_current_tenant)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Return the authenticated user from the Bearer token or session cookie."""
    token = _extract_token(request)
    if not token:
        return None
    claims = decode_access_token(token)
    if claims is None:
        return None
    # A customer token must never resolve as a staff user.
    if claims.get("subject_type") == "customer":
        return None
    try:
        user_id = UUID(claims.get("sub"))
        tenant_id = UUID(str(claims.get("tenant_id")))
    except (ValueError, TypeError):
        return None
    # Users are RLS tenant-scoped: establish the token's tenant context BEFORE
    # the lookup, mirroring get_current_customer. Without this, endpoints that
    # resolve the user without a TenantDep (e.g. /auth/me, /auth/tenant-status)
    # only authenticated when a pooled connection happened to carry the right
    # app.current_tenant GUC — an intermittent 401 under pool churn.
    await set_tenant_in_session(db, tenant_id)
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


CurrentUserDep = Annotated[User | None, Depends(get_current_user)]


async def get_current_active_user(
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """Require an authenticated active user."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


ActiveUserDep = Annotated[User, Depends(get_current_active_user)]


async def get_current_customer(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Customer:
    """Resolve the authenticated homeowner (customer) from a customer token.

    Rejects staff-user tokens (``subject_type`` must be ``customer``), looks up
    the Customer, and sets the tenant RLS context from the token's tenant so
    subsequent tenant-scoped reads are correctly isolated.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    claims = decode_access_token(token)
    if claims is None or claims.get("subject_type") != "customer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        customer_id = UUID(claims.get("sub"))
        tenant_id = UUID(claims.get("tenant_id"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    await set_tenant_in_session(db, tenant_id)
    customer = await db.get(Customer, customer_id)
    if customer is None or not customer.is_active or customer.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return customer


CurrentCustomerDep = Annotated[Customer, Depends(get_current_customer)]


class RoleChecker:
    """Dependency factory that enforces one of the allowed roles."""

    def __init__(self, allowed_roles: set[str]) -> None:
        self.allowed_roles = allowed_roles

    async def __call__(self, user: ActiveUserDep) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user


RequireAdminDep = Annotated[User, Depends(RoleChecker({"admin"}))]
RequireManagerDep = Annotated[User, Depends(RoleChecker({"admin", "manager"}))]


async def get_current_platform_staff(user: ActiveUserDep) -> User:
    """Require an authenticated platform-staff (founder/ops) caller.

    Every other staff gate in the API is tenant-scoped (``RoleChecker`` on
    the caller's tenant role), but ops endpoints such as the per-org AI cost
    leaderboard are cross-tenant by definition and a tenant role can never
    authorise them. The back-office (Django admin) gates on Django
    superusers, which the API cannot reuse, so platform staff are identified
    by the ``PLATFORM_STAFF_EMAILS`` env allowlist instead: the caller must
    be an authenticated active user AND their email must be listed. An empty
    allowlist rejects everyone. Rejections mirror ``RoleChecker`` (403
    "Insufficient permissions") so the staff-gate contract is uniform.
    """
    allowed = {
        email.strip().lower()
        for email in app_config.PLATFORM_STAFF_EMAILS.split(",")
        if email.strip()
    }
    if user.email.lower() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user


PlatformStaffDep = Annotated[User, Depends(get_current_platform_staff)]


async def _tenant_plan(tenant: Tenant, db: AsyncSession) -> Plan:
    """Resolve the tenant's subscription plan; no subscription → sole_trader."""
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    return get_plan(sub.plan_key) if sub is not None else get_plan(DEFAULT_PLAN_KEY)


def require_tier_feature(feature: str) -> Callable[[Tenant, AsyncSession], Awaitable[Tenant]]:
    """Dependency factory gating an endpoint on a plan capability.

    Tiers differ by capability only (flat pricing, unlimited users, unmetered
    AI), so this is the only enforcement dependency. A tenant without a
    subscription row defaults to ``sole_trader``. Missing capability → HTTP
    403 with a structured ``feature_not_in_plan`` payload and an upgrade hint
    naming the cheapest tier that unlocks the feature. Wire in as::

        Depends(require_tier_feature("drawing_analysis"))
    """

    async def _enforce(tenant: TenantDep, db: DbDep) -> Tenant:
        plan = await _tenant_plan(tenant, db)
        if feature not in plan.features:
            upgrade = lowest_plan_with_feature(feature)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "detail": "feature_not_in_plan",
                    "feature": feature,
                    "current_plan": plan.key,
                    "upgrade_hint": (
                        f"Upgrade to {upgrade.name} to unlock this feature."
                        if upgrade is not None
                        else "This feature is not available on any current plan."
                    ),
                },
            )
        return tenant

    return _enforce


async def _fire_fair_use_alert_once(db: AsyncSession, tenant: Tenant, monthly_count: int) -> None:
    """Dispatch exactly one fair-use staff alert per org per month.

    Deduped by an ``ai_alert_state`` row inserted (in a savepoint, so a
    duplicate rolls back nothing else) BEFORE dispatch — a crashed or
    concurrent request can never double-fire. The unique constraint is on
    (period, threshold), so the tenant id is folded into the threshold key.
    """
    period = current_period()
    try:
        # Add inside the savepoint so a duplicate rollback expunges the
        # pending row — otherwise the request's later commit would re-attempt
        # the INSERT and fail the whole endpoint on the unique constraint.
        async with db.begin_nested():
            db.add(
                AiAlertState(
                    period=period,
                    threshold=f"fair_use:{tenant.id}",
                    payload={"tenant_id": str(tenant.id), "monthly_ai_actions": monthly_count},
                )
            )
            await db.flush()
    except IntegrityError:
        return  # already fired this month
    await send_alert(
        subject=f"AI fair-use threshold crossed ({tenant.slug})",
        text=(
            f"Tenant {tenant.slug} ({tenant.id}) has made {monthly_count} AI calls this "
            f"month, crossing the fair-use threshold of "
            f"{app_config.AI_FAIR_USE_MONTHLY_THRESHOLD}. The tenant has been switched to "
            "the cheap model route for the rest of the month. No customer action needed."
        ),
    )


async def fair_use_guard(tenant: TenantDep, db: DbDep) -> None:
    """Invisible fair-use guardrail for AI endpoints. Fail-open.

    Flat pricing means AI is unmetered for customers; this dependency protects
    cost without ever exposing a usage meter:

    - Burst limit: when the tenant's ``ai_call_events`` count for the current
      UTC hour reaches ``AI_BURST_LIMIT_PER_HOUR`` → HTTP 429 with a
      ``Retry-After`` header (seconds until the hour rolls over). This is
      plain rate protection for the API caller — never surface it as a quota.
    - Monthly threshold: once the tenant's current-month AI action count
      reaches ``AI_FAIR_USE_MONTHLY_THRESHOLD``, set
      ``tenant.settings["ai_cheap_route"] = True`` (generation reads it to
      pick cheaper models) and fire ONE staff alert per org per month.

    Any internal error (DB blip, alert failure) is logged and swallowed: the
    guardrail must never take down an AI endpoint.
    """
    try:
        now = datetime.utcnow()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        burst_count = await db.scalar(
            select(func.count(AiCallEvent.id)).where(
                AiCallEvent.tenant_id == tenant.id,
                AiCallEvent.created_at >= hour_start,
            )
        )
        if (burst_count or 0) >= app_config.AI_BURST_LIMIT_PER_HOUR:
            retry_after = max(1, int((hour_start + timedelta(hours=1) - now).total_seconds()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limited",
                headers={"Retry-After": str(retry_after)},
            )

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_count = await db.scalar(
            select(func.count(AiCallEvent.id)).where(
                AiCallEvent.tenant_id == tenant.id,
                AiCallEvent.created_at >= month_start,
            )
        )
        if (monthly_count or 0) >= app_config.AI_FAIR_USE_MONTHLY_THRESHOLD:
            if not tenant.settings.get("ai_cheap_route"):
                tenant.settings = {**tenant.settings, "ai_cheap_route": True}
            await _fire_fair_use_alert_once(db, tenant, monthly_count or 0)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "fair_use_guard_failed_open",
            tenant_id=str(tenant.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )


async def require_ai_allowance(tenant: TenantDep, db: DbDep) -> None:
    """Back-compat shim for routers still declaring ``allowance: AiAllowanceDep``.

    The hybrid quota/allowance model (HTTP 402 on block plans, 80% warnings,
    metered overage) was replaced by flat tiers with unmetered AI. Kept so
    ``app.routers.quotes`` works unmodified: it now applies only the invisible
    fair-use guardrail and returns None — handlers never consumed the old
    ``AllowanceInfo`` payload.
    """
    await fair_use_guard(tenant, db)


AiAllowanceDep = Annotated[None, Depends(require_ai_allowance)]
