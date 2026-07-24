#!/usr/bin/env python3
"""Wrapper that runs DB init followed by data-pipeline init in one preDeploy step.

Railway's preDeployCommand must be a single-element array, so this script lets us
sequence the two idempotent init scripts without relying on shell `&&`.
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
    print("[init_api] Done")
    print("[init_api] Note: cost data is populated by the data-pipeline service (manual or scheduled), not during API deploy.")
