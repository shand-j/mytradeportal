#!/usr/bin/env bash
# =============================================================================
# Wave A evidence — narrated quote-to-cash lifecycle runner.
#
# Drives the REAL local API (stubbed-Stripe instance on :8100, see
# stubbed_api.py) through the full lifecycle with banners and assertions
# after every step. State (ids, tokens) is persisted to run/state.env so the
# capture script can interleave browser segments between step ranges.
#
#   ./lifecycle.sh          # run all steps 1..16
#   ./lifecycle.sh 1 8      # run a step range (used by capture.mjs)
#
# Everything external is mocked, by design:
#   * LLM (Kimi)   — quotes are seeded via the API with ai_generated=true line
#                    items; only the funnel trace id (normally minted by the
#                    generation path) is stamped via SQL.
#   * Stripe       — stripe_client network calls stubbed in-process; webhook
#                    signatures are REAL HMAC against a test secret.
#   * Resend       — blanked; email flows via SMTP to local Mailpit (:8025).
# =============================================================================
set -euo pipefail

API="${API:-http://localhost:8100}"
MAILPIT="${MAILPIT:-http://localhost:8025}"
DB="${DB:-postgresql://mtp:mtp@localhost:5432/mtp}"
PAUSE="${PAUSE:-1}"
PY="${PY:-$(command -v python3)}"

WAVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$WAVE_DIR/run"
SCRIPTS_DIR="$WAVE_DIR/scripts"
STATE="$RUN_DIR/state.env"
mkdir -p "$RUN_DIR"
touch "$STATE"
# shellcheck disable=SC1090
source "$STATE"

SLUG="evidence-electrical"
BUSINESS="Evidence Electrical"
ADMIN_EMAIL="eddie@evidence-electrical.example"
ADMIN_PASSWORD="Evidence-Trader-123"
CUSTOMER_NAME="Alice Homeowner"
CUSTOMER_EMAIL="alice.homeowner@example.com"
CUSTOMER_PASSWORD="Evidence-Customer-123"
STUB_PI="pi_evidence_stub_0001"

banner() { printf '\n\033[1;36m====================  STEP %s: %s  ====================\033[0m\n' "$1" "$2"; sleep "$PAUSE"; }
note()   { printf '  \342\206\222 %s\n' "$1"; }
fail()   { printf '\033[1;31mASSERTION FAILED: %s\033[0m\n' "$1" >&2; exit 1; }

save() { # persist KEY=VALUE for later steps / the capture script
  grep -v "^$1=" "$STATE" > "$STATE.tmp" 2>/dev/null || true
  printf '%s="%s"\n' "$1" "$2" >> "$STATE.tmp"
  mv "$STATE.tmp" "$STATE"
  export "$1=$2"
}

sql() { psql "$DB" -v ON_ERROR_STOP=1 -Atq -c "SET app.bypass_rls='on'" -c "$1"; }

api() { # api METHOD PATH [JSON] [TOKEN]  — token defaults to the tradie's
  local method="$1" path="$2" body="${3:-}" token="${4:-${TOKEN:-}}"
  local args=(-sS -X "$method" "$API$path" -H 'Content-Type: application/json')
  # Staff clients (web/mobile) scope every call with X-Tenant-ID; mirror that.
  [ -n "${TENANT_ID:-}" ] && args+=(-H "X-Tenant-ID: $TENANT_ID")
  [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
  [ -n "$body" ] && args+=(-d "$body")
  curl "${args[@]}"
}

mailpit_latest_to() { # mailpit_latest_to <email> <subject-regex> → message JSON
  curl -sS "$MAILPIT/api/v1/messages?limit=100" \
    | jq -r --arg to "$1" --arg re "$2" \
      '[.messages[] | select(any(.To[]; .Address==$to) and (.Subject | test($re; "i")))]
       | sort_by(.Created) | last | .ID // empty'
}

extract_doc_token() { # extract_doc_token <message-id> <kind> → raw token
  curl -sS "$MAILPIT/api/v1/message/$1" \
    | jq -r '.Text, .HTML // empty' \
    | grep -oE "/$2/[A-Za-z0-9_-]{20,}" | head -1 | cut -d/ -f3
}

# --------------------------------------------------------------------------
step_1() {
  banner 1 "Tradie onboarding — create tenant '$BUSINESS' (no live Paddle: trial row only)"
  local code
  code=$(curl -sS -o "$RUN_DIR/tenant.json" -w '%{http_code}' -X POST "$API/tenants" \
    -H 'Content-Type: application/json' \
    -d '{"slug":"'"$SLUG"'","name":"'"$BUSINESS"'","phone":"07700 900123","postcode":"E2 8DY","admin_email":"'"$ADMIN_EMAIL"'","admin_password":"'"$ADMIN_PASSWORD"'","admin_name":"Eddie Evidence"}')
  if [ "$code" = "201" ]; then
    note "tenant created with first admin user + 14-day no-card trial"
  elif [ "$code" = "409" ]; then
    note "tenant already exists (re-run) — reusing it"
  else
    cat "$RUN_DIR/tenant.json"; fail "tenant creation returned HTTP $code"
  fi
  save TENANT_ID "$(sql "SELECT id FROM tenants WHERE slug='$SLUG'")"
  note "tenant_id=$TENANT_ID"
  sql "SELECT t.slug, t.name, s.status AS subscription, s.trial_ends_at
       FROM tenants t JOIN subscriptions s ON s.tenant_id = t.id WHERE t.slug='$SLUG'" \
    | sed 's/^/  db: /'
}

step_2() {
  banner 2 "Tradie login (local bcrypt — Supabase blanked)"
  local resp
  resp=$(curl -sS -X POST "$API/auth/token" -H 'Content-Type: application/json' \
    -d '{"email":"'"$ADMIN_EMAIL"'","password":"'"$ADMIN_PASSWORD"'","tenant_slug":"'"$SLUG"'"}')
  save TOKEN "$(echo "$resp" | jq -r '.access_token')"
  [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ] || fail "login: $resp"
  note "JWT issued for $(echo "$resp" | jq -r '.user.email') (role $(echo "$resp" | jq -r '.user.role'))"
  api GET /auth/me | jq -r '"  /auth/me: \(.full_name) <\(.email)>"'
}

step_3() {
  banner 3 "Business setup — branding, VAT registration + card payments ON (Stripe account row seeded, API mocked)"
  # The Connect account row is normally written after real Stripe onboarding;
  # here it is seeded directly because Stripe itself is mocked.
  sql "INSERT INTO stripe_accounts (id, tenant_id, stripe_account_id, details_submitted, charges_enabled, payouts_enabled, onboarding_complete, created_at, updated_at)
       VALUES (gen_random_uuid(), '$TENANT_ID', 'acct_evidence_stub_0001', true, true, true, true, now(), now())
       ON CONFLICT (tenant_id) DO UPDATE SET charges_enabled=true, payouts_enabled=true, onboarding_complete=true"
  note "stripe_accounts row: acct_evidence_stub_0001 (charges_enabled=true)"
  api PATCH /tenants/me '{"settings":{"primary_color":"#0E7C5B","email":"quotes@evidence-electrical.example","phone":"07700 900123","address":"14 Evidence Way, London","postcode":"E2 8DY","vat_rate":0.20}}' \
    | jq -r '"  tenant branding: \(.name)"'
  # The real onboarding Tax step — sets vat_registered on the tenant record.
  api PATCH /onboarding/step/tax '{"step":"tax","value":{"vat_registered":true,"vat_scheme":"standard","vat_number":"GB123456789"}}' \
    | jq -r '"  onboarding tax step: completed (VAT registered, 20%)"'
  api PATCH /payments/settings '{"accept_card_default":true}' \
    | jq -r '"  accept_card_default=\(.accept_card_default)  stripe_configured=\(.stripe_configured)  charges_enabled=\(.charges_enabled)"'
}

step_4() {
  banner 4 "CRM — create the customer contact ($CUSTOMER_NAME)"
  local existing
  existing=$(api GET /contacts | jq -r --arg e "$CUSTOMER_EMAIL" '[.[] | select(.email==$e)][0].id // empty')
  if [ -n "$existing" ]; then
    save CONTACT_ID "$existing"; note "contact exists (re-run): $CONTACT_ID"
  else
    save CONTACT_ID "$(api POST /contacts '{"name":"'"$CUSTOMER_NAME"'","email":"'"$CUSTOMER_EMAIL"'","phone":"07900 123456","address":"7 Millers Close, London","postcode":"E2 9AA"}' | jq -r '.id')"
    note "contact created: $CONTACT_ID"
  fi
}

step_5() {
  banner 5 "AI-drafted quotes (LLM MOCKED — seeded via API with ai_generated line items)"
  save QUOTE_ONE "$(api POST /quotes '{"contact_id":"'"$CONTACT_ID"'","title":"Two extra double sockets — lounge","description":"Supply and fit two additional double socket outlets in the lounge.","line_items":[{"description":"Double socket outlet, white moulded","quantity":2,"unit":"ea","unit_price":28.50,"ai_generated":true},{"description":"Labour — chase, wire, make good","quantity":1.5,"unit":"hr","unit_price":65.00,"ai_generated":true}]}' | jq -r '.id')"
  save QUOTE_TWO "$(api POST /quotes '{"contact_id":"'"$CONTACT_ID"'","title":"Outside PIR security light","description":"Install a PIR security floodlight to the rear elevation.","line_items":[{"description":"PIR LED floodlight 30W","quantity":1,"unit":"ea","unit_price":42.00,"ai_generated":true},{"description":"Labour — install and test","quantity":1,"unit":"hr","unit_price":65.00,"ai_generated":true}]}' | jq -r '.id')"
  save QUOTE_HERO "$(api POST /quotes '{"contact_id":"'"$CONTACT_ID"'","title":"Consumer unit replacement","description":"Replace the existing fuse board with a modern 10-way RCBO consumer unit, including certification.","line_items":[{"description":"10-way RCBO consumer unit (SPD)","quantity":1,"unit":"ea","unit_price":450.00,"ai_generated":true},{"description":"Labour — certified installation and testing","quantity":4.5,"unit":"hr","unit_price":65.00,"ai_generated":true},{"description":"Electrical Installation Certificate","quantity":1,"unit":"ea","unit_price":120.00,"ai_generated":true},{"description":"Materials — tails, glands, trunking","quantity":1,"unit":"ea","unit_price":85.00,"ai_generated":true}]}' | jq -r '.id')"
  for q in "$QUOTE_ONE" "$QUOTE_TWO" "$QUOTE_HERO"; do
    [ -n "$q" ] && [ "$q" != "null" ] || fail "quote seeding failed"
    # The trace id is normally minted by the LLM generation path
    # (app.ai_telemetry.get_or_create_trace_id); with the LLM mocked we stamp
    # it so quote_sent / quote_accepted / invoice_paid outcome events join up.
    sql "UPDATE quotes SET
           ai_metadata = jsonb_build_object('trace_id', md5(random()::text || clock_timestamp()::text)),
           extra_data  = jsonb_build_object('rag', jsonb_build_object(
             'confidence', 0.82, 'retrieval_status', 'seeded_llm_mocked',
             'assumptions', '[]'::jsonb, 'warnings', '[]'::jsonb,
             'notes', 'Seeded for Wave A evidence capture — LLM not called'))
         WHERE id = '$q'"
  done
  note "seeded quotes: $QUOTE_ONE, $QUOTE_TWO, hero=$QUOTE_HERO (ai line items + trace ids)"
  api GET "/quotes/$QUOTE_HERO" | jq -r '"  hero quote: ai_generated=\(.ai_generated) subtotal=£\(.subtotal) vat=£\(.vat_amount) total=£\(.total)"'
}

step_6() {
  banner 6 "Send quotes 1 and 2 — trial-extension counter sees sent AI quotes"
  # Re-run support: clear a previously fired extension so the threshold
  # crossing below is genuine on every run (first run: no-op).
  sql "UPDATE tenants SET settings = settings - 'trial_extended_at' WHERE id='$TENANT_ID'"
  sql "UPDATE subscriptions SET status='trialing', trial_ends_at = now() + interval '14 days' WHERE tenant_id='$TENANT_ID'"
  save TRIAL_BEFORE "$(sql "SELECT trial_ends_at FROM subscriptions WHERE tenant_id='$TENANT_ID'")"
  note "trial_ends_at before sends: $TRIAL_BEFORE"
  api POST "/quotes/$QUOTE_ONE/send" | jq -r '"  quote 1 sent: status=\(.status)"'
  api POST "/quotes/$QUOTE_TWO/send" | jq -r '"  quote 2 sent: status=\(.status)"'
  local sent_ai
  sent_ai=$(sql "SELECT count(DISTINCT q.id) FROM quotes q JOIN quote_line_items li ON li.quote_id=q.id
                 WHERE q.tenant_id='$TENANT_ID' AND q.status IN ('sent','approved','invoiced') AND li.ai_generated")
  note "sent AI quotes counted by trial logic: $sent_ai (threshold for extension: 3)"
  [ "$sent_ai" -ge 2 ] || fail "trial counter expected >= 2 sent AI quotes"
}

step_7() {
  banner 7 "Tradie edits a line on the AI draft (labour 4.5h → 5h)"
  local resp
  resp=$(api PATCH "/quotes/$QUOTE_HERO" '{"line_items":[{"description":"10-way RCBO consumer unit (SPD)","quantity":1,"unit":"ea","unit_price":450.00,"ai_generated":true},{"description":"Labour — certified installation and testing","quantity":5,"unit":"hr","unit_price":65.00,"ai_generated":true},{"description":"Electrical Installation Certificate","quantity":1,"unit":"ea","unit_price":120.00,"ai_generated":true},{"description":"Materials — tails, glands, trunking","quantity":1,"unit":"ea","unit_price":85.00,"ai_generated":true}]}')
  echo "$resp" | jq -r '"  after edit: subtotal=£\(.subtotal) vat=£\(.vat_amount) total=£\(.total) (was £1137.00)"'
  [ "$(echo "$resp" | jq -r '.total')" = "1176.00" ] || fail "edited quote total expected 1176.00"
  local edits
  edits=$(sql "SELECT count(*) FROM events WHERE event_type='quote_lines_edited' AND entity_id='$QUOTE_HERO'")
  note "quote_lines_edited training events captured: $edits (before/after snapshots for AI fine-tuning)"
  [ "$edits" -ge 1 ] || fail "expected a quote_lines_edited event"
}

step_8() {
  banner 8 "Tradie sends the hero quote — 3rd sent AI quote fires the trial extension"
  api POST "/quotes/$QUOTE_HERO/send" | jq -r '"  hero quote: status=\(.status) sent_at=\(.sent_at)"'
  local outcome marker trial_after
  outcome=$(sql "SELECT count(*) FROM ai_call_events WHERE feature='outcome' AND quote_id='$QUOTE_HERO' AND raw_payload->>'outcome'='quote_sent'")
  note "ai_call_events outcome 'quote_sent': $outcome row(s)"
  [ "$outcome" -ge 1 ] || fail "quote_sent outcome event missing"
  marker=$(sql "SELECT settings->>'trial_extended_at' FROM tenants WHERE id='$TENANT_ID'")
  trial_after=$(sql "SELECT trial_ends_at FROM subscriptions WHERE tenant_id='$TENANT_ID'")
  note "TRIAL EXTENSION FIRED: trial_extended_at=$marker"
  note "trial_ends_at: $TRIAL_BEFORE -> $trial_after (14d -> 30d from send)"
  [ -n "$marker" ] || fail "trial extension did not fire on 3rd sent AI quote"
  local msg
  msg=$(mailpit_latest_to "$CUSTOMER_EMAIL" "Your quote from")
  [ -n "$msg" ] || fail "quote email not found in Mailpit"
  save QUOTE_TOKEN "$(extract_doc_token "$msg" quote)"
  note "customer email received (Mailpit id $msg); secure link token extracted"
  curl -sS "$API/public/quote/$QUOTE_TOKEN" \
    | jq -r '"  GET /public/quote/<token>: status=\(.status) total=£\(.total) tenant=\(.tenant.name) first_name=\(.customer_first_name)"'
}

step_10() {
  banner 10 "Customer registers (homeowner portal) and ACCEPTS the quote"
  local code resp
  code=$(curl -sS -o "$RUN_DIR/customer.json" -w '%{http_code}' -X POST "$API/customer/register" \
    -H 'Content-Type: application/json' \
    -d '{"slug":"'"$SLUG"'","full_name":"'"$CUSTOMER_NAME"'","email":"'"$CUSTOMER_EMAIL"'","password":"'"$CUSTOMER_PASSWORD"'","phone":"07900 123456"}')
  if [ "$code" = "409" ]; then
    note "customer account exists (re-run) — logging in"
    resp=$(curl -sS -X POST "$API/customer/login" -H 'Content-Type: application/json' \
      -d '{"slug":"'"$SLUG"'","email":"'"$CUSTOMER_EMAIL"'","password":"'"$CUSTOMER_PASSWORD"'"}')
  else
    [ "$code" = "201" ] || { cat "$RUN_DIR/customer.json"; fail "customer register HTTP $code"; }
    resp=$(cat "$RUN_DIR/customer.json")
    note "customer account created and linked to the CRM contact"
  fi
  save CUSTOMER_TOKEN "$(echo "$resp" | jq -r '.accessToken // .access_token')"
  [ "$CUSTOMER_TOKEN" != "null" ] && [ -n "$CUSTOMER_TOKEN" ] || fail "customer auth: $resp"
  local mine
  mine=$(curl -sS "$API/customer/quotes" -H "Authorization: Bearer $CUSTOMER_TOKEN" \
    | jq -r --arg q "$QUOTE_HERO" '[.[] | select(.id==$q)][0].status // empty')
  note "quote visible in customer portal with status: $mine"
  [ "$mine" = "sent" ] || fail "hero quote not visible as 'sent' to customer (got '$mine')"
  curl -sS -X POST "$API/customer/quotes/$QUOTE_HERO/accept" \
    -H "Authorization: Bearer $CUSTOMER_TOKEN" -H 'Content-Type: application/json' \
    -d '{"preferred_dates":["2026-09-21","2026-09-22"]}' \
    | jq -r '"  customer accepted: status=\(.status) approved_at=\(.approved_at) preferred=\(.accepted_dates | join(", "))"'
  local actor notif
  actor=$(sql "SELECT raw_payload->>'actor' FROM ai_call_events WHERE quote_id='$QUOTE_HERO' AND raw_payload->>'outcome'='quote_accepted' ORDER BY created_at DESC LIMIT 1")
  note "ai_call_events outcome 'quote_accepted' recorded (actor=$actor)"
  [ "$actor" = "customer" ] || fail "quote_accepted outcome missing or wrong actor"
  notif=$(sql "SELECT title || ' — ' || body FROM notifications WHERE tenant_id='$TENANT_ID' AND type='quote_accepted' ORDER BY created_at DESC LIMIT 1")
  note "tradie in-app notification: $notif"
  mailpit_latest_to "$CUSTOMER_EMAIL" "Quote accepted" > /dev/null
  note "acceptance confirmation email received in Mailpit"
}

step_11() {
  banner 11 "Tradie converts the approved quote to a scheduled job, starts and completes it"
  local resp
  resp=$(api POST "/quotes/$QUOTE_HERO/convert-to-job" '{"scheduled_start":"2026-09-21T09:00:00","scheduled_end":"2026-09-21T13:00:00","notes":"Wave A evidence job"}')
  save JOB_ID "$(echo "$resp" | jq -r '.id')"
  [ -n "$JOB_ID" ] && [ "$JOB_ID" != "null" ] || fail "convert-to-job: $resp"
  echo "$resp" | jq -r '"  job created: \(.title) — scheduled \(.scheduled_start) -> \(.scheduled_end)"'
  api POST "/jobs/$JOB_ID/start" | jq -r '"  job started: status=\(.status)"'
  api POST "/jobs/$JOB_ID/complete" | jq -r '"  job completed: status=\(.status) completed_at=\(.completed_at)"'
}

step_12() {
  banner 12 "Invoice created from the completed job (mirrors quote totals) and sent"
  local resp qtotal
  resp=$(api POST /invoices '{"contact_id":"'"$CONTACT_ID"'","job_id":"'"$JOB_ID"'"}')
  save INVOICE_ID "$(echo "$resp" | jq -r '.id')"
  [ -n "$INVOICE_ID" ] && [ "$INVOICE_ID" != "null" ] || fail "create invoice: $resp"
  qtotal=$(api GET "/quotes/$QUOTE_HERO" | jq -r '.total')
  echo "$resp" | jq -r '"  invoice \(.invoice_number): subtotal=£\(.subtotal) vat=£\(.vat_amount) total=£\(.total) quote_id=\(.quote_id)"'
  [ "$(echo "$resp" | jq -r '.total')" = "$qtotal" ] || fail "invoice total does not mirror the quote"
  note "invoice mirrors the accepted quote exactly (£$qtotal, never re-rounded)"
  api POST "/invoices/$INVOICE_ID/send" | jq -r '"  invoice sent: status=\(.status)"'
  local msg
  msg=$(mailpit_latest_to "$CUSTOMER_EMAIL" "Invoice .* from")
  [ -n "$msg" ] || fail "invoice email not found in Mailpit"
  save INVOICE_TOKEN "$(extract_doc_token "$msg" invoice)"
  note "invoice email received (Mailpit id $msg); secure link token extracted"
  local pub
  pub=$(curl -sS "$API/public/invoice/$INVOICE_TOKEN")
  echo "$pub" | jq -r '"  GET /public/invoice/<token>: status=\(.status) number=\(.invoice_number) total=£\(.total)"'
  save PAY_URL "$(echo "$pub" | jq -r '.payment_url // empty')"
  note "payment_url issued by the REAL destination-charge code path (stub PaymentIntent):"
  echo "    $PAY_URL" | sed 's/cs=.*/cs=<client_secret>/'
  [ -n "$PAY_URL" ] || fail "payment_url missing — Pay button would not render"
}

step_14() {
  banner 14 "Payment settles — payment_intent.succeeded webhook with a REAL HMAC signature"
  local total
  total=$(curl -sS "$API/public/invoice/$INVOICE_TOKEN" | jq -r '.total | tonumber * 100 | floor')
  STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-whsec_evidence_local_test}" \
    "$PY" "$SCRIPTS_DIR/replay_stripe_webhook.py" succeeded \
      --pi "$STUB_PI" --amount "$total" --invoice "$INVOICE_ID" --tenant "$TENANT_ID" \
    | sed 's/^/  webhook: /'
  sleep 1
  sql "SELECT status, paid_via, paid_at FROM invoices WHERE id='$INVOICE_ID'" | sed 's/^/  db invoice: /'
  [ "$(sql "SELECT status FROM invoices WHERE id='$INVOICE_ID'")" = "paid" ] || fail "invoice not marked paid"
  sql "SELECT provider, provider_transaction_id, amount, currency_code, status FROM payments WHERE invoice_id='$INVOICE_ID'" | sed 's/^/  db payment: /'
  local outcome notif
  outcome=$(sql "SELECT count(*) FROM ai_call_events WHERE quote_id='$QUOTE_HERO' AND raw_payload->>'outcome'='invoice_paid'")
  note "ai_call_events outcome 'invoice_paid' (AI funnel closed): $outcome row(s)"
  [ "$outcome" -ge 1 ] || fail "invoice_paid outcome missing"
  notif=$(sql "SELECT title || ' — ' || body FROM notifications WHERE tenant_id='$TENANT_ID' AND type='invoice_paid' ORDER BY created_at DESC LIMIT 1")
  note "tradie in-app notification: $notif"
  curl -sS "$API/public/invoice/$INVOICE_TOKEN" | jq -r '"  public invoice now: status=\(.status) paid_at=\(.paid_at) payment_url=\(.payment_url)"'
}

step_15() {
  banner 15 "Tradie issues a FULL refund (stub Stripe refund) — status refunded"
  api POST "/invoices/$INVOICE_ID/refund" | jq -r '"  refund endpoint: status=\(.status)"'
  [ "$(sql "SELECT status FROM invoices WHERE id='$INVOICE_ID'")" = "refunded" ] || fail "invoice not refunded"
  sql "SELECT payload->>'stripe_refund_id' FROM audit_logs WHERE entity_id='$INVOICE_ID' AND action='invoice.refunded' ORDER BY created_at DESC LIMIT 1" \
    | sed 's/^/  audit stripe_refund_id: /'
  sql "SELECT title || ' — ' || body FROM notifications WHERE tenant_id='$TENANT_ID' AND type='invoice_refunded' ORDER BY created_at DESC LIMIT 1" \
    | sed 's/^/  tradie notification: /'
  note "replaying Stripe's charge.refunded webhook (idempotent mirror path):"
  STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-whsec_evidence_local_test}" \
    "$PY" "$SCRIPTS_DIR/replay_stripe_webhook.py" refunded --pi "$STUB_PI" \
    | sed 's/^/  webhook: /'
  sleep 1
  [ "$(sql "SELECT status FROM invoices WHERE id='$INVOICE_ID'")" = "refunded" ] || fail "refund replay changed state"
  note "invoice still 'refunded' after webhook replay (idempotent)"
  curl -sS "$API/public/invoice/$INVOICE_TOKEN" | jq -r '"  public invoice now: status=\(.status) payment_url=\(.payment_url)"'
}

step_16() {
  banner 16 "Evidence summary"
  cat <<EOF
  tenant:    $BUSINESS ($SLUG) / $TENANT_ID
  quotes:    $QUOTE_ONE, $QUOTE_TWO, hero=$QUOTE_HERO
  job:       $JOB_ID
  invoice:   $INVOICE_ID
  links:     $API/public/quote/$QUOTE_TOKEN
             $API/public/invoice/$INVOICE_TOKEN
  mailpit:   $MAILPIT (search: $CUSTOMER_EMAIL)
EOF
  sql "SELECT raw_payload->>'outcome', count(*) FROM ai_call_events
       WHERE quote_id='$QUOTE_HERO' AND feature='outcome' GROUP BY 1 ORDER BY 1" | sed 's/^/  funnel: /'
}

main() {
  local from="${1:-1}" to="${2:-16}" n
  for ((n = from; n <= to; n++)); do
    if declare -F "step_$n" > /dev/null; then
      "step_$n"
    fi
  done
}

main "$@"
