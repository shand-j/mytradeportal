#!/usr/bin/env python3
"""One-time database initialisation for a fresh install.

This is the single source of truth for the API schema (there are no Alembic
migrations). It creates the SQLAlchemy-managed tables from the current models,
creates the non-privileged application role used by the API plus the read-only
``mtp_metabase`` BI role, and applies the Row-Level Security policies that
enforce tenant isolation.

The script is idempotent and is intended to run as the API preDeploy command
(and optionally as the admin preDeploy command for Django's own tables).
"""

from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateColumn

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.sql.schema import Column, MetaData

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"

# NOTE: sync_missing_columns below is safe on non-empty tables (see PR #10).
# Ensure the API package is importable whether we run from the repo root or
# from a container that has copied the API code elsewhere.
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.models import Base  # noqa: E402
from app.rls import TENANT_SCOPED_TABLES, apply_tenant_rls_sync  # noqa: E402

# Load shared settings so the production app-role password is read from env.
from mtp_shared import get_settings  # noqa: E402

_shared_settings = get_settings()

APP_ROLE = _shared_settings.app_role_name
APP_ROLE_PASSWORD = _shared_settings.app_role_password

# Read-only BI role used by the local Metabase container (compose profile
# ``observability``). The default password is dev-only; production deployments
# must set METABASE_DB_PASSWORD.
METABASE_ROLE = os.environ.get("METABASE_DB_USER", "mtp_metabase")
METABASE_DATABASE = os.environ.get("METABASE_DB_NAME", "metabase")
METABASE_ROLE_PASSWORD = os.environ.get("METABASE_DB_PASSWORD", "mtp_metabase")

DATABASE_URL = os.environ["DATABASE_URL"]


def _create_app_role(conn: Connection) -> None:
    """Create a non-superuser role that respects RLS policies."""
    existing = conn.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
        {"role": APP_ROLE},
    ).first()
    if existing is None:
        conn.exec_driver_sql(
            f"CREATE ROLE {APP_ROLE} WITH LOGIN PASSWORD '{APP_ROLE_PASSWORD}' "
            f"NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    else:
        # Keep the role password in sync with the env var in case it was
        # rotated after the role was first created.
        conn.exec_driver_sql(f"ALTER ROLE {APP_ROLE} WITH PASSWORD '{APP_ROLE_PASSWORD}'")
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


def _create_metabase_role(conn: Connection) -> None:
    """Create the read-only BI role used by Metabase (BI-only, not for the API).

    RLS is ``FORCE``d on every tenant-scoped table, so a regular role would
    see zero rows; the role therefore carries ``BYPASSRLS`` and must stay
    strictly read-only on application data — it is granted ``SELECT`` on all
    current tables and via default privileges on future ones.

    The one exception is ``CREATE ON SCHEMA public``: Metabase stores its own
    metadata (users, dashboards, the Liquibase changelog) in the database
    named by ``MB_DB_DBNAME`` and refuses to boot if it cannot migrate. As
    owner of the tables it creates, the role can maintain its metadata while
    remaining unable to write to any application table.
    """
    existing = conn.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
        {"role": METABASE_ROLE},
    ).first()
    if existing is None:
        conn.exec_driver_sql(
            f"CREATE ROLE {METABASE_ROLE} WITH LOGIN PASSWORD '{METABASE_ROLE_PASSWORD}' "
            f"NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    else:
        # Keep the password and BYPASSRLS flag in sync in case either changed
        # after the role was first created.
        conn.exec_driver_sql(
            f"ALTER ROLE {METABASE_ROLE} WITH LOGIN PASSWORD '{METABASE_ROLE_PASSWORD}' "
            f"NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {METABASE_ROLE}")
    conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {METABASE_ROLE}")
    conn.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {METABASE_ROLE}"
    )


def _postgres_default_literal(column: Column[object]) -> str | None:
    """Best-effort SQL literal to use as a temporary DEFAULT for backfilling.

    Recent models declare ``nullable=False`` with a Python-side ``default=``
    but no ``server_default=``; the migration DDL supplies the server default
    separately. When we're reconciling a live schema against ``Base.metadata``
    we need to backfill existing rows before we can enforce ``NOT NULL``, so
    map the common Python defaults to safe Postgres literals.

    Returns ``None`` if we can't confidently synthesise a literal — the
    caller then falls back to leaving the column nullable and logging a
    warning.
    """
    default = column.default
    if default is None:
        return None
    arg = getattr(default, "arg", None)
    # SQLAlchemy wraps zero-arg callables (e.g. ``dict``, ``list``) so they
    # accept a context; invoke with ``None`` to recover the raw value.
    if getattr(default, "is_callable", False) and callable(arg):
        try:
            arg = arg(None)
        except Exception:  # pragma: no cover - defensive
            return None
    if isinstance(column.type, JSONB):
        if arg == {}:
            return "'{}'::jsonb"
        if arg == []:
            return "'[]'::jsonb"
        return None
    if isinstance(arg, bool):
        return "true" if arg else "false"
    if isinstance(arg, int | float | Decimal):
        return str(arg)
    if isinstance(arg, str):
        escaped = arg.replace("'", "''")
        return f"'{escaped}'"
    return None


def _add_missing_column(
    conn: Connection, table_name: str, column: Column[object], dialect: object
) -> str:
    """Issue DDL for a single missing column and return the identifier added.

    Handles the ``NOT NULL`` + no ``server_default`` case in two steps so we
    stay safe on tables that already contain rows.
    """
    column_ddl = str(CreateColumn(column).compile(dialect=dialect)).strip()  # type: ignore[arg-type]
    needs_backfill = not column.nullable and column.server_default is None

    if not needs_backfill:
        statement = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS {column_ddl}'
        print(f"[init_db] Adding missing column {table_name}.{column.name} via: {statement}")
        conn.exec_driver_sql(statement)
        return f"{table_name}.{column.name}"

    nullable_ddl = column_ddl.replace(" NOT NULL", "")
    default_literal = _postgres_default_literal(column)
    print(f"[init_db] Adding missing NOT NULL column {table_name}.{column.name} in two steps")
    conn.exec_driver_sql(f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS {nullable_ddl}')
    if default_literal is None:
        print(
            f"[init_db] WARNING: {table_name}.{column.name} is NOT NULL but no "
            f"default could be synthesised; leaving nullable so the pre-deploy "
            f"step does not fail. Please add a server_default or backfill migration."
        )
        return f"{table_name}.{column.name} (nullable)"

    conn.exec_driver_sql(
        f'UPDATE "{table_name}" SET "{column.name}" = {default_literal} '
        f'WHERE "{column.name}" IS NULL'
    )
    conn.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column.name}" SET DEFAULT {default_literal}'
    )
    conn.exec_driver_sql(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column.name}" SET NOT NULL')
    return f"{table_name}.{column.name}"


def sync_missing_columns(conn: Connection, metadata: MetaData) -> list[str]:
    """Add columns declared on ``metadata`` but missing from the live database.

    ``Base.metadata.create_all`` only creates *tables* that do not yet exist;
    it never issues ``ALTER TABLE`` for new columns on existing tables. During
    pre-go-live iteration we add model columns without running Alembic on
    Railway, which historically produced 500s such as
    ``asyncpg.exceptions.UndefinedColumnError: column
    bills_of_quantities.retrieval_evidence does not exist``.

    Returns the list of ``"<table>.<column>"`` identifiers that were added,
    for logging and tests.
    """
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names(schema="public"))
    dialect = conn.dialect
    added: list[str] = []

    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            # create_all just created this whole table, so every column is
            # already present.
            continue
        live_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in live_columns:
                continue
            added.append(_add_missing_column(conn, table.name, column, dialect))

    if added:
        print(f"[init_db] Reconciled {len(added)} missing column(s): {added}")
    else:
        print("[init_db] No missing columns to reconcile")
    return added


def _create_metabase_database(engine) -> None:
    """Create Metabase's own metadata database, owned by the BI role.

    Metabase refuses to boot unless it can migrate its metadata store, but its
    Liquibase migrations ALTER tables by name and clash with the application
    schema (e.g. ``tenants``) — so it gets a dedicated database, never the
    application one. Runs in AUTOCOMMIT: CREATE DATABASE cannot run inside a
    transaction block.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :db"),
            {"db": METABASE_DATABASE},
        ).first()
        if exists is None:
            conn.exec_driver_sql(f"CREATE DATABASE {METABASE_DATABASE} OWNER {METABASE_ROLE}")


def init_api_schema() -> None:
    """Create the API schema from the current SQLAlchemy models."""
    print("[init_db] Creating SQLAlchemy tables from models")
    engine = create_engine(DATABASE_URL.replace("+asyncpg", ""))
    with engine.begin() as conn:
        # The BI role must exist before its database is created with it as owner.
        _create_metabase_role(conn)
    _create_metabase_database(engine)
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        # ``create_all`` never issues ``ALTER TABLE`` for new columns on
        # existing tables, so bring the live schema forward for any columns
        # added to the models since the last deploy.
        sync_missing_columns(conn, Base.metadata)
        _create_app_role(conn)
        _create_metabase_role(conn)
        apply_tenant_rls_sync(conn)

    # Sanity check: every expected tenant-scoped table must have RLS + FORCE.
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid "
                "WHERE n.nspname='public' AND c.relrowsecurity AND c.relforcerowsecurity "
                "ORDER BY c.relname"
            )
        ).all()
        secured = {row[0] for row in rows}
        missing = set(TENANT_SCOPED_TABLES) - secured
        if missing:
            raise RuntimeError(
                f"RLS setup finished but the following tables are not secured: {sorted(missing)}"
            )
        print(f"[init_db] RLS applied to {len(secured)} tenant-scoped tables")


def init_admin_schema() -> None:
    """Create/update Django admin tables."""
    candidates = [
        ROOT / "services" / "admin" / "manage.py",
        ROOT / "manage.py",
    ]
    manage_py = next((p for p in candidates if p.exists()), None)
    if manage_py is None:
        print("[init_db] Django manage.py not found, skipping admin schema")
        return

    admin_dir = manage_py.parent
    print("[init_db] Running Django migrate")
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=admin_dir,
        check=True,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "admin_project.settings"},
    )


if __name__ == "__main__":
    init_api_schema()
    init_admin_schema()
    print("[init_db] Done")
