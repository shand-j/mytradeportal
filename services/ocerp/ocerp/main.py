"""OpenConstructionERP microservice entrypoint."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from ocerp.config import settings
from ocerp.logging import configure_logging
from ocerp.routers import boq, health, knowledge, pricing, standards, takeoff

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(app: FastAPI) -> "AsyncIterator[None]":
    """Application lifespan: configure logging on startup."""
    configure_logging(settings.log_level)
    yield


app = FastAPI(
    title="My Trade Portal V2 — OpenConstructionERP Service",
    version="2.0.0",
    description="Internal estimation microservice for BoQ generation and cost lookups",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(boq.router)
app.include_router(pricing.router)
app.include_router(standards.router)
app.include_router(takeoff.router)
app.include_router(knowledge.router)
