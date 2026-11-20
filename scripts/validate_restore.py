#!/usr/bin/env python3
"""Read-only validation for an isolated PostgreSQL/RustFS/Qdrant restore drill.

This script must only be pointed at an isolated estate. It never writes to
Postgres, object storage, or Qdrant. Credentials are supplied through environment
variables or command-line arguments and are not persisted by the script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.models import Base  # noqa: E402
from app.rls import TENANT_SCOPED_TABLES  # noqa: E402


def _http(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


def _require_ok(name: str, status: int, body: bytes) -> dict[str, Any]:
    if status < 200 or status >= 300:
        raise RuntimeError(f"{name}: HTTP {status}: {body[:500]!r}")
    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {"raw": body.decode("utf-8", "replace")[:500]}


def validate_ready(api_base: str) -> dict[str, Any]:
    status, body, _ = _http(f"{api_base.rstrip('/')}/ready")
    payload = _require_ok("/ready", status, body)
    if payload.get("status") != "ready":
        raise RuntimeError(f"/ready did not report ready: {payload}")
    checks = payload.get("checks", {})
    for dependency in ("postgres", "storage"):
        if checks.get(dependency) != "ok":
            raise RuntimeError(f"/ready {dependency} check failed: {payload}")
    return payload


def validate_api_reads(
    api_base: str,
    token: str,
    tenant_id: str,
    *,
    quote_id: str | None,
    job_id: str | None,
    invoice_id: str | None,
    file_key: str | None,
    business_slug: str | None,
    document_url: str | None,
) -> dict[str, Any]:
    headers = {
        "Authorization": "Bearer " + token,
        "X-Tenant-ID": tenant_id,
        "Accept": "application/json",
    }
    results: dict[str, Any] = {}
    for name, path in (
        ("quotes", "/quotes"),
        ("jobs", "/jobs"),
        ("invoices", "/invoices"),
    ):
        status, body, _ = _http(f"{api_base.rstrip('/')}{path}", headers=headers)
        _require_ok(name, status, body)
        payload = json.loads(body)
        results[name] = {"count": len(payload) if isinstance(payload, list) else None}

    for name, path in (
        ("quote_detail", f"/quotes/{quote_id}" if quote_id else None),
        ("job_detail", f"/jobs/{job_id}" if job_id else None),
        ("invoice_detail", f"/invoices/{invoice_id}" if invoice_id else None),
        (
            "media",
            f"/files/download?{urllib.parse.urlencode({'key': file_key})}"
            if file_key
            else None,
        ),
    ):
        if path:
            status, body, _ = _http(f"{api_base.rstrip('/')}{path}", headers=headers)
            _require_ok(name, status, body)
            results[name] = {
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }

    if business_slug:
        status, body, _ = _http(
            f"{api_base.rstrip('/')}/businesses/{urllib.parse.quote(business_slug)}/logo"
        )
        _require_ok("tenant_logo", status, body)
        results["tenant_logo"] = {
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    if document_url:
        status, body, _ = _http(document_url)
        _require_ok("public_document", status, body)
        results["public_document"] = {
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    return results


def validate_postgres(
    database_url: str,
    tenant_a: str | None,
    tenant_b: str | None,
) -> dict[str, Any]:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    missing_tables = sorted(set(Base.metadata.tables) - set(table_names))
    if missing_tables:
        raise RuntimeError(f"schema missing tables: {missing_tables}")

    missing_columns: dict[str, list[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in table_names:
            continue
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        missing = sorted(set(table.columns.keys()) - actual)
        if missing:
            missing_columns[table_name] = missing
    if missing_columns:
        raise RuntimeError(f"schema missing columns: {missing_columns}")

    counts: dict[str, int] = {}
    checksums: dict[str, str] = {}
    isolation: dict[str, Any] = {}
    with engine.begin() as connection:
        role = connection.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        if role.bypassrls or role.rolsuper:
            raise RuntimeError(
                "database validation role must not be superuser or BYPASSRLS; "
                "use the isolated app role"
            )
        connection.execute(text("SET app.bypass_rls = 'off'"))

        for table_name in sorted(table_names):
            count = connection.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')
            ).scalar_one()
            counts[table_name] = int(count)
            checksum = connection.execute(
                text(
                    f'SELECT md5(COALESCE(string_agg(md5(row_to_json(t)::text), '
                    f"'|'), '')) FROM "
                    f'(SELECT * FROM "{table_name}" LIMIT 10000) AS t'
                )
            ).scalar_one()
            checksums[table_name] = str(checksum or "")

        rls_missing = []
        for table_name in TENANT_SCOPED_TABLES:
            row = connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE oid = to_regclass(:table_name)"
                ),
                {"table_name": table_name},
            ).one_or_none()
            if row is None or not row.relrowsecurity or not row.relforcerowsecurity:
                rls_missing.append(table_name)
        if rls_missing:
            raise RuntimeError(f"tenant tables missing ENABLE/FORCE RLS: {rls_missing}")

        for tenant_id in (tenant_a, tenant_b):
            if not tenant_id:
                continue
            connection.execute(
                text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                {"tenant_id": tenant_id},
            )
            visible: dict[str, int] = {}
            for table_name in TENANT_SCOPED_TABLES:
                if table_name not in table_names:
                    continue
                visible_rows = connection.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar_one()
                visible[table_name] = int(visible_rows)
                foreign_rows = connection.execute(
                    text(
                        f'SELECT COUNT(*) FROM "{table_name}" '
                        "WHERE tenant_id::text <> "
                        "current_setting('app.current_tenant', true)"
                    )
                ).scalar_one()
                if int(foreign_rows) != 0:
                    raise RuntimeError(
                        f"tenant isolation failed for {tenant_id} in {table_name}: "
                        f"{foreign_rows} foreign rows visible"
                    )
            isolation[tenant_id] = visible
    engine.dispose()
    return {
        "counts": counts,
        "checksums": checksums,
        "rls": "ok",
        "tenant_isolation": isolation,
    }


def validate_qdrant(qdrant_url: str, collections: list[str]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for collection in collections:
        status, body, _ = _http(
            f"{qdrant_url.rstrip('/')}/collections/{urllib.parse.quote(collection)}"
        )
        payload = _require_ok(f"Qdrant collection {collection}", status, body)
        result = payload.get("result", {})
        points = result.get("points_count")
        if not isinstance(points, int):
            raise RuntimeError(f"Qdrant collection {collection} has no points_count")
        results[collection] = {"points_count": points}
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default=os.getenv("RESTORE_API_BASE_URL"))
    parser.add_argument("--database-url", default=os.getenv("RESTORE_DATABASE_URL"))
    parser.add_argument("--tenant-id")
    parser.add_argument("--tenant-a")
    parser.add_argument("--tenant-b")
    parser.add_argument("--auth-token", default=os.getenv("RESTORE_AUTH_TOKEN"))
    parser.add_argument("--quote-id")
    parser.add_argument("--job-id")
    parser.add_argument("--invoice-id")
    parser.add_argument("--file-key")
    parser.add_argument("--business-slug")
    parser.add_argument("--document-url")
    parser.add_argument("--qdrant-url", default=os.getenv("RESTORE_QDRANT_URL"))
    parser.add_argument(
        "--qdrant-collection",
        action="append",
        default=[],
        help="Expected Qdrant collection; repeat for multiple collections",
    )
    parser.add_argument("--evidence-json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_base:
        raise SystemExit("--api-base or RESTORE_API_BASE_URL is required")
    report: dict[str, Any] = {"ready": validate_ready(args.api_base)}

    if args.database_url:
        report["postgres"] = validate_postgres(
            args.database_url, args.tenant_a, args.tenant_b
        )
    if args.auth_token and args.tenant_id:
        report["api_reads"] = validate_api_reads(
            args.api_base,
            args.auth_token,
            args.tenant_id,
            quote_id=args.quote_id,
            job_id=args.job_id,
            invoice_id=args.invoice_id,
            file_key=args.file_key,
            business_slug=args.business_slug,
            document_url=args.document_url,
        )
    if args.qdrant_url and args.qdrant_collection:
        report["qdrant"] = validate_qdrant(args.qdrant_url, args.qdrant_collection)

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.evidence_json:
        Path(args.evidence_json).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RESTORE VALIDATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
