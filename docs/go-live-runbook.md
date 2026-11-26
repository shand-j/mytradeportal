# Go-Live Runbook — My Trade Portal Beta

Audience: whoever drives the deployment on go-live morning. Every step is
copy-pasteable. Local prerequisites: Docker Desktop, pnpm, the repo `.venv`.

For the Stripe payments launch gate (issue #44), run the dedicated checklist:
`docs/runbooks/go-live-checklist.md`.
Current scope and release authority are in [beta-readiness.md](beta-readiness.md).
The present decision is **no-go** until its gates pass. This runbook does not
authorise a release or replace live/device evidence.

---

## 1. What is shipping

- **Mobile iOS app** (`mobile/`) — trade + customer flows, AI quote intake,
  AI lead-triage chat, team invites + assignment on multi-seat plans, and
  Stripe Connect onboarding after its live gates pass.
- **Landing site and tenant portal** (`web/landing/new design/app`) — marketing,
  public intake, secure quote/invoice/payment pages, and customer portal.
- **Web back-office** (`web/app`) — available code, but not a required surface
  for the concierge beta while its Railway deployment is parked.
- **Certificates and offline mode are excluded.** The certificate prototype has
  no backend persistence and offline sync is not a real delivery mechanism;
  neither may be promised to beta users.
- **API** (`services/api`) — FastAPI, RLS-enforced multi-tenancy, structured
  JSON logs on stdout (request IDs, LLM call metrics), `/health` + `/ready`,
  the reminder scheduler (email quote/invoice chasers + SMS Works SMS appointment
  reminders), and dispatch guardrails on every assignment path.
- **AI features** — Quote Agent (guide-priced drafts from free text, catalogue
  grounding via Qdrant when embedding keys are configured, confidence +
  warnings + assumptions surfaced in both apps, edit-feedback instrumentation)
  and Lead Triage Agent (see loop below).
- **The customer quote loop (WOW path)** — on public submission the backend
  instantly acknowledges, then in the background: drafts an AI quote
  automatically, opens triage chat that acknowledges the stated problem and
  asks precise layperson questions (with multiple-choice quick-replies),
  extracts stated facts into the request, re-drafts the quote when the triage
  closes, and always ends in a clear closure: confident → "quote sent once
  reviewed"; unconfident after the final turn → "the electrician will call" +
  the lead is flagged **Requires callback** with AI-suggested call questions
  for the electrician, captured details, and a tap-to-call button.
- **Admin** (`services/admin`) — Django back-office.

Deliberately NOT in this release (post-beta): voice-to-quote, voice-to-EICR,
OCERP/BoQ (endpoints return 501), dashboard voice analytics, demand
forecasting. No UI path leads to any of these.

## 2. Environment variables to wire (production)

| Variable | Value / source | Service |
|---|---|---|
| `LLM_API_BASE` | `https://api.moonshot.ai/v1` | api |
| `LLM_API_KEY` | prod Kimi key (from 1Password) | api |
| `LLM_MODEL` | `openai/kimi-k2.6` | api |
| `LLM_TEMPERATURE` | leave UNSET/empty for kimi-k* — they 400 on any custom temperature (the code now also omits it automatically for `kimi-k*` models) | api |
| `LLM_TIMEOUT_SECONDS` | `180` — a full quote JSON from Kimi takes 60–120s; the 45s default times out mid-generation | api |
| `LLM_FOLLOWUP_MODEL` / `LLM_REFINE_MODEL` | fast model id (e.g. `gpt-4o-mini`) for the triage chat and refine routes — without them both inherit the flagship and blow their latency budgets | api |
| `LLM_VISION_MODEL` | only if `LLM_MODEL` cannot take image input; powers photo captioning on AI quotes | api |
| `EMBEDDING_MODEL` / `EMBEDDING_API_KEY` / `EMBEDDING_API_BASE` | OpenAI text-embedding-3-small key — enables catalogue grounding; without it quotes are guide-priced only (`retrieval_status: skipped_no_key`) | api |
| `AUTH_SECRET_KEY` | generate: `openssl rand -hex 32` — **not** the dev default | api, admin |
| `ALLOWED_ORIGINS` | `https://<web-domain>` (no wildcard) | api |
| `DATABASE_URL` / `REDIS_URL` / `QDRANT_URL` | Railway reference vars | api |
| `MINIO_*` | Railway reference vars | api |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_CONNECT_CLIENT_ID` / `STRIPE_PUBLISHABLE_KEY` | prod Stripe dashboard — customer→tradesperson card payments (Connect Express) | api |
| `SMSWORKS_API_TOKEN` (required) + optional `SMSWORKS_FROM_NUMBER` | SMS Works account JWT — tenant-name sender IDs; numeric sender only for reply-capable setups; unset degrades reminders to email/push | api |
| `SMSWORKS_DELIVERY_REPORT_URL` / `SMSWORKS_WEBHOOK_USERNAME` / `SMSWORKS_WEBHOOK_PASSWORD` | Delivery-report callback and optional Basic credentials for `POST /webhooks/smsworks`; partial Basic config returns 503 | api |
| `RESEND_FROM_EMAIL` / `RESEND_NO_REPLY_EMAIL` / `RESEND_WEBHOOK_SECRET` | see `docs/resend-config.md` — branded quotes@ sender, platform no-reply sender, bounce/failure webhook | api |
| `PUBLIC_DOCS_BASE_URL` / `PASSWORD_RESET_BASE_URL` | `https://www.mytradeportal.co.uk` — public token pages, Stripe bounce page, emailed reset/invite links | api |
| `CALENDAR_FEED_BASE_URL` | `https://api.mytradeportal.co.uk`; verify Apple Calendar subscription on device (#36/#181) | api |
| `paddle_billing` Railway Signal | `false` in staging and production for the free beta; no Paddle keys are needed for beta access | api |
| Paddle keys / webhook secret / `PADDLE_PRICE_ID_*` | retained only for later re-enablement; do not initiate Paddle checkout or price previews during beta | api |
| `VITE_API_BASE_URL` | `https://<api-domain>` (build arg) | web |
| `EXPO_PUBLIC_API_BASE_URL` | `https://<api-domain>` (EAS build) | mobile |
| `PLATFORM_STAFF_EMAILS` | comma-separated founder/ops emails allowed to read cross-tenant AI and beta analytics; empty denies everyone | api |
| `POSTHOG_API_KEY` / `POSTHOG_HOST` | optional server-side mirror; product analytics work without a client SDK or key | api |
| `VITE_APP_VERSION` | optional release/version string attached to browser events | web, landing |

`settings.validate_production()` fails the API boot fast if dev secrets or
wildcard CORS survive — if the API won't boot, check its logs first.

## 3. Deploy order (Railway)

1. Infra services: `postgres`, `redis`, `qdrant`, `minio` (IaC in
   `.railway/railway.ts`).
2. `api` — its preDeploy runs `scripts/init_api.py` → `scripts/init_db.py`
   (schema create/reconcile + RLS; idempotent).
3. `web` (production Dockerfile target — nginx static bundle).
4. `admin`, then `data-pipeline` (catalogue scrape for grounding).
5. Set domains; verify CORS origin matches the web domain exactly.

### Post-deploy smoke (5 minutes)

```bash
curl -s https://<api-domain>/health   # {"status":"ok","environment":"production"}
curl -s https://<api-domain>/ready    # {"status":"ready"} (degraded if qdrant down)
```

Then in the browser: sign up a fresh tenant → grab the customer quote-request
link → submit a request as a customer → confirm the AI triage question arrives
in chat → answer it → log in as the electrician → generate the AI quote →
refine it → send. That is the full "WOW" path end to end.

### Staging deploy queue recovery (non-production only)

Use this when Railway shows API/landing deploys stuck in `QUEUED` ("Waiting for
deployment slot") and staging preDeploy appears hung in `scripts/init_db.py`.

1. **Find blocking sessions (read-only SQL):**
   ```sql
   SELECT pid, usename, state, wait_event_type, wait_event,
          now() - xact_start AS xact_age, now() - query_start AS query_age
   FROM pg_stat_activity
   WHERE datname = current_database()
   ORDER BY xact_start NULLS LAST;
   ```
   Treat `state = 'idle in transaction'` with very old `xact_age` as potentially
   stale; active deploy work typically has recent `xact_start` and a changing
   wait pattern. Do not print raw query text: role DDL can contain credentials.
2. **Confirm who blocks whom:**
   ```sql
   SELECT blocked.pid AS blocked_pid,
          pg_blocking_pids(blocked.pid) AS blocking_pids,
          blocked.wait_event, now() - blocked.xact_start AS xact_age
   FROM pg_stat_activity blocked
   WHERE blocked.wait_event_type = 'Lock';
   ```
3. **With owner approval, clear only confirmed stale non-production sessions**
   using `SELECT pg_terminate_backend(<pid>);` for sessions idle in transaction,
   or restart the affected **staging** Railway service. `pg_cancel_backend` only
   cancels an active query and does not close an idle transaction. Do not
   terminate active work or run production mutations from this runbook.
4. Redeploy staging, then re-run preview smoke (`/health`, API smoke, landing smoke).

## 4. Logs (operational alerts are post-beta)

Logs are one JSON object per line on stdout — point the New Relic log
forwarder at stdout, index on `request_id`, `tenant_id`, `event`.

Key events: `http_request` (method/path/status/duration_ms/tenant_id),
`http_request_failed` (5xx + traceback), `llm_quote_generated` (model,
duration_ms, line_items, catalogue_items), `llm_followup_generated`
(confidence, complete), `llm_error`, `retrieval_completed` (status:
grounded/no_index), `embedding_generated` (cache_hits).

Configuring or verifying operational alert delivery (#62 and related work) is
explicitly outside the current beta release gate. Do not add it to deploy
prerequisites.

### Beta product analytics

Product analytics are separate from operational alerts and require no third-party
service. Server journey events and batched client events are stored as
`analytics.*` rows in the tenant-scoped `events` table:

- `POST /analytics/events` accepts up to 50 events per authenticated staff or
  customer batch. Mobile and browser clients flush up to 20 every 15 seconds,
  in the background and on lifecycle exits where possible.
- `POST /public/{kind}/{token}/analytics` accepts the same constrained batch only
  after validating the secure document token. Anonymous writes to a tenant are
  otherwise rejected.
- Payload keys are allow-listed. UUIDs/long path segments become `:id`; query
  strings are removed. Credentials, tokens, free-text customer content, raw error
  messages and stack traces are not collected.
- Successful API timing is sampled at 10%; instrumented API failures are always
  emitted. Queues are memory-only, so offline or fatal-crash delivery is
  best-effort rather than guaranteed.

Set `PLATFORM_STAFF_EMAILS` before trying to read the cross-tenant summaries.
With an authenticated platform-staff session, use:

- `GET /staff/ops/beta-analytics?days=30` for activation funnel conversion,
  active users/organisations/sessions, daily activity, top screens/actions,
  grouped errors, client performance and per-organisation activation.
- `GET /staff/ops/beta-events?days=7&limit=200` for newest-first raw drill-down;
  optionally filter `tenant_id` and `event_type` (for example
  `event_type=screen_view` or `event_type=error`).
- `GET /staff/ops/ai-costs` for the existing AI unit-economics leaderboard.

Verify ingestion against these staff reads on every release, as required by
`docs/beta-test-plan.md` §3.4. PostHog remains an optional server-side mirror;
there is no browser/mobile analytics SDK and no analytics secret in client builds.

## 5. Local bring-up for manual testing (morning)

```bash
docker compose up -d                 # full stack; web self-heals its node_modules
source .venv/bin/activate
python scripts/init_db.py            # if schema not yet applied
python scripts/seed_demo_estate.py   # idempotent; safe to re-run to reset
```

Note: the `admin` container runs gunicorn (no auto-reload) — after editing
anything under `services/admin/`, run `docker compose restart admin`.

Then open `docs/testing-accounts.md` — every login, the seeded-data map, and
the four prioritized test flows are there. Known local quirk: if a Homebrew
Postgres occupies `localhost:5432`, `localhost` connections land in the host
DB, not the Docker one (the seed script seeds both on this machine; see the
doc's caveat).

## 6. Tech-debt register (all measured in hours)

| Item | Impact | Effort |
|---|---|---|
| Certificates are excluded from beta UI; no certificate backend or persistence exists | No unsupported certificate issuance/persistence claim | Future scope (needs certificates API) |
| Voice features deferred (post-beta) | none — no UI leads to them | scoped separately |
| OCERP/BoQ parked (501) | none — UI removed | product decision |
| `web/app` mock layer (`src/lib/mock`, `dataStore`) is dead code | bundle weight only | 1–2 h |
| Mobile e2e suite covers the regression journeys (G-series) against a live backend but native-only UX (date wheels, push, deep links) stays manual — see `docs/beta-test-plan.md` §3 | less regression safety on device-only paths | ongoing |
| Other mobile screens share the `ScrollView flex-1` + fixed-footer pattern that hid QuoteEditScreen's send button on web (`ManualLeadScreen`, `FollowUpSettingsScreen`, …) — fine today, fragile if content grows | future layout bugs on web builds | 1–2 h |
| Kimi flagship latency (60–120s) is routed around for the chatty paths — triage follow-ups use `LLM_FOLLOWUP_MODEL` and refine uses `LLM_REFINE_MODEL`; only full generation stays on the flagship | slow first draft if the fast models are left unset | set the env vars; monitor |
| Demo/marketing video scripts lost their voice segments | re-record marketing assets | n/a (marketing) |
| Eval harness confidence calibration only meaningful in `--live` mode | offline evals can't judge calibration | n/a |

## 7. Running the mobile e2e suite (isolated stack)

The mobile regression suite runs its OWN backend stack and never touches the
demo stack:

```bash
cd mobile
pnpm e2e:install   # first time only
pnpm test:e2e      # full 7-group suite, video always recorded
```

- The suite stack (`docker-compose.mobile.yml`) runs as compose project
  `mtp-mobile-e2e` on dedicated host ports: api :8002, postgres :5433,
  redis :6380, qdrant :6335/6336, minio :9002/9003, mailpit :1026/8026,
  admin :8003. The demo stack stays on :8000 et al. — both can run at once.
- **Never** point the suite at :8000 or run it without its compose file: the
  suite expects rate limits disabled (it bulk-creates tenants) and an
  unseeded database. If manual testers report failed logins, check
  `docker ps` for `mtp_mobile_*` containers squatting on :8000 — that means
  someone bypassed the isolation.
- Videos land in `mobile/test-results/<group>/video.webm`.

## 8. Rollback

Railway: redeploy the previous deployment from the dashboard. `init_db.py`
only ever ADDS columns, so a rolled-back API works against the newer schema.
