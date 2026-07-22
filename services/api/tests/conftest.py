"""Shared pytest fixtures for API integration tests."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Tenant, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


async def _ensure_test_database(database_url: str) -> str:
    """Return a URL for the test database, creating the DB if necessary."""
    parsed = urlparse(database_url)
    admin_url = parsed._replace(path="/postgres").geturl()
    test_db_name = f"{parsed.path.lstrip('/')}_test"
    test_url = parsed._replace(path=f"/{test_db_name}").geturl()

    import asyncpg

    asyncpg_admin_url = admin_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(asyncpg_admin_url)
    try:
        # Start each test run with a fresh database so migrations are applied
        # from scratch and schema always matches the migration history.
        await conn.execute(
            f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE)"
        )
        await conn.execute(f"CREATE DATABASE {test_db_name}")
    finally:
        await conn.close()
    return test_url


def _run_alembic_migrations(database_url: str) -> None:
    """Apply all Alembic migrations to the given database."""
    root_dir = Path(__file__).resolve().parents[3]
    cfg = Config(str(root_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


def _app_role_database_url(admin_url: str) -> str:
    """Return a URL that authenticates as the non-superuser ``mtp_app`` role.

    Real RLS enforcement requires the application connection to be a regular
    (non-superuser, non-BYPASSRLS) role; the migration creates ``mtp_app`` and
    grants it DML. Reusing it in tests proves the policies actually filter
    rows rather than being silently bypassed.
    """
    parsed = urlparse(admin_url)
    # urlparse keeps the userinfo in ``netloc``; swap it for mtp_app:mtp_app.
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    new_netloc = f"mtp_app:mtp_app@{host}{port}"
    return parsed._replace(netloc=new_netloc).geturl()


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def test_database_url() -> str:
    url = await _ensure_test_database(settings.database_url)
    await asyncio.to_thread(_run_alembic_migrations, url)
    # Migrations create the ``mtp_app`` role; tests connect through it so RLS
    # policies are actually enforced.
    return _app_role_database_url(url)


@pytest_asyncio.fixture(loop_scope="function")
async def db(client: AsyncClient) -> AsyncIterator[AsyncSession]:
    """Expose the same AsyncSession that the test client injects into the app."""
    override = app.dependency_overrides[get_db]
    gen = override()
    session = await gen.__anext__()
    try:
        yield session
    finally:
        await gen.aclose()


@pytest_asyncio.fixture(loop_scope="function")
async def client(test_database_url: str) -> AsyncIterator[AsyncClient]:
    """Yield an HTTP test client with an isolated per-test transaction.

    ``Base.metadata.create_all`` is a no-op once migrations have run, but we
    cannot execute it as ``mtp_app`` because that role does not own the
    schema. Skip it entirely — the migration is the source of truth.
    """
    engine = create_async_engine(test_database_url, echo=False, poolclass=NullPool)

    # Outer connection transaction is rolled back at the end of the test,
    # ensuring no data persists between tests.
    async with engine.connect() as conn, conn.begin() as trans:
            # Open a savepoint so that FastAPI endpoints can call session.commit()
            # without closing the connection-level transaction.
            await conn.begin_nested()

            session = AsyncSession(bind=conn, expire_on_commit=False)

            async def override_get_db() -> AsyncIterator[AsyncSession]:
                try:
                    yield session
                finally:
                    # Return to a clean savepoint for the next request, but do
                    # not close the underlying connection or outer transaction.
                    if not session.in_transaction():
                        await session.begin_nested()

            app.dependency_overrides[get_db] = override_get_db

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                yield c

            app.dependency_overrides.clear()
            await session.close()
            await trans.rollback()

    await engine.dispose()


@pytest.fixture(autouse=True)
def _disable_supabase_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force local password auth so tests do not need a running Supabase instance."""
    monkeypatch.setattr("app.routers.auth.is_supabase_configured", lambda: False)
    monkeypatch.setattr("app.supabase.is_supabase_configured", lambda: False)


@pytest.fixture(autouse=True)
def _disable_rate_limiter_in_tests() -> "Iterator[None]":
    """Disable the global rate limiter so the bulk of integration tests are
    not flaky against shared per-IP/tenant buckets.

    Dedicated rate-limit tests opt back in by setting ``limiter.enabled = True``
    and clearing storage at the start of the test.
    """
    from app.limiter import limiter

    previous = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = previous


@pytest_asyncio.fixture(loop_scope="function")
async def admin_client(client: AsyncClient, db: AsyncSession) -> AsyncClient:
    """Yield an authenticated client for a freshly created admin user and tenant."""
    tenant = Tenant(slug=f"test-{uuid4().hex[:8]}", name="Test Electrical")
    db.add(tenant)
    await db.flush()

    # Tenant-scoped tables have RLS; the User insert below would be rejected
    # unless we declare which tenant we are operating as.
    await set_tenant_in_session(db, tenant.id)

    password = "admin-password-123"
    user = User(
        tenant_id=tenant.id,
        email="admin@test.local",
        full_name="Test Admin",
        role="admin",
        password_hash=get_password_hash(password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    response = await client.post(
        "/auth/login",
        headers={"host": f"{tenant.slug}.localhost"},
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200
    client.headers["X-Tenant-ID"] = str(tenant.id)
    return client
