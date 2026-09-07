#!/usr/bin/env bash
#
# One command to (re)generate the marketing demo videos for both journeys.
#
#   mobile/scripts/build-demo-videos.sh [electrician|customer|all]
#
# It will:
#   1. Start the Expo web dev server on :8084 if it isn't already running.
#   2. Record each journey with Playwright (raw webm + live-timed captions).
#   3. Composite each into a framed, captioned MP4 with intro/outro cards.
#
# Output: mobile/demo-video/<journey>-journey.mp4 (+ poster JPG)
#
# Requirements: node + playwright, python3 with Pillow, ffmpeg/ffprobe.
set -euo pipefail

JOURNEYS_ARG="${1:-all}"
PORT="${DEMO_PORT:-8084}"
BASE_URL="http://localhost:${PORT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PWA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PWA_DIR}/../.." && pwd)"

case "${JOURNEYS_ARG}" in
  all) JOURNEYS=(electrician customer) ;;
  electrician|customer) JOURNEYS=("${JOURNEYS_ARG}") ;;
  *) echo "Usage: $0 [electrician|customer|all]" >&2; exit 1 ;;
esac

# Resolve a Python interpreter (prefer the repo venv).
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PY="${REPO_ROOT}/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

STARTED_EXPO=0
EXPO_PID=""

cleanup() {
  if [[ "${STARTED_EXPO}" == "1" && -n "${EXPO_PID}" ]]; then
    echo "Stopping Expo web (pid ${EXPO_PID})"
    kill "${EXPO_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> Checking Expo web on ${BASE_URL}"
if curl -s -o /dev/null "${BASE_URL}/"; then
  echo "    Reusing already-running dev server."
else
  echo "    Starting Expo web dev server..."
  ( cd "${PWA_DIR}" && CI=1 npx expo start --web --port "${PORT}" >/tmp/expo-demo-web.log 2>&1 ) &
  EXPO_PID=$!
  STARTED_EXPO=1
  echo "    Waiting for bundler (pid ${EXPO_PID})..."
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null "${BASE_URL}/"; then break; fi
    sleep 2
  done
  if ! curl -s -o /dev/null "${BASE_URL}/"; then
    echo "Expo web did not come up on ${BASE_URL}; see /tmp/expo-demo-web.log" >&2
    exit 1
  fi
fi

for journey in "${JOURNEYS[@]}"; do
  echo "==> Recording ${journey} journey"
  DEMO_BASE_URL="${BASE_URL}" node "${SCRIPT_DIR}/record-demo-video.js" --journey="${journey}"
  echo "==> Composing ${journey} video"
  "${PY}" "${SCRIPT_DIR}/compose_demo_video.py" --journey "${journey}"
done

echo "==> Done. Videos in ${PWA_DIR}/demo-video/"
ls -1 "${PWA_DIR}/demo-video/"*.mp4
