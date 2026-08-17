#!/usr/bin/env bash
set -euo pipefail

# Run the mobile app in the iOS Simulator against the local Docker backend, for
# MANUAL TESTING. Brings up the API (dev mode + local auth + demo seed), then
# builds, installs, launches the app and starts Metro in CONNECTED mode so every
# wired screen talks to the real backend.
#
# Usage:
#   services/pwa/scripts/run-ios.sh ["iPhone 17"]
#
# Env toggles:
#   SKIP_BACKEND=1   Don't touch Docker (backend already up + seeded).
#   EXPO_PUBLIC_API_BASE_URL   Override the API URL (default http://localhost:8000).
#
# Demo login once it's running:
#   Electrician:  owner@demo.trade / demo123
#   Homeowner:    tap "Customer login" -> "Create an account", or enter code
#                 123456 at the entry to open the branded "Demo" flow.

SIM_NAME="${1:-iPhone 17}"
API_BASE_URL="${EXPO_PUBLIC_API_BASE_URL:-http://localhost:8000}"
# Any non-empty value: the dev API leaves POST /tenants open, so this simply
# enables the in-app "Register my business" flow to provision a real tenant.
SETUP_TOKEN_VALUE="${EXPO_PUBLIC_SETUP_TOKEN:-dev-manual-testing}"

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PWA_DIR="$REPO_ROOT/services/pwa"

# The iOS Simulator shares the host network, so http://localhost:8000 reaches the
# Docker-published API. A physical device would need the host's LAN IP instead.

# Point the toolchain at full Xcode (not the Command Line Tools) when present.
if [ -d "/Applications/Xcode.app/Contents/Developer" ]; then
  export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
fi

if [ "${SKIP_BACKEND:-0}" != "1" ]; then
  echo "==> Ensuring the backend is up and seeded (dev mode, local auth)..."
  bash "$PWA_DIR/e2e/start-stack.sh"
fi

echo
echo "==> Building and launching the app on the iOS Simulator"
echo "    Simulator : ${SIM_NAME}"
echo "    API (live): ${API_BASE_URL}"
echo "    Login     : owner@demo.trade / demo123 (electrician)"
echo
echo "    Keep this process running — it serves Metro (the JS bundle). Press"
echo "    Ctrl-C to stop. Re-run this script to relaunch."
echo

cd "$PWA_DIR"
EXPO_PUBLIC_API_BASE_URL="$API_BASE_URL" \
EXPO_PUBLIC_SETUP_TOKEN="$SETUP_TOKEN_VALUE" \
  pnpm exec expo run:ios --device "$SIM_NAME"
