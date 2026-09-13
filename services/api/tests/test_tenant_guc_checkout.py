"""Regression tests for the tenant-GUC checkout listener (``app.database``).

The listener restores ``app.current_tenant`` on every pooled connection
checkout so RLS keeps filtering after ``commit()`` returns a connection to
the pool. Two failure modes are pinned down here:

1. Under pool churn (NullPool = a fresh physical connection per checkout),
   tenant-scoped reads after commit must still see the tenant's rows.
2. The async checkout proxy (``AsyncAdapt_asyncpg_connection``) has no
   ``exec_driver_sql``; the listener must fall back to a raw DBAPI cursor on
   AttributeError specifically, and must NOT fall back on unrelated errors.
"""

from typing import Any
from uuid import uuid4

import pytest
from app.database import _set_tenant_on_checkout
from app.models import Tenant, User
from app.rls import _current_tenant_ctx, set_tenant_in_session
from app.security import get_password_hash
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


class _RecordingCursor:
    def __init__(self, executed: list[str]) -> None:
        self._executed = executed

    def execute(self, statement: str) -> None:
        self._executed.append(statement)

    def close(self) -> None:
        pass


class _FakeDbapiConn:
    def __init__(self, executed: list[str]) -> None:
        self._executed = executed

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self._executed)


class _ProxyWithoutDriverSql:
    """Mirrors AsyncAdapt_asyncpg_connection: no ``exec_driver_sql`` method."""


class _ExplodingProxy:
    def exec_driver_sql(self, statement: str) -> None:
        raise RuntimeError("boom")


def _expected_statement(tenant_id: Any) -> str:
    return f"SELECT set_config('app.current_tenant', '{tenant_id}', false)"


def test_listener_falls_back_to_raw_cursor_when_proxy_lacks_driver_sql() -> None:
    executed: list[str] = []
    tenant_id = uuid4()
    token = _current_tenant_ctx.set(tenant_id)
    try:
        _set_tenant_on_checkout(_FakeDbapiConn(executed), None, _ProxyWithoutDriverSql())
    finally:
        _current_tenant_ctx.reset(token)
    assert executed == [_expected_statement(tenant_id)]


def test_listener_does_not_fall_back_on_unrelated_proxy_errors() -> None:
    """Only AttributeError reaches the raw-cursor path (raw cursors mid-checkout
    can abort the transaction in some asyncpg states); other errors fail safe."""
    executed: list[str] = []
    token = _current_tenant_ctx.set(uuid4())
    try:
        _set_tenant_on_checkout(_FakeDbapiConn(executed), None, _ExplodingProxy())
    finally:
        _current_tenant_ctx.reset(token)
    assert executed == []


def test_listener_is_a_noop_without_tenant_context() -> None:
    executed: list[str] = []
    token = _current_tenant_ctx.set(None)
    try:
        _set_tenant_on_checkout(_FakeDbapiConn(executed), None, _ProxyWithoutDriverSql())
    finally:
        _current_tenant_ctx.reset(token)
    assert executed == []


@pytest.mark.asyncio
async def test_tenant_reads_survive_pool_churn_after_commit(test_database_url: str) -> None:
    """NullPool hands out a fresh physical connection per checkout, so the
    session GUC set by ``set_tenant_in_session`` can never survive a commit.
    Only the checkout listener re-applying it keeps tenant rows visible.
    """
    engine = create_async_engine(test_database_url, echo=False, poolclass=NullPool)
    event.listens_for(engine.sync_engine, "checkout")(_set_tenant_on_checkout)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            tenant = Tenant(slug=f"churn-{uuid4().hex[:8]}", name="Churn Electrical")
            session.add(tenant)
            await session.flush()
            await set_tenant_in_session(session, tenant.id)
            user = User(
                tenant_id=tenant.id,
                email=f"churn-{uuid4().hex[:8]}@test.local",
                full_name="Churn Admin",
                role="admin",
                password_hash=get_password_hash("password-123"),
                is_active=True,
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        # Fresh session → fresh physical connection. If the listener failed to
        # restore the GUC, FORCE RLS would hide the row and this would be None.
        async with session_factory() as session:
            assert await session.get(User, user_id) is not None

        # Negative control: with a different tenant in context the row must be
        # hidden, proving visibility above came from the restored GUC rather
        # than an RLS bypass.
        async with session_factory() as session:
            await set_tenant_in_session(session, uuid4())
            assert await session.get(User, user_id) is None
    finally:
        _current_tenant_ctx.set(None)
        await engine.dispose()
