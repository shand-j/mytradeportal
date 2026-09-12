"""Regression tests for the pre-deploy schema reconciler.

Prior to this fix, ``scripts/init_db.py`` only called
``Base.metadata.create_all(conn)``, which never issues ``ALTER TABLE`` to
add newly declared columns on already-existing tables. That caused prod
smoke tests to fail with
``asyncpg.exceptions.UndefinedColumnError: column
bills_of_quantities.retrieval_evidence does not exist`` after we added new
JSONB columns to the models without running Alembic on Railway.

These tests prove that ``sync_missing_columns`` fixes that drift.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from app.config import settings
from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from types import ModuleType

    from sqlalchemy.engine import Engine

_REPO_ROOT = Path(__file__).resolve().parents[3]
_INIT_DB_PATH = _REPO_ROOT / "scripts" / "init_db.py"


def _load_init_db_module() -> ModuleType:
    """Import ``scripts/init_db.py`` as a module without side effects.

    The script reads ``os.environ["DATABASE_URL"]`` at import time, so tests
    must run under the same environment used by the rest of the suite (where
    ``DATABASE_URL`` is set by the docker-compose stack).
    """
    if "scripts_init_db" in sys.modules:
        return sys.modules["scripts_init_db"]
    spec = importlib.util.spec_from_file_location("scripts_init_db", _INIT_DB_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["scripts_init_db"] = module
    spec.loader.exec_module(module)
    return module


def _sync_engine() -> Engine:
    """Sync engine against the shared test DB, using the superuser URL."""
    # ``settings.database_url`` is the migrated test DB after conftest wiring.
    url = settings.database_url.replace("+asyncpg", "")
    return create_engine(url)


@pytest.mark.usefixtures("test_database_url")
def test_sync_missing_columns_adds_declared_column() -> None:
    """Declares a table missing a JSONB column, then reconciles it."""
    init_db = _load_init_db_module()

    metadata = MetaData()
    Table(
        "_recon_test_boq",
        metadata,
        Column("id", String, primary_key=True),
        # ``retrieval_evidence`` mirrors the shape of the column added by
        # alembic revision ``e41c9d3f9c21``: JSONB NOT NULL DEFAULT '{}'.
        Column(
            "retrieval_evidence",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
    )

    engine = _sync_engine()
    try:
        # Build the pre-drift schema: create the table without the
        # ``retrieval_evidence`` column so we can prove the reconciler adds it.
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS "_recon_test_boq"')
            conn.exec_driver_sql('CREATE TABLE "_recon_test_boq" (id text PRIMARY KEY)')

        with engine.begin() as conn:
            added = init_db.sync_missing_columns(conn, metadata)

        assert "_recon_test_boq.retrieval_evidence" in added

        # The column must actually exist and be usable.
        with engine.connect() as conn:
            live_cols = {c["name"] for c in inspect(conn).get_columns("_recon_test_boq")}
            assert "retrieval_evidence" in live_cols
            # SELECT must succeed with the default applied on insert.
            conn.exec_driver_sql("INSERT INTO \"_recon_test_boq\" (id) VALUES ('a')")
            row = conn.exec_driver_sql(
                "SELECT retrieval_evidence FROM \"_recon_test_boq\" WHERE id = 'a'"
            ).one()
            assert row[0] == {}

        # Running the reconciler again is a no-op.
        with engine.begin() as conn:
            added_again = init_db.sync_missing_columns(conn, metadata)
        assert added_again == []
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS "_recon_test_boq"')
        engine.dispose()


@pytest.mark.usefixtures("test_database_url")
def test_sync_missing_columns_skips_unknown_tables() -> None:
    """Tables declared on metadata but not present in the DB are ignored."""
    init_db = _load_init_db_module()

    metadata = MetaData()
    Table(
        "_recon_never_created",
        metadata,
        Column("id", String, primary_key=True),
        Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS "_recon_never_created"')
            added = init_db.sync_missing_columns(conn, metadata)
        assert added == []
    finally:
        engine.dispose()


@pytest.mark.usefixtures("test_database_url")
def test_sync_missing_columns_backfills_not_null_without_server_default() -> None:
    """NOT NULL columns without server_default are safely added on non-empty tables.

    Recent JSONB columns (e.g. ``retrieval_evidence``) declare
    ``nullable=False`` with a Python-side ``default=dict`` but no
    ``server_default``. Naively running ``ADD COLUMN ... NOT NULL`` would fail
    against a table that already contains rows. The reconciler adds the
    column as nullable, backfills existing rows with a synthesised default,
    then tightens to ``NOT NULL``.
    """
    init_db = _load_init_db_module()

    metadata = MetaData()
    Table(
        "_recon_test_not_null",
        metadata,
        Column("id", String, primary_key=True),
        # Mirrors the model definition of ``BillOfQuantities.retrieval_evidence``:
        # ``mapped_column(JSONB, default=dict, nullable=False)`` — no server_default.
        Column("retrieval_evidence", JSONB, default=dict, nullable=False),
    )

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS "_recon_test_not_null"')
            conn.exec_driver_sql('CREATE TABLE "_recon_test_not_null" (id text PRIMARY KEY)')
            # Row exists before the reconciler runs — proves backfill works.
            conn.exec_driver_sql("INSERT INTO \"_recon_test_not_null\" (id) VALUES ('existing')")

        with engine.begin() as conn:
            added = init_db.sync_missing_columns(conn, metadata)

        assert "_recon_test_not_null.retrieval_evidence" in added

        with engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT retrieval_evidence FROM \"_recon_test_not_null\" WHERE id = 'existing'"
            ).one()
            assert row[0] == {}

            # A fresh insert without providing the column must also succeed
            # thanks to the synthesised DEFAULT.
            conn.exec_driver_sql("INSERT INTO \"_recon_test_not_null\" (id) VALUES ('fresh')")
            row2 = conn.exec_driver_sql(
                "SELECT retrieval_evidence FROM \"_recon_test_not_null\" WHERE id = 'fresh'"
            ).one()
            assert row2[0] == {}

            # And the column must now enforce NOT NULL.
            with pytest.raises(IntegrityError):
                conn.exec_driver_sql(
                    'INSERT INTO "_recon_test_not_null" (id, retrieval_evidence) '
                    "VALUES ('nulled', NULL)"
                )
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS "_recon_test_not_null"')
        engine.dispose()


@pytest.mark.usefixtures("test_database_url")
def test_create_metabase_role_is_read_only_bypassrls_and_idempotent() -> None:
    """The BI role can log in, bypasses RLS, and holds SELECT-only privileges.

    Metabase (compose profile ``observability``) connects as ``mtp_metabase``;
    because RLS is ``FORCE``d on every tenant-scoped table the role must carry
    ``BYPASSRLS`` to see any rows, which makes its SELECT-only grants the only
    write protection. Running the creation step twice must be a no-op.
    """
    init_db = _load_init_db_module()

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            # Probe table created BEFORE the role so GRANT SELECT ON ALL TABLES
            # covers it — keeps the privilege assertions independent of whether
            # the app schema happens to exist in this database (CI vs local).
            conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS _recon_metabase_probe (id integer)")
            init_db._create_metabase_role(conn)
            # Idempotent: a second run (e.g. every preDeploy) must not fail.
            init_db._create_metabase_role(conn)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                    "FROM pg_roles WHERE rolname = :role"
                ),
                {"role": init_db.METABASE_ROLE},
            ).one()
            assert tuple(row) == (True, False, True, False, False)

            can_select = conn.execute(
                text("SELECT has_table_privilege(:role, 'public._recon_metabase_probe', 'SELECT')"),
                {"role": init_db.METABASE_ROLE},
            ).scalar_one()
            assert can_select is True

            can_insert = conn.execute(
                text("SELECT has_table_privilege(:role, 'public._recon_metabase_probe', 'INSERT')"),
                {"role": init_db.METABASE_ROLE},
            ).scalar_one()
            assert can_insert is False
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS _recon_metabase_probe")
        engine.dispose()
