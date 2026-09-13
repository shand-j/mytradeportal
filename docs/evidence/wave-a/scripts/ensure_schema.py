#!/usr/bin/env python3
"""Reconcile the local dev database schema with the current SQLAlchemy models.

The compose Postgres volume on this machine was initialised before several
model revisions landed (Stripe Connect tables/columns, ai_call_events
telemetry columns, ...). The API's fail-open writers then silently drop rows
and strict paths 500. This script is ADDITIVE ONLY:

1. ``ADD COLUMN`` for model columns missing from existing tables (nullable,
   or with the model's scalar default — the same end state as a fresh init
   for the rows we care about),
2. ``CREATE TABLE IF NOT EXISTS`` for tables that do not exist at all,
3. (re)apply the standard tenant-isolation RLS policies from ``app.rls`` —
   exactly what ``scripts/init_db.py`` does on a fresh init.

Idempotent. Uses the app's own engine, so run with the same env as
``start-stack.sh`` (DATABASE_URL).

    ../../.venv/bin/python ../../docs/evidence/wave-a/scripts/ensure_schema.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "services" / "api"))

from app.database import engine
from app.models import Base
from app.rls import TENANT_SCOPED_TABLES, _policy_statements


def _column_ddl(table_name: str, column, dialect) -> str:
    col_type = column.type.compile(dialect=dialect)
    stmt = f'ALTER TABLE {table_name} ADD COLUMN "{column.name}" {col_type}'
    if column.default is not None and column.default.is_scalar:
        default = column.default.arg
        if isinstance(default, bool):
            stmt += f" DEFAULT {'true' if default else 'false'}"
        elif isinstance(default, (int, float)):
            stmt += f" DEFAULT {default}"
        else:
            stmt += f" DEFAULT '{default}'"
    # NOT NULL columns without a scalar default stay nullable so the ALTER
    # works on non-empty tables; new writes always supply a value.
    return stmt


async def _sync_missing_columns(conn, table) -> list[str]:
    existing = {
        row[0]
        for row in (
            await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": table.name},
            )
        ).fetchall()
    }
    if not existing:
        return []  # table does not exist yet — create_all handles it
    added: list[str] = []
    dialect = engine.dialect
    for column in table.columns:
        if column.name in existing:
            continue
        await conn.exec_driver_sql(_column_ddl(table.name, column, dialect))
        added.append(f"{table.name}.{column.name}")
    return added


async def main() -> None:
    added: list[str] = []
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            added.extend(await _sync_missing_columns(conn, table))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))
        for table_name in TENANT_SCOPED_TABLES:
            for stmt in _policy_statements(table_name):
                try:
                    await conn.exec_driver_sql(stmt)
                except Exception as exc:  # table absent from this DB — skip
                    print(f"  RLS skipped for {table_name}: {type(exc).__name__}")
                    break
    await engine.dispose()
    print(f"schema reconciled — columns added: {added or 'none'}")


if __name__ == "__main__":
    asyncio.run(main())
