"""FastAPI application entrypoint."""

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> "AsyncIterator[None]":
    """Application lifespan: validate config, create tables in dev, configure logging."""
    # Fail fast in production if dev secrets / wildcards are still in place.
    settings.validate_production()
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # `create_all` does not run Alembic migrations, so apply the
            # tenant-isolation RLS policies here too. Production deployments
            # rely on the dedicated migration (b7e1c0f4_enable_rls) instead.
            await conn.run_sync(apply_tenant_rls_sync)
    configure_logging(settings.log_level)
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()
    ],
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
