#!/usr/bin/env bash
set -euo pipefail

# Local green-deploy validation pipeline.
#
# Builds the production Docker images, starts the local prod replica, runs
# the extensive Playwright prod-validation suite, and reports the result.
# The goal is that a green run locally guarantees a green deploy to Railway.

cd "$(dirname "$0")/.."

ENV_FILE=".env.prod-replica"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod-replica.yml"

# 1. Ensure the replica env file exists and is fresh.
if [ ! -f "$ENV_FILE" ]; then
  echo "Generating production-replica env from Railway..."
  ./scripts/generate-prod-replica-env.sh
fi

# 2. Build the production images.
echo "Building production images..."
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" build --parallel

# 3. Start the replica.
echo "Starting local production replica..."
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" up -d

# 4. Wait for health.
./scripts/wait-for-local-prod.sh

# 5. Run the extensive Playwright prod-validation suite.
echo "Running production validation Playwright suite..."
(
  cd web/app
  ENVIRONMENT=production \
  E2E_TENANT_SLUG="${E2E_TENANT_SLUG:-prod-validation}" \
  E2E_TENANT_NAME="${E2E_TENANT_NAME:-Prod Validation Electrical}" \
  E2E_ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-prod-validation@example.com}" \
  E2E_ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-prod-validation-password-123}" \
  E2E_ADMIN_NAME="${E2E_ADMIN_NAME:-Prod Validation Admin}" \
  npx playwright test --config=playwright.config.prod-replica.ts
)

# 6. Optional: tear down the stack when asked.
if [ "${GREEN_DEPLOY_DOWN:-true}" = "true" ]; then
  echo "Tearing down replica..."
  docker compose $COMPOSE_FILES --env-file "$ENV_FILE" down -v
fi

echo "Local green-deploy validation PASSED"
