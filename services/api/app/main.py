"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.database import engine
from app.limiter import limiter
from app.logging import configure_logging
from app.models import Base
from app.rls import apply_tenant_rls_sync
from app.routers import (
    address_lookup,
    analytics,
    appointments,
    auth,
    communications,
    contacts,
    feature_flags,
    files,
    health,
    invoices,
    jobs,
    payments,
    quotes,
    reviews,
    tenants,
    users,
    webhooks,
)

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
    yield
    await engine.dispose()


app = FastAPI(
    title="My Trade Portal V2 API",
    version="2.0.0",
    description="AI-native field service management platform — UK electrician MVP",
    lifespan=lifespan,
)

# Rate limiting: register the shared limiter instance with the app so route
# decorators (e.g. ``@limiter.limit("5/minute")``) take effect, and surface
# 429s through slowapi's exception handler.
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
_configured_regex = settings.allowed_origin_regex or None
if _configured_regex:
    _allow_origin_regex: str | None = f"({_configured_regex})|({_RAILWAY_PREVIEW_ORIGIN_REGEX})"
else:
    _allow_origin_regex = _RAILWAY_PREVIEW_ORIGIN_REGEX

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

app.include_router(health.router)
app.include_router(feature_flags.router)
app.include_router(tenants.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(contacts.router)
app.include_router(address_lookup.router)
app.include_router(quotes.router)
app.include_router(jobs.router)
app.include_router(appointments.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(webhooks.router)
app.include_router(analytics.router)
app.include_router(reviews.router)
app.include_router(communications.router)
app.include_router(files.router)
