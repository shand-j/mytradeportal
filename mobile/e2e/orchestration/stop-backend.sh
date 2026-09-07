#!/usr/bin/env bash
set -euo pipefail

# Stop the FastAPI backend stack started for mobile E2E regression.
# Set E2E_TEARDOWN=1 to also remove volumes (useful for CI).

REPO_ROOT="$(cd "$(dirname "$0")/../../../" && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILES="-f docker-compose.mobile.yml"

if [[ "${E2E_TEARDOWN:-0}" == "1" ]]; then
  echo "Tearing down backend stack and volumes..."
  docker compose ${COMPOSE_FILES} down -v
else
  echo "Stopping backend stack (keeping volumes)..."
  docker compose ${COMPOSE_FILES} stop
fi
