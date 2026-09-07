#!/usr/bin/env bash
set -euo pipefail

# Start the FastAPI backend stack for the mobile E2E regression suite.
# This script is idempotent: it will reuse already-running containers.
#
# Usage:
#   E2E_API_BASE_URL=http://localhost:8002 bash mobile/e2e/orchestration/start-backend.sh

REPO_ROOT="$(cd "$(dirname "$0")/../../../" && pwd)"
cd "$REPO_ROOT"

API_BASE_URL="${E2E_API_BASE_URL:-http://localhost:8002}"
COMPOSE_FILES="-f docker-compose.mobile.yml"

# Use development mode so the tenant seed script can run without a setup token.
export ENVIRONMENT=development

# E2E repeatedly logs in to create isolated tenants; the default per-IP
# auth rate limit would trip after a few groups, so disable it for this stack.
export RATE_LIMIT_ENABLED=false

# The local E2E stack uses bcrypt/JWT auth; do not let a host .env that points
# at Supabase override that.
export SUPABASE_URL=""
export SUPABASE_ANON_KEY=""
export SUPABASE_SERVICE_ROLE_KEY=""

# Kimi models reject a custom temperature; leave it blank so the backend omits
# the parameter entirely.
export LLM_TEMPERATURE=""

echo "Starting mobile backend stack..."
# Force-recreate the API container so it picks up the env vars exported above.
docker compose ${COMPOSE_FILES} up -d --force-recreate api

echo "Waiting for API health at ${API_BASE_URL}..."
for i in $(seq 1 90); do
  status=$(curl -sS -o /dev/null -w "%{http_code}" "${API_BASE_URL}/health" 2>/dev/null || echo "000")
  if [[ "${status}" -ge 200 && "${status}" -lt 300 ]]; then
    echo "API is healthy"
    break
  fi
  if [[ "${i}" -eq 90 ]]; then
    echo "API failed to become healthy within 180s" >&2
    exit 1
  fi
  sleep 2
done

# The /health endpoint responds before the database schema init is complete in
# dev mode. Wait for a request that touches the DB (and exercises the RLS
# bypass path) to succeed before declaring the stack ready.
echo "Waiting for API database readiness..."
for i in $(seq 1 60); do
  status=$(curl -sS -o /dev/null -w "%{http_code}" "${API_BASE_URL}/businesses/nonexistent/public-config" 2>/dev/null || echo "000")
  if [[ "${status}" -eq 404 ]]; then
    echo "API database is ready"
    break
  fi
  if [[ "${i}" -eq 60 ]]; then
    echo "API database failed to become ready within 120s" >&2
    exit 1
  fi
  sleep 2
done

echo "Backend stack ready."
