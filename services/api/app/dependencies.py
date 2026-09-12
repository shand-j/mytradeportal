"""FastAPI dependencies."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from mtp_shared import get_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config as app_config
from app.database import get_db
from app.models import Customer, Subscription, Tenant, User
from app.plans import (
    DEFAULT_PLAN_KEY,
    AllowanceInfo,
    get_ai_usage,
    get_plan,
)
from app.rls import set_tenant_in_session
from app.security import AUTH_COOKIE_NAME, decode_access_token

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
    except (ValueError, TypeError):
        return None
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


async def require_ai_allowance(tenant: TenantDep, db: DbDep) -> AllowanceInfo:
    """Enforce the tenant's monthly AI allowance (W2-A entitlements).

    Wire into the staff AI endpoints (generate / generate-async / refine) as::

        allowance: AiAllowanceDep  # +2 lines in the handler to surface the warning

    Behaviour:
    - Kill switch: while ``ENTITLEMENTS_ENABLED`` is false (the default) this
      is a no-op pass-through — no DB reads, always allowed.
    - Plan resolution: the tenant's Subscription.plan_key via the plan catalog
      (legacy starter|pro|business keys map onto the current tiers); tenants
      with no subscription default to ``sole_trader`` (beta tenants are
      beta_comped anyway, so this is inert during beta).
    - 80%+ of the allowance used → returned with ``warning`` set; handlers
      surface it (e.g. an ``X-AI-Allowance-Warning`` header or the quote's
      ``ai_warnings``).
    - 100%+ on a ``block`` plan (Sole Trader) → HTTP 402 with a structured
      detail payload ``{"detail": "ai_allowance_exceeded", "allowance": N,
      "used": M}`` (FastAPI wraps it under the top-level ``detail`` key).
    - 100%+ on a ``metered`` plan (Pro / Team) → allowed, with
      ``over_limit=True`` so the telemetry writer can flag overage rows for
      billing.

    The counter itself is incremented on success by the telemetry writer via
    ``app.plans.increment_ai_usage`` — never here, so failed/abandoned calls
    do not consume allowance.
    """
    if not app_config.ENTITLEMENTS_ENABLED:
        plan = get_plan(DEFAULT_PLAN_KEY)
        return AllowanceInfo(
            plan=plan,
            used=0,
            allowance=plan.ai_allowance_monthly,
            allowed=True,
            warning=None,
            over_limit=False,
        )

    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    plan = get_plan(sub.plan_key) if sub is not None else get_plan(DEFAULT_PLAN_KEY)
    allowance = plan.ai_allowance_monthly
    used = await get_ai_usage(db, tenant.id)

    warning: str | None = None
    if allowance > 0 and used >= 0.8 * allowance:
        warning = f"AI allowance nearly exhausted: {used}/{allowance} actions used this month"

    if used >= allowance and plan.overage_behavior == "block":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "detail": "ai_allowance_exceeded",
                "allowance": allowance,
                "used": used,
            },
        )

    return AllowanceInfo(
        plan=plan,
        used=used,
        allowance=allowance,
        allowed=True,
        warning=warning,
        over_limit=used >= allowance,
    )


AiAllowanceDep = Annotated[AllowanceInfo, Depends(require_ai_allowance)]
