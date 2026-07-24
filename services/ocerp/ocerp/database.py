"""Database session and engine configuration for the OpenConstructionERP service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ocerp.config import settings

# In production the app MUST connect through the low-privilege role that is
# subject to Row-Level Security policies. The owner/superuser DATABASE_URL is
# only used by preDeploy schema initialisation.
_DATABASE_URL = (
    settings.get_app_database_url()
    if settings.environment == "production"
    else settings.database_url
)

engine = create_async_engine(
    _DATABASE_URL,
    echo=settings.environment == "development",
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a DB session."""
    async with get_db_session() as session:
        yield session
