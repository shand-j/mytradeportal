#!/usr/bin/env bash
set -euo pipefail

# Run the full mobile regression suite against the FastAPI backend.

cd "$(dirname "$0")/.."  # mobile

pnpm exec playwright test --config=playwright.config.regression.ts "$@"
