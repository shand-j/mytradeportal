#!/usr/bin/env bash
set -euo pipefail

# Start the local production replica stack: same env vars and external
# dependencies as production, same Docker images and compute limits.
#
# Usage:
#   ./scripts/prod-replica-up.sh          # build and start
#   ./scripts/prod-replica-up.sh --down   # stop and remove volumes

cd "$(dirname "$0")/.."

ENV_FILE=".env.prod-replica"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod-replica.yml"

if [ "${1:-}" = "--down" ]; then
  echo "Stopping local production replica..."
  docker compose $COMPOSE_FILES --env-file "$ENV_FILE" down -v
  exit 0
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Run ./scripts/generate-prod-replica-env.sh first." >&2
  exit 1
fi

# Build images
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" build --parallel

# Start the stack
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" up -d

echo "Local production replica is starting. Wait for health checks..."
./scripts/wait-for-local-prod.sh

echo "Replica is up:"
echo "  API:    http://demo.localhost:8000"
echo "  Web:    http://demo.localhost:3000"
echo "  Admin:  http://localhost:8001/admin"
echo "  Qdrant: http://localhost:6333"
echo "  MinIO:  http://localhost:9001"
