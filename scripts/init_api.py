#!/usr/bin/env python3
"""Wrapper that runs production-safe bootstrap tasks as API preDeploy step.

Railway's preDeployCommand must be a single-element array, so this script lets us
run idempotent bootstrap scripts without relying on shell `&&`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(script_name: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script_name)], check=True)


if __name__ == "__main__":
    run("init_db.py")
    # Purge any legacy seed/curated_seed rows left over from previous deploys.
    # Idempotent: once removed this is a no-op on subsequent runs.
    run("cleanup_seed_data.py")
    print("[init_api] Done")
    print(
        "[init_api] Note: no catalogue seed is applied on deploy; the data-pipeline "
        "populates cost_items. The API healthcheck (/health/ready) gates traffic "
        "until the catalogue is populated."
    )
