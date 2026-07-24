#!/usr/bin/env python3
"""One-time data-pipeline initialisation for first production install.

Runs the curated seed loader and the knowledge loader so the Qdrant collections
(`cost_items`, `quoting_knowledge`) and Postgres `cost_items` table are
populated before the first AI quote is generated. Both loaders are idempotent,
so this script is safe to run on every deploy, but it is intended for the empty
pre-go-live environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    env = {**os.environ, **(extra_env or {})}
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def init_data_pipeline() -> None:
    """Run the curated seed and knowledge loaders."""
    # In the repo the package lives under services/data-pipeline/src; in the
    # Docker image it lives at /app/src. Use whichever layout exists.
    repo_src = ROOT / "services" / "data-pipeline" / "src"
    container_src = ROOT / "src"
    src_dir = repo_src if repo_src.exists() else container_src

    if not src_dir.exists():
        print("[init_data_pipeline] data-pipeline source not found, skipping")
        return

    shared_src = ROOT / "packages" / "shared" / "py"
    if not shared_src.exists():
        print("[init_data_pipeline] shared package not found, skipping")
        return

    pythonpath = f"{src_dir}:{shared_src}"
    env = {"PYTHONPATH": pythonpath}

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
