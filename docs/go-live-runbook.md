# Go-Live Runbook — My Trade Portal Beta

Audience: whoever drives the deployment on go-live morning. Every step is
copy-pasteable. Local prerequisites: Docker Desktop, pnpm, the repo `.venv`.

---

## 1. What is shipping

- **Web back-office** (`web/app`) — CRM, quotes (incl. AI generate + refine),
  jobs, invoices, calendar, reviews, AI insights, settings.
- **Mobile iOS app** (`mobile/`) — trade + customer flows, AI quote intake,
  AI lead-triage chat, digital EICR certificates with BS 7671 validation,
  team invites + assignment on multi-seat plans, Stripe Connect onboarding in
  an in-app browser.
- **API** (`services/api`) — FastAPI, RLS-enforced multi-tenancy, structured
  JSON logs on stdout (request IDs, LLM call metrics), `/health` + `/ready`,
  the reminder scheduler (email quote/invoice chasers + Telnyx SMS appointment
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
| `TELNYX_API_KEY` + `TELNYX_FROM_NUMBER` or `TELNYX_MESSAGING_PROFILE_ID` | Telnyx Mission Control — SMS appointment reminders; unset degrades reminders to email/push | api |
| `TELNYX_PUBLIC_KEY` | Telnyx public key for `POST /webhooks/telnyx` (delivery receipts + STOP opt-outs; 503 until set) | api |
| `RESEND_FROM_EMAIL` / `RESEND_NO_REPLY_EMAIL` / `RESEND_WEBHOOK_SECRET` | see `docs/resend-config.md` — branded quotes@ sender, platform no-reply sender, bounce/failure webhook | api |
| `PUBLIC_DOCS_BASE_URL` / `PASSWORD_RESET_BASE_URL` | `https://www.mytradeportal.co.uk` — public token pages, Stripe bounce page, emailed reset/invite links | api |
| `CALENDAR_FEED_BASE_URL` | leave empty until the branded API domain lands (issue #181) | api |
| Paddle keys / webhook secret / `PADDLE_PRICE_ID_*` | prod Paddle dashboard | api |
| `VITE_API_BASE_URL` | `https://<api-domain>` (build arg) | web |
| `EXPO_PUBLIC_API_BASE_URL` | `https://<api-domain>` (EAS build) | mobile |

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

## 4. Observability (New Relic)

Logs are one JSON object per line on stdout — point the New Relic log
forwarder at stdout, index on `request_id`, `tenant_id`, `event`.

Key events: `http_request` (method/path/status/duration_ms/tenant_id),
`http_request_failed` (5xx + traceback), `llm_quote_generated` (model,
duration_ms, line_items, catalogue_items), `llm_followup_generated`
(confidence, complete), `llm_error`, `retrieval_completed` (status:
grounded/no_index), `embedding_generated` (cache_hits).

Suggested alerts: 5xx rate, `llm_error` count, p95 `duration_ms` on
`http_request` where path = `/quotes/generate`.

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
| Certificates have no backend persistence — drafts are local-only and lost on unmount; `CertificatesScreen` list is empty; no observations entry UI; max-Zs entered manually | EICR feature is on-site drafting/validation only | 4–8 h (needs certificates API) |
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
