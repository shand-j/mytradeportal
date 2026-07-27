#!/usr/bin/env bash
set -e

# Start the local Docker Compose stack and bootstrap the E2E tenant/admin.
# Intended to be invoked by Playwright's webServer option.

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILES="-f docker-compose.yml"
API_BASE_URL="${E2E_API_BASE_URL:-http://demo.localhost:8000}"

cd "$(dirname "$0")/../../.."

# shellcheck source=/dev/null
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

if [ "${ENVIRONMENT:-development}" = "production" ]; then
  COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod-like.yml"
fi

docker compose ${COMPOSE_FILES} --env-file "${ENV_FILE}" up --build -d

if [ "${ENVIRONMENT:-development}" = "production" ] && [ -n "${APP_ROLE_PASSWORD:-}" ]; then
  echo "Syncing mtp_app role password for production-like startup..."
  ESCAPED_APP_ROLE_PASSWORD=${APP_ROLE_PASSWORD//\'/\'\'}
  docker compose ${COMPOSE_FILES} exec -T postgres \
    psql -U "${POSTGRES_USER:-mtp}" -d "${POSTGRES_DB:-mtp}" \
    -c "ALTER ROLE mtp_app WITH PASSWORD '${ESCAPED_APP_ROLE_PASSWORD}';" >/dev/null
  docker compose ${COMPOSE_FILES} restart api >/dev/null
fi

echo "Waiting for API health check..."
for i in {1..60}; do
  if curl -sS "${API_BASE_URL}/health" >/dev/null 2>&1; then
    echo "API is healthy"
    break
  fi
  sleep 2
done

./web/app/e2e/bootstrap-tenant.sh
