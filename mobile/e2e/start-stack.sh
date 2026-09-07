#!/usr/bin/env bash
set -euo pipefail

# Bring up the API stack (dev mode) and seed the connected-mode E2E data for the
# mobile app: the demo tenant + trade owner (matching the app's pre-filled login)
# plus one contact, one outstanding quote, and one scheduled job.
#
# Idempotent: safe to run repeatedly. Intended for local runs and CI.

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

API_BASE_URL="${E2E_API_BASE_URL:-http://localhost:8002}"
TENANT_SLUG="${E2E_TENANT_SLUG:-demo}"
TENANT_NAME="${E2E_TENANT_NAME:-Demo Electrical}"
ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-owner@demo.trade}"
ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-demo123}"
ADMIN_NAME="${E2E_ADMIN_NAME:-Demo Owner}"

# Dev stack: ENVIRONMENT=development keeps POST /tenants open (no setup token
# required) and lets the seed script run. docker-compose.mobile.yml blanks
# Supabase by default so auth is local bcrypt/JWT (self-contained, matches CI).
# Bring up the API and its dependencies.
export ENVIRONMENT=development
COMPOSE_FILES="-f docker-compose.mobile.yml"
echo "Starting mobile API stack (dev)..."
docker compose ${COMPOSE_FILES} up -d api

echo "Waiting for API health at ${API_BASE_URL}..."
for _ in $(seq 1 90); do
  status=$(curl -sS -o /dev/null -w "%{http_code}" "${API_BASE_URL}/health" 2>/dev/null || echo "000")
  if [ "${status}" -ge 200 ] && [ "${status}" -lt 300 ]; then
    echo "API is healthy"
    break
  fi
  sleep 2
done

echo "Seeding demo tenant + trade owner..."
docker compose ${COMPOSE_FILES} run --rm \
  -e SEED_TENANT_SLUG="${TENANT_SLUG}" \
  -e SEED_TENANT_NAME="${TENANT_NAME}" \
  -e SEED_ADMIN_EMAIL="${ADMIN_EMAIL}" \
  -e SEED_ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  -e SEED_ADMIN_NAME="${ADMIN_NAME}" \
  api python -m app.seed_admin_user

# Ensure the admin has a usable LOCAL password even if the row predates this
# e2e (e.g. a dev whose demo user was created against Supabase, leaving
# password_hash NULL). Idempotent and safe to re-run.
echo "Ensuring local admin password..."
docker compose ${COMPOSE_FILES} run --rm -T \
  -e SEED_ADMIN_EMAIL="${ADMIN_EMAIL}" \
  -e SEED_ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  api python - <<'PYEOF'
import asyncio
import os

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User
from app.rls import bypass_rls_in_session
from app.security import get_password_hash


async def main() -> None:
    email = os.environ["SEED_ADMIN_EMAIL"]
    password = os.environ["SEED_ADMIN_PASSWORD"]
    async with AsyncSessionLocal() as session:
        await bypass_rls_in_session(session)
        users = (await session.execute(select(User).where(User.email == email))).scalars().all()
        for user in users:
            user.password_hash = get_password_hash(password)
            user.supabase_uid = None
        await session.commit()
    print(f"Ensured local password for {email} ({len(users)} row(s))")


asyncio.run(main())
PYEOF

echo "Seeding E2E contact + quote + job..."
E2E_API_BASE_URL="${API_BASE_URL}" \
E2E_ADMIN_EMAIL="${ADMIN_EMAIL}" \
E2E_ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
E2E_TENANT_SLUG="${TENANT_SLUG}" \
  node "${REPO_ROOT}/mobile/e2e/seed-e2e.mjs"

echo "Stack ready."
