#!/usr/bin/env bash
set -euo pipefail

# Full connected-mode E2E for the mobile app. Brings up the API stack + seed,
# then runs the trade and white-label suites sequentially. They use separate
# Expo builds (different EXPO_PUBLIC_* env), so they must not run at the same
# time — hence two sequential Playwright invocations on the same port.

cd "$(dirname "$0")/.."  # services/pwa

bash e2e/start-stack.sh

echo "== Running trade connected smoke =="
pnpm exec playwright test --config=playwright.config.ts "$@"

echo "== Running white-label smoke =="
pnpm exec playwright test --config=playwright.config.whitelabel.ts "$@"

echo "All mobile E2E suites passed."
