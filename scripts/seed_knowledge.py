#!/usr/bin/env python3
"""Seed the local ``quoting_knowledge`` Qdrant collection.

Thin wrapper around ``data_pipeline.knowledge_loader`` that puts the data
pipeline package on ``sys.path`` so this can run from the repo root without
installing anything, matching :mod:`scripts.seed_cost_items`.

Usage (from the repo root, with the repo venv active)::

    docker compose up -d qdrant
    source .venv/bin/activate
    python scripts/seed_knowledge.py                  # default: reset + embed
    python scripts/seed_knowledge.py --dry-run        # chunk only, no embed
    python scripts/seed_knowledge.py --no-reset       # overwrite by chunk id

Embeddings use the ``EMBEDDING_*`` env vars (falls back to ``OPENAI_API_KEY``).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SRC = ROOT / "services" / "data-pipeline" / "src"
if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

from data_pipeline.knowledge_loader import main  # noqa: E402

if __name__ == "__main__":
    main()
