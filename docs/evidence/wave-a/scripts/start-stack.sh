#!/usr/bin/env bash
# =============================================================================
# Wave A evidence — start the two app servers the capture needs.
#
#   1. The REAL FastAPI app on :8100 with Stripe network calls stubbed
#      (stubbed_api.py), email via local Mailpit, auth via local bcrypt.
#   2. The landing site (web/landing/new design/app — path contains a space)
#      Vite dev server on :5174, pointed at the stubbed API, WITHOUT
#      VITE_STRIPE_PUBLISHABLE_KEY so /pay/:token shows its documented
#      graceful-degradation state.
#
#   ./start-stack.sh        # foreground logs for both; Ctrl-C stops both
# =============================================================================
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPTS_DIR/../../../.." && pwd)"

export ENVIRONMENT=staging
export DATABASE_URL="postgresql+asyncpg://mtp:mtp@localhost:5432/mtp"
export REDIS_URL="redis://localhost:6379/0"
# --- mocked externals -------------------------------------------------------
export RESEND_API_KEY=""            # -> SMTP fallback to Mailpit on :1025
export SUPABASE_URL="" SUPABASE_ANON_KEY="" SUPABASE_SERVICE_ROLE_KEY=""
export STRIPE_SECRET_KEY="sk_test_evidence_stubbed"       # enables the code path only
export STRIPE_WEBHOOK_SECRET="whsec_evidence_local_test"  # real HMAC verification target
export PUBLIC_DOCS_BASE_URL="http://localhost:5174"
export ALLOWED_ORIGINS="http://localhost:5174,http://localhost:3000"
# Schedulers off: the docker API already runs them against the same database.
export REMINDER_SCHEDULER_ENABLED=false
export ROLLUP_SCHEDULER_ENABLED=false

cd "$REPO/services/api"
# Local dev DBs initialised before the Stripe work lack stripe_accounts.
"$REPO/.venv/bin/python" "$SCRIPTS_DIR/ensure_schema.py"
"$REPO/.venv/bin/python" "$SCRIPTS_DIR/stubbed_api.py" &
API_PID=$!

cd "$REPO/web/landing/new design/app"
VITE_API_URL="http://localhost:8100" npx vite --port 5174 --strictPort &
WEB_PID=$!

trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT
echo "stubbed API: http://localhost:8100  (pid $API_PID)"
echo "landing:     http://localhost:5174  (pid $WEB_PID)"
wait
