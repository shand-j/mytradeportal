"""PostgreSQL Row-Level Security helpers.

The application enforces tenant isolation at two layers:

1. **Application layer** — every router that takes ``TenantDep`` filters by
   ``tenant_id`` in WHERE clauses and rejects cross-tenant references.
2. **Database layer** — every tenant-scoped table has Row-Level Security
   enabled with a policy that restricts visible rows to the value of the
   ``app.current_tenant`` session variable.

``set_tenant_in_session`` is called on every authenticated request via the
``get_current_tenant`` FastAPI dependency. The policy also honours an explicit
``app.bypass_rls = 'on'`` setting which is used by schema init, seed scripts,
and Celery workers that legitimately need cross-tenant access.
"""

from contextvars import ContextVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

# Holds the current tenant id for the active request/task. SQLAlchemy's async
# engine pool checkout listener reads this to restore the RLS session GUC on
# every connection checkout, fixing the intermittent "Could not refresh"
# errors that happen after commit() releases a connection back to the pool.
_current_tenant_ctx: ContextVar[UUID | None] = ContextVar("_current_tenant_ctx", default=None)


def get_current_tenant_id() -> UUID | None:
    """Return the tenant id for the current request/task, or None."""
    return _current_tenant_ctx.get()


# Every table that carries a tenant_id column and therefore needs RLS.
# The Tenant table itself and the shared cost_items table are intentionally
# omitted because they are not tenant-scoped.
TENANT_SCOPED_TABLES: tuple[str, ...] = (
    "users",
    "contacts",
    "quotes",
    "quote_line_items",
    "bills_of_quantities",
    "boq_line_items",
    "jobs",
    "appointments",
    "invoices",
    "invoice_line_items",
    "payments",
    "communications",
    "reviews",
    "audit_logs",
    "business_credentials",
    "service_areas",
    "business_services",
    "pricing_profiles",
    "pricing_rates",
    "integrations",
    "customers",
    "properties",
    "quote_requests",
    "media_assets",
    "consents",
    "events",
)


def _policy_statements(table: str) -> tuple[str, ...]:
    policy = f"{table}_tenant_isolation"
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {policy} ON {table}",
        f"""
        CREATE POLICY {policy}
            ON {table}
            USING (
                current_setting('app.bypass_rls', true) = 'on'
                OR tenant_id::text = current_setting('app.current_tenant', true)
            )
            WITH CHECK (
                current_setting('app.bypass_rls', true) = 'on'
                OR tenant_id::text = current_setting('app.current_tenant', true)
            )
        """,
    )


def _drop_policy_statements(table: str) -> tuple[str, ...]:
    policy = f"{table}_tenant_isolation"
    return (
        f"DROP POLICY IF EXISTS {policy} ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
    )


def apply_tenant_rls_sync(connection: Connection) -> None:
    """Enable RLS + tenant isolation policy on every tenant-scoped table.

    Safe to call multiple times; the policy is dropped and recreated each
    time. Used by the schema init (`scripts/init_db.py`) and the dev-mode
    lifespan hook so the behaviour is identical in tests and in
    `docker compose up`.

    Each ALTER/CREATE statement is issued individually because the asyncpg
    driver rejects multi-statement strings sent through a prepared statement.
    """
    for table in TENANT_SCOPED_TABLES:
        for stmt in _policy_statements(table):
            connection.exec_driver_sql(stmt)


def drop_tenant_rls_sync(connection: Connection) -> None:
    """Reverse of :func:`apply_tenant_rls_sync`."""
    for table in TENANT_SCOPED_TABLES:
        for stmt in _drop_policy_statements(table):
            connection.exec_driver_sql(stmt)


async def enable_rls(session: AsyncSession, table_name: str) -> None:
    """Enable RLS on a single table (kept for backwards compatibility)."""
    await session.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))


async def create_tenant_policy(
    session: AsyncSession,
    table_name: str,
    tenant_id_column: str = "tenant_id",
) -> None:
    """Create a policy that restricts rows to the current tenant.

    Prefer :func:`apply_tenant_rls_sync` from schema init; this helper is
    only used by legacy callers.
    """
    policy_name = f"{table_name}_tenant_isolation"
    await session.execute(text(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"))
    await session.execute(
        text(
            f"""
            CREATE POLICY {policy_name}
                ON {table_name}
                USING (
                    current_setting('app.bypass_rls', true) = 'on'
                    OR {tenant_id_column}::text = current_setting('app.current_tenant', true)
                )
                WITH CHECK (
                    current_setting('app.bypass_rls', true) = 'on'
                    OR {tenant_id_column}::text = current_setting('app.current_tenant', true)
                )
            """
        )
    )


async def set_tenant_in_session(session: AsyncSession, tenant_id: UUID) -> None:
    """Set the tenant id for the current database session.

    The setting is stored both as a PostgreSQL session GUC (using
    ``is_local = false`` so it persists for the lifetime of the connection)
    and as a Python :class:`contextvars.ContextVar`. A SQLAlchemy connection
    checkout listener reads the context var on every pool checkout and restores
    the GUC, so RLS policies keep working after ``commit()`` / ``refresh()``
    returns a connection to the pool.
    """
    _current_tenant_ctx.set(tenant_id)
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )


async def bypass_rls_in_session(session: AsyncSession) -> None:
    """Disable RLS for the current session (for seed scripts and admin tasks).

    Only call this from trusted server-side scripts that explicitly need
    cross-tenant access (seed bootstrap, scheduled cleanup jobs). The setting
    is connection-scoped and will leak across requests if used inside a
    pooled FastAPI handler.
    """
    await session.execute(text("SELECT set_config('app.bypass_rls', 'on', false)"))


async def clear_rls_session(session: AsyncSession) -> None:
    """Reset both RLS session variables. Useful for tests."""
    _current_tenant_ctx.set(None)
    await session.execute(text("SELECT set_config('app.current_tenant', '', false)"))
    await session.execute(text("SELECT set_config('app.bypass_rls', '', false)"))
