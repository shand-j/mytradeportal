"""Database session and engine configuration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.rls import get_current_tenant_id

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


@event.listens_for(engine.sync_engine, "checkout")
def _set_tenant_on_checkout(dbapi_conn: Any, connection_record: Any, connection_proxy: Any) -> None:
    """Restore the RLS tenant GUC every time a connection is checked out.

    Async SQLAlchemy returns connections to the pool after commit(), which
    loses the PostgreSQL session GUC set by ``set_tenant_in_session``. By
    storing the tenant id in a ContextVar and re-applying it on checkout, RLS
    policies continue to work for subsequent operations such as refresh().
    """
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        return
    try:
        # Prefer executing through the SQLAlchemy connection proxy when it is
        # available. Some asyncpg wrapper states do not support a raw DBAPI
        # cursor during checkout, which can abort the transaction.
        if connection_proxy is not None:
            connection_proxy.exec_driver_sql(
                "SELECT set_config('app.current_tenant', %s, false)",
                (str(tenant_id),),
            )
        else:
            cursor = dbapi_conn.cursor()
            cursor.execute(
                "SELECT set_config('app.current_tenant', %s, false)",
                (str(tenant_id),),
            )
            cursor.close()
    except Exception:
        # Fail safe: if we cannot set the tenant the connection will still
        # work, but RLS may hide rows. Let the application handle the error.
        pass


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
