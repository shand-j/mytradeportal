"""Database session and engine configuration for the data pipeline."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from data_pipeline.config import settings

# In production the pipeline connects through the low-privilege role used by
# the rest of the application stack.
_DATABASE_URL = (
    settings.get_app_database_url()
    if settings.environment == "production"
    else settings.database_url
)

engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
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
