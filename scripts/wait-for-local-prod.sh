#!/usr/bin/env bash
set -euo pipefail

# Wait for the local production replica to be healthy.

check_url() {
  local url="$1"
  local name="$2"
  local max="${3:-60}"
  echo "Waiting for ${name}..."
  for i in $(seq 1 "$max"); do
    if curl -sS -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q "200\|302"; then
      echo "${name} is healthy"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: ${name} did not become healthy" >&2
  return 1
}

check_url "http://demo.localhost:8000/health" "API"
check_url "http://demo.localhost:3000" "Web"
check_url "http://localhost:8001/admin/login/" "Admin"
check_url "http://localhost:6333/collections" "Qdrant"
check_url "http://localhost:9000/minio/health/live" "MinIO"
