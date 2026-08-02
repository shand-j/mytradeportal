"""Shared pytest fixtures for API integration tests."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import pytest_asyncio
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Base, Tenant, User
from app.rls import TENANT_SCOPED_TABLES, apply_tenant_rls_sync, set_tenant_in_session
from app.security import get_password_hash
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


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
        # Start each test run with a fresh database so the schema is created
        # from scratch and always matches the current SQLAlchemy models.
        await conn.execute(f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {test_db_name}")
    finally:
        await conn.close()
    return test_url


def _init_test_schema(database_url: str) -> None:
    """Create the schema from models, the app role, and RLS policies.

    This mirrors ``scripts/init_db.py`` (the single source of truth used in
    production) so tests exercise exactly the schema the app boots against,
    without a separate Alembic migration history.
    """
    sync_url = database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
            _create_app_role(conn)
            apply_tenant_rls_sync(conn)

        # Sanity check: every expected tenant-scoped table must have RLS forced.
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON c.relnamespace = n.oid "
                    "WHERE n.nspname = 'public' AND c.relrowsecurity "
                    "AND c.relforcerowsecurity"
                )
            ).all()
            secured = {row[0] for row in rows}
            missing = set(TENANT_SCOPED_TABLES) - secured
            if missing:
                raise RuntimeError(f"RLS not applied to: {sorted(missing)}")
    finally:
        engine.dispose()


def _create_app_role(conn: "Connection") -> None:
    """Create the non-superuser ``mtp_app`` role that respects RLS policies."""
    # The role name is an SQL identifier and the password is a string literal;
    # both come from configuration/environment, so quote them safely rather than
    # interpolating raw values (which breaks on quotes and risks SQL injection).
    role = conn.dialect.identifier_preparer.quote(settings.app_role_name)
    password = "'" + settings.app_role_password.replace("'", "''") + "'"
    existing = conn.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
        {"role": settings.app_role_name},
    ).first()
    if existing is None:
        conn.exec_driver_sql(
            f"CREATE ROLE {role} WITH LOGIN PASSWORD {password} "
            f"NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    else:
        conn.exec_driver_sql(f"ALTER ROLE {role} WITH PASSWORD {password}")
    conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
    conn.exec_driver_sql(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
    )
    conn.exec_driver_sql(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")


def _app_role_database_url(admin_url: str) -> str:
    """Return a URL that authenticates as the non-superuser ``mtp_app`` role.

    Real RLS enforcement requires the application connection to be a regular
    (non-superuser, non-BYPASSRLS) role; the migration creates ``mtp_app`` and
    grants it DML. Reusing it in tests proves the policies actually filter
    rows rather than being silently bypassed.
    """
    parsed = urlparse(admin_url)
    # urlparse keeps the userinfo in ``netloc``; swap it for mtp_app:<env password>.
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    new_netloc = f"mtp_app:{settings.app_role_password}@{host}{port}"
    return parsed._replace(netloc=new_netloc).geturl()


@pytest_asyncio.fixture(loop_scope="session", scope="session", autouse=True)
async def test_database_url() -> str:
    url = await _ensure_test_database(settings.database_url)
    await asyncio.to_thread(_init_test_schema, url)
    # Schema init creates the ``mtp_app`` role; tests connect through it so RLS
    # policies are actually enforced.
    app_role_url = _app_role_database_url(url)
    # Patch the module-level engine so tests that don't use the ``client``
    # fixture still hit the migrated test database instead of the default app DB.
    from app.database import engine as app_engine

    await app_engine.dispose()
    new_engine = create_async_engine(app_role_url, echo=False, poolclass=NullPool)
    app_engine.pool = new_engine.pool
    app_engine.url = new_engine.url
    app_engine.dialect = new_engine.dialect
    app_engine.sync_engine = new_engine.sync_engine
    # Rebind the sessionmaker so get_db() uses the test DB too.
    from app.database import AsyncSessionLocal

    AsyncSessionLocal.configure(bind=new_engine)
    return app_role_url


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

    ``Base.metadata.create_all`` is a no-op once the schema has been created,
    but we cannot execute it as ``mtp_app`` because that role does not own the
    schema. Skip it entirely — the model-based schema init is the source of
    truth.
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

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
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
