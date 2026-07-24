"""Enable Row-Level Security and tenant-isolation policies.

Revision ID: b7e1c0f4
Revises: 450d95702829
Create Date: 2026-06-23

Every tenant-scoped table gets ``ENABLE ROW LEVEL SECURITY`` plus
``FORCE ROW LEVEL SECURITY`` so the policy applies even to the table owner
(our application connects as the ``mtp`` database role which owns the schema
in local dev). The policy honours an explicit ``app.bypass_rls = 'on'``
session setting so seed scripts and migrations can still operate across
tenants when explicitly opted in.

To make the RLS enforcement effective the application MUST NOT connect as a
PostgreSQL superuser (Postgres docs are explicit: superusers and roles with
the BYPASSRLS attribute bypass every policy). This migration also creates a
non-privileged ``mtp_app`` role with DML rights on every existing and future
table. The API container can then be pointed at a ``DATABASE_URL`` that
authenticates as ``mtp_app`` while migrations continue running as the owner.
"""

import os
from collections.abc import Sequence

from alembic import op
from app.rls import (
    TENANT_SCOPED_TABLES,
    apply_tenant_rls_sync,
    drop_tenant_rls_sync,
)

# revision identifiers, used by Alembic.
revision: str = "b7e1c0f4"
down_revision: str | Sequence[str] | None = "450d95702829"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APP_ROLE = "mtp_app"
APP_ROLE_PASSWORD = os.environ.get("APP_ROLE_PASSWORD", "mtp_app")


def _create_app_role(conn) -> None:  # type: ignore[no-untyped-def]
    """Create a non-superuser role that respects RLS policies."""
    existing = conn.exec_driver_sql(f"SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}'").first()
    if existing is None:
        conn.exec_driver_sql(
            f"CREATE ROLE {APP_ROLE} WITH LOGIN PASSWORD '{APP_ROLE_PASSWORD}' "
            f"NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    # Grants are idempotent so we re-apply them every upgrade in case a new
    # table has been added since the last migration.
    conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    conn.exec_driver_sql(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
    )
    conn.exec_driver_sql(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    conn.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    conn.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )


def upgrade() -> None:
    """Enable RLS and create the tenant-isolation policy on every scoped table."""
    conn = op.get_bind()
    _create_app_role(conn)
    apply_tenant_rls_sync(conn)
    # Sanity check: every expected table must have RLS + FORCE.
    rows = conn.exec_driver_sql(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid "
        "WHERE n.nspname='public' AND c.relrowsecurity AND c.relforcerowsecurity "
        "ORDER BY c.relname"
    ).all()
    secured = {row[0] for row in rows}
    missing = set(TENANT_SCOPED_TABLES) - secured
    if missing:
        raise RuntimeError(
            f"RLS migration finished but the following tables are not secured: {sorted(missing)}"
        )


def downgrade() -> None:
    """Drop the RLS policies and disable RLS on every scoped table."""
    drop_tenant_rls_sync(op.get_bind())
    # Intentionally leave the mtp_app role and its grants in place — dropping
    # a role with owned objects fails, and removing the role here would make
    # rerunning the upgrade much more fragile.
