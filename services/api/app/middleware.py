"""HTTP middleware: request IDs and structured access logs.

Every request gets an ``X-Request-ID`` (propagated from the caller when
present, otherwise a fresh UUID4). The ID is bound to the structlog context
for the whole request lifecycle so downstream log events (LLM calls, audit
lines, errors) automatically carry ``request_id``, and it is echoed back on
the response so support can correlate client reports with server logs.

Each completed request emits one ``http_request`` event (INFO) with method,
path, status, duration and tenant; 5xx responses and unhandled exceptions log
at ERROR instead. ``/health`` and ``/ready`` are demoted to DEBUG so probes
do not drown out real traffic.
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import structlog
from fastapi import status
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger("api.http")

# Probe endpoints: logged at DEBUG rather than INFO to keep noise down.
_QUIET_PATHS = frozenset({"/health", "/ready"})

# Cap propagated request IDs so a malicious/buggy caller cannot inject
# unbounded strings into every log line of the request.
_MAX_REQUEST_ID_LENGTH = 64


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Bind a request ID to the log context and emit one access log per request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id", "")[:_MAX_REQUEST_ID_LENGTH]
        if not request_id:
            request_id = str(uuid.uuid4())

        # Reset the context (contextvars are per-task, but be explicit) and
        # bind the fields every downstream log event should carry.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Tenant is taken from the header only — no DB lookups on the hot path.
        tenant_id = request.headers.get("X-Tenant-ID")

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.error(
                "http_request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                tenant_id=tenant_id,
                exc_info=True,
            )
            # Re-raise: FastAPI's ServerErrorMiddleware turns this into a
            # plain 500 without leaking a stack trace to the client.
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if request.url.path in _QUIET_PATHS:
            log = logger.debug
        elif response.status_code >= 500:
            log = logger.error
        else:
            log = logger.info
        log(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            tenant_id=tenant_id,
        )

        response.headers["X-Request-ID"] = request_id
        return response


class SubscriptionPaywallMiddleware(BaseHTTPMiddleware):
    """Block staff API access when the tenant's subscription is inactive.

    Beta semantics: tenants with NO subscription row are allowed (beta is
    free; legacy/seed tenants predate billing). A row exists once the tenant
    reached the plan step; from then on the subscription must be in a live
    state (trialing/active/past_due grace) — an abandoned or lapsed checkout
    gets 402 ``subscription_required`` and the app shows the paywall.

    Post-beta flip: treat "no row" as gated too, then route all new tenants
    through checkout before the dashboard.
    """

    _EXEMPT_PREFIXES = (
        "/auth",  # login/logout/me must work so the app can load the session
        "/billing",  # checkout creation + subscription read are the escape hatch
        "/onboarding",
        "/customer",
        "/businesses",  # public white-label config + quote requests
        "/webhooks",  # Paddle lifecycle events are how subscriptions activate
        "/tenants",  # bootstrap + /tenants/me branding
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
    )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or any(
            path == p or path.startswith(f"{p}/") for p in self._EXEMPT_PREFIXES
        ):
            return await call_next(request)

        from app.dependencies import _extract_token
        from app.security import decode_access_token

        token = _extract_token(request)
        claims = decode_access_token(token) if token else None
        if not claims or claims.get("subject_type") == "customer":
            return await call_next(request)

        tenant_id_raw = claims.get("tenant_id")
        if not tenant_id_raw:
            return await call_next(request)

        from app.database import get_db, get_db_session
        from app.models import Subscription
        from app.routers.billing import is_subscription_active

        try:
            tenant_id = UUID(str(tenant_id_raw))
        except (ValueError, TypeError):
            return await call_next(request)

        async def _read_subscription() -> Subscription | None:
            # Honour dependency_overrides so tests (and any embedded host) get
            # their own session factory; production uses the pooled one.
            override = request.app.dependency_overrides.get(get_db)
            if override is not None:
                async with asynccontextmanager(override)() as db:
                    return await db.scalar(
                        select(Subscription).where(Subscription.tenant_id == tenant_id)
                    )
            async with get_db_session() as db:
                return await db.scalar(
                    select(Subscription).where(Subscription.tenant_id == tenant_id)
                )

        subscription = await _read_subscription()
        if subscription is not None and not is_subscription_active(subscription):
            logger.info(
                "paywall_blocked",
                method=request.method,
                path=path,
                tenant_id=str(tenant_id),
                subscription_status=subscription.status,
            )
            return JSONResponse(
                {"detail": "subscription_required"},
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
            )
        return await call_next(request)
