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

    seed_script = ROOT / "scripts" / "seed_minimum_catalog.py"
    if seed_script.exists():
        run("seed_minimum_catalog.py")
        print(
            "[init_api] Note: minimum catalogue seed applied; data-pipeline still enriches full pricing."
        )
    else:
        print("[init_api] Note: no seed_minimum_catalog.py found; skipping catalogue seed.")

    print("[init_api] Done")
