#!/usr/bin/env python3
"""One-time database initialisation for first production install.

Runs Alembic to create the API schema and Django migrate to create the
admin tables.  Both steps are idempotent, so the script is safe to run
on every deploy, but it is intended for the empty database before the
app goes live.

The script detects which toolchains are installed and only runs the
steps that apply to the current container:

- API container: has Alembic -> runs Alembic upgrade head
- Admin container: has Django -> runs manage.py migrate
- Local dev environment: has both -> runs both
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    env = {**os.environ, **(extra_env or {})}
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def init_api_schema() -> None:
    """Create/update the API schema via Alembic."""
    if shutil.which("alembic") is None:
        print("[init_db] alembic not available, skipping API schema")
        return

    alembic_ini = ROOT / "alembic.ini"
    if not alembic_ini.exists():
        print("[init_db] alembic.ini not found, skipping API schema")
        return

    api_dir = ROOT / "services" / "api"
    print("[init_db] Running Alembic upgrade head")
    _run(["alembic", "upgrade", "head"], cwd=ROOT, extra_env={"PYTHONPATH": str(api_dir)})


def init_admin_schema() -> None:
    """Create/update Django admin tables."""
    admin_dir = ROOT / "services" / "admin"
    manage_py = admin_dir / "manage.py"
    if not manage_py.exists():
        print("[init_db] Django manage.py not found, skipping admin schema")
        return

    print("[init_db] Running Django migrate")
    _run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=admin_dir,
        extra_env={"DJANGO_SETTINGS_MODULE": "admin_project.settings"},
    )


if __name__ == "__main__":
    init_api_schema()
    init_admin_schema()
    print("[init_db] Done")
