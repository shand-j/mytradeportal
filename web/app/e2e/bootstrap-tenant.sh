#!/usr/bin/env bash
set -e

# Bootstrap a tenant and first admin user for the Playwright E2E suite.
# In production mode this uses the SETUP_TOKEN-guarded POST /tenants endpoint;
# in development it falls back to the local seed script.

BOOTSTRAP_SLUG="${E2E_TENANT_SLUG:-demo}"
BOOTSTRAP_NAME="${E2E_TENANT_NAME:-Demo Electrical}"
ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-admin@demo.example.com}"
ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-e2e-password-123}"
ADMIN_NAME="${E2E_ADMIN_NAME:-Demo Admin}"
SETUP_TOKEN="${SETUP_TOKEN:-}"
DJANGO_USERNAME="${E2E_DJANGO_ADMIN_USERNAME:-superadmin}"
DJANGO_PASSWORD="${E2E_DJANGO_ADMIN_PASSWORD:-super-password-123}"

cd "$(dirname "$0")/../../.."

# shellcheck source=/dev/null
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

COMPOSE_FILES="-f docker-compose.yml"
if [ "${ENVIRONMENT:-development}" = "production" ]; then
  COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod-like.yml"
fi

wait_for_api() {
  echo "Waiting for API health check..."
  for i in {1..60}; do
    if curl -sS http://demo.localhost:8000/health >/dev/null 2>&1; then
      echo "API is healthy"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: API did not become healthy" >&2
  return 1
}

wait_for_admin() {
  echo "Waiting for admin health check..."
  for i in {1..60}; do
    if curl -sS -o /dev/null -w "%{http_code}" http://localhost:8001/admin/login/ | grep -q "200\|302"; then
      echo "Admin is reachable"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: Admin did not become reachable" >&2
  return 1
}

create_django_superuser() {
  echo "Ensuring Django superuser exists..."
  docker compose ${COMPOSE_FILES} exec -T admin python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_project.settings')
import django
django.setup()
from django.contrib.auth.models import User
if not User.objects.filter(username='${DJANGO_USERNAME}').exists():
    User.objects.create_superuser('${DJANGO_USERNAME}', '${ADMIN_EMAIL}', '${DJANGO_PASSWORD}')
    print('Django superuser created')
else:
    print('Django superuser already exists')
"
}

wait_for_api

if [ "${ENVIRONMENT:-development}" = "production" ]; then
  if [ -z "$SETUP_TOKEN" ]; then
    echo "ERROR: SETUP_TOKEN is required when ENVIRONMENT=production" >&2
    exit 1
  fi

  echo "Bootstrapping tenant '${BOOTSTRAP_SLUG}' via production API..."

  curl -sS -X POST "http://demo.localhost:8000/tenants" \
    -H "Content-Type: application/json" \
    -H "X-Setup-Token: ${SETUP_TOKEN}" \
    -d "{
      \"slug\": \"${BOOTSTRAP_SLUG}\",
      \"name\": \"${BOOTSTRAP_NAME}\",
      \"admin_email\": \"${ADMIN_EMAIL}\",
      \"admin_password\": \"${ADMIN_PASSWORD}\",
      \"admin_name\": \"${ADMIN_NAME}\"
    }" > /tmp/bootstrap-response.json

  if grep -q '"admin_user"' /tmp/bootstrap-response.json; then
    echo "Tenant '${BOOTSTRAP_SLUG}' bootstrapped with admin ${ADMIN_EMAIL}"
  elif grep -q '"Tenant slug already exists"' /tmp/bootstrap-response.json; then
    echo "Tenant '${BOOTSTRAP_SLUG}' already exists; continuing"
  else
    echo "ERROR: tenant bootstrap failed. Response:" >&2
    cat /tmp/bootstrap-response.json >&2
    exit 1
  fi
else
  echo "Running development seed script..."
  docker compose ${COMPOSE_FILES} run --rm api \
    python -m app.seed_admin_user
fi

wait_for_admin
create_django_superuser
