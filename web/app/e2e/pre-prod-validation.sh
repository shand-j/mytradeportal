#!/usr/bin/env bash
set -euo pipefail

# Standardized pre-run for production-like Playwright validation:
# 1) load env, 2) flush limiter/cache state, 3) deterministic tenant/admin bootstrap.

ENV_FILE="${ENV_FILE:-.env.prod-like}"
export ENVIRONMENT="${ENVIRONMENT:-production}"

cd "$(dirname "$0")/../../.."

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
set -a
. "$ENV_FILE"
set +a

export ENV_FILE
export E2E_TENANT_SLUG="${E2E_TENANT_SLUG:-prodlike1}"
export E2E_ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-prodlike1@example.com}"
export E2E_ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-e2e-password-123}"
export E2E_DJANGO_ADMIN_USERNAME="${E2E_DJANGO_ADMIN_USERNAME:-superadmin}"

if [ -z "${E2E_DJANGO_ADMIN_PASSWORD:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  export E2E_DJANGO_ADMIN_PASSWORD="$DJANGO_SUPERUSER_PASSWORD"
fi

if [ "$ENVIRONMENT" = "production" ] && [ -z "${SETUP_TOKEN:-}" ]; then
  echo "ERROR: SETUP_TOKEN is required for production bootstrap" >&2
  exit 1
fi

COMPOSE_FILES="-f docker-compose.yml"
if [ "$ENVIRONMENT" = "production" ]; then
  COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod-like.yml"
fi

echo "[pre-prod-validation] Flushing Redis limiter/cache state..."
docker compose ${COMPOSE_FILES} --env-file "$ENV_FILE" exec -T redis redis-cli FLUSHALL >/dev/null

echo "[pre-prod-validation] Bootstrapping deterministic tenant/admin..."
./web/app/e2e/bootstrap-tenant.sh

echo "[pre-prod-validation] Ready for Playwright production validation."
