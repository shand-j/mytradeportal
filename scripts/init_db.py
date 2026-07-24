#!/usr/bin/env python3
"""One-time database initialisation for a fresh production install.

This replaces Alembic migrations for pre-go-live deployments where the
database is empty. It creates the SQLAlchemy-managed tables from the current
models, creates the non-privileged application role used by the API, and
applies the Row-Level Security policies that enforce tenant isolation.

The script is idempotent and is intended to run as the API preDeploy command
(and optionally as the admin preDeploy command for Django's own tables).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, text

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"

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


def init_api_schema() -> None:
    """Create the API schema from the current SQLAlchemy models."""
    print("[init_db] Creating SQLAlchemy tables from models")
    engine = create_engine(DATABASE_URL.replace("+asyncpg", ""))
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        _create_app_role(conn)
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
