#!/usr/bin/env bash
set -e

# Start the local Docker Compose stack and seed the demo admin user.
# Intended to be invoked by Playwright's webServer option.

cd "$(dirname "$0")/../.."

docker compose up --build -d

echo "Waiting for API health check..."
for i in {1..60}; do
  if curl -sS http://demo.localhost:8000/health >/dev/null 2>&1; then
    echo "API is healthy"
    break
  fi
  sleep 2
done

docker compose run --rm api python -m app.seed_admin_user
