#!/usr/bin/env python3
"""One-time data-pipeline initialisation for first production install.

Runs the curated seed loader and the knowledge loader so the Qdrant collections
(`cost_items`, `quoting_knowledge`) and Postgres `cost_items` table are
populated before the first AI quote is generated. Both loaders are idempotent,
so this script is safe to run on every deploy, but it is intended for the empty
pre-go-live environment.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# In the repo the package lives under services/data-pipeline/src; in the Docker
# image it lives at /app/src. Use whichever layout exists.
REPO_SRC = ROOT / "services" / "data-pipeline" / "src"
CONTAINER_SRC = ROOT / "src"
SRC_DIR = REPO_SRC if REPO_SRC.exists() else CONTAINER_SRC
SHARED_SRC = ROOT / "packages" / "shared" / "py"

if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if SHARED_SRC.exists() and str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))


def _run(cmd: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    env = {**os.environ, **(extra_env or {})}
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


async def _wait_for_qdrant(timeout: int = 120) -> None:
    """Wait until the configured Qdrant instance is reachable.

    Deploys are parallel, so Qdrant may not be listening when this script runs
    as part of the API preDeploy command.  A short wait avoids failing the
    whole deployment because of a brief race.
    """
    # Import here so the sys.path updates above take effect before module load.
    from data_pipeline.config import settings as dp_settings
    from data_pipeline.qdrant import get_qdrant_client

    qdrant = get_qdrant_client()
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            await qdrant.get_collections()
            print(f"[init_data_pipeline] Qdrant reachable at {dp_settings.qdrant_url}")
            return
        except Exception as exc:
            last_error = str(exc)
            print(f"[init_data_pipeline] Waiting for Qdrant... {last_error}")
            time.sleep(5)
    raise TimeoutError(f"Qdrant did not become reachable within {timeout}s: {last_error}")


def init_data_pipeline() -> None:
    """Run the curated seed and knowledge loaders."""
    if not SRC_DIR.exists():
        print("[init_data_pipeline] data-pipeline source not found, skipping")
        return

    if not SHARED_SRC.exists():
        print("[init_data_pipeline] shared package not found, skipping")
        return

    pythonpath = f"{SRC_DIR}:{SHARED_SRC}"
    env = {"PYTHONPATH": pythonpath}

    print("[init_data_pipeline] Waiting for Qdrant")
    asyncio.run(_wait_for_qdrant())

    print("[init_data_pipeline] Running load_curated_seed")
    _run(
        [sys.executable, "-m", "data_pipeline.load_curated_seed"],
        cwd=ROOT,
        extra_env=env,
    )

    print("[init_data_pipeline] Running knowledge_loader")
    _run(
        [sys.executable, "-m", "data_pipeline.knowledge_loader"],
        cwd=ROOT,
        extra_env=env,
    )


if __name__ == "__main__":
    init_data_pipeline()
    print("[init_data_pipeline] Done")
