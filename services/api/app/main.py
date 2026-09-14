"""FastAPI application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.config import REMINDER_SCHEDULER_ENABLED, ROLLUP_SCHEDULER_ENABLED, settings
from app.database import engine
from app.limiter import limiter
from app.logging import configure_logging
from app.middleware import RequestLoggingMiddleware, SubscriptionPaywallMiddleware
from app.models import Base
from app.redis_client import close_redis
from app.rls import apply_tenant_rls_sync
from app.routers import (
    address_lookup,
    analytics,
    appointments,
    auth,
    billing,
    businesses,
    calendar,
    communications,
    contacts,
    customer_portal,
    customers,
    data_export,
    demo,
    diagnostics,
    feature_flags,
    files,
    health,
    invoices,
    jobs,
    notifications,
    onboarding,
    payments,
    pricing,
    public_docs,
    public_threads,
    quote_requests,
    quotes,
    resend_webhooks,
    reviews,
    stripe_webhooks,
    tenants,
    users,
    webhooks,
)
from app.scheduler import reminder_loop, rollup_loop

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> "AsyncIterator[None]":
    """Application lifespan: validate config, create tables in dev, configure logging."""
    # Fail fast in production if dev secrets / wildcards are still in place.
    settings.validate_production()
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # `create_all` does not add columns to existing tables. Backfill any
            # columns added since the volume was first created so local dev keeps
            # working without a manual migration.
            await conn.execute(
                text(
                    "ALTER TABLE communications ADD COLUMN IF NOT EXISTS "
                    "ai_metadata JSONB NOT NULL DEFAULT '{}'::jsonb"
                )
            )
            # `create_all` sets up the schema in dev; apply the tenant-isolation
            # RLS policies here too. Production deployments run the same schema
            # init via `scripts/init_db.py` (the single source of truth).
            await conn.run_sync(apply_tenant_rls_sync)
    configure_logging(settings.log_level)
    logger.info(
        "api_startup",
        extra={
            "environment": settings.environment,
            "allowed_origins": settings.allowed_origins,
        },
    )
    # In-process reminder scheduler (quote/invoice follow-up emails). Runs as
    # a background asyncio task; stopped cleanly on shutdown. The first sweep
    # happens one full tick after startup.
    reminder_stop: asyncio.Event | None = None
    reminder_task: asyncio.Task[None] | None = None
    if REMINDER_SCHEDULER_ENABLED:
        reminder_stop = asyncio.Event()
        reminder_task = asyncio.create_task(reminder_loop(reminder_stop))
    # Nightly AI rollup + alerts scheduler (W1-C): folds ai_call_events into
    # the ai_rollup_* tables, refreshes the weekly FX rate, and fires
    # budget/anomaly alerts. Runs once per UTC day (~02:30); idempotent.
    rollup_stop: asyncio.Event | None = None
    rollup_task: asyncio.Task[None] | None = None
    if ROLLUP_SCHEDULER_ENABLED:
        rollup_stop = asyncio.Event()
        rollup_task = asyncio.create_task(rollup_loop(rollup_stop))
    yield
    if reminder_stop is not None and reminder_task is not None:
        reminder_stop.set()
        await asyncio.gather(reminder_task, return_exceptions=True)
    if rollup_stop is not None and rollup_task is not None:
        rollup_stop.set()
        await asyncio.gather(rollup_task, return_exceptions=True)
    await engine.dispose()
    await close_redis()


app = FastAPI(
    title="My Trade Portal V2 API",
    version="2.0.0",
    description="AI-native field service management platform — UK electrician MVP",
    lifespan=lifespan,
)

# Rate limiting: register the shared limiter instance with the app so route
# decorators (e.g. ``@limiter.limit("5/minute")``) take effect, and surface
# 429s through slowapi's exception handler.
limiter.enabled = settings.rate_limit_enabled
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

# CORS is restricted to the back-office UI origin. In production this should be
# the deployed web/app URL.
#
# Railway PR-preview environments inherit the production ``ALLOWED_ORIGINS``
# value literally rather than re-resolving ``${{web.RAILWAY_PUBLIC_DOMAIN}}``
# to the preview's own web domain, which breaks smoke tests running against
# ``web-mytradeportal-pr-<n>.up.railway.app``. Always allow the deterministic
# Railway preview pattern via a strict regex so preview smoke can authenticate
# without depending on Railway variable re-templating.
_RAILWAY_PREVIEW_ORIGIN_REGEX = r"^https://web-mytradeportal-pr-\d+\.up\.railway\.app$"
# Customer portals live on per-tenant subdomains of the portal base domain.
_PORTAL_ORIGIN_REGEX = r"https://.*\.mytradeportal\.co\.uk"
_configured_regex = settings.allowed_origin_regex or None
if _configured_regex:
    _allow_origin_regex: str | None = (
        f"({_configured_regex})|({_RAILWAY_PREVIEW_ORIGIN_REGEX})|({_PORTAL_ORIGIN_REGEX})"
    )
else:
    _allow_origin_regex = f"({_RAILWAY_PREVIEW_ORIGIN_REGEX})|({_PORTAL_ORIGIN_REGEX})"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()
    ],
    allow_origin_regex=_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request IDs + structured access logs. Added last so it runs outermost and
# sees every request, including CORS preflights and rate-limit rejections.
app.add_middleware(RequestLoggingMiddleware)
# Subscription gate for staff API access (402 on inactive subscriptions).
# Sits inside the logging middleware so blocked requests are still logged.
app.add_middleware(SubscriptionPaywallMiddleware)

app.include_router(health.router)
app.include_router(feature_flags.router)
app.include_router(demo.router)
app.include_router(tenants.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(contacts.router)
app.include_router(customers.router)
app.include_router(diagnostics.router)
app.include_router(customer_portal.router)
app.include_router(quote_requests.router)
app.include_router(businesses.router)
app.include_router(onboarding.router)
app.include_router(pricing.router)
app.include_router(address_lookup.router)
app.include_router(quotes.router)
app.include_router(jobs.router)
app.include_router(appointments.router)
app.include_router(calendar.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(public_docs.router)
app.include_router(public_threads.router)
app.include_router(billing.router)
app.include_router(webhooks.router)
app.include_router(stripe_webhooks.router)
app.include_router(resend_webhooks.router)
app.include_router(analytics.router)
app.include_router(reviews.router)
app.include_router(communications.router)
app.include_router(files.router)
app.include_router(notifications.router)
app.include_router(data_export.router)
