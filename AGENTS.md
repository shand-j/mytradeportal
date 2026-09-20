# AGENTS.md — My Trade Portal

This file is written for AI coding agents who need to understand the project as it
exists in the working tree. The pivot is complete: the backend services
(`services/api`, `services/admin`, `services/data-pipeline`) are present, and the
old `services/pwa` Expo app has been replaced by the React Native + Expo iOS app
under `mobile/`. The only remaining references to deleted services are
commented-out `services/ocerp` blocks (see "Known issues"), so treat this document
as the source of truth for the *current* layout.

---

## Project overview

**My Trade Portal** is a field-service management product for UK electricians and
trade businesses. The current working tree contains:

- **`services/api/`** — the FastAPI backend (SQLAlchemy + asyncpg, RLS-enforced
  multi-tenancy). Includes the provider-agnostic LLM quote pipeline in
  `app/rag/` (retrieval, generation, validation) and the golden-set eval harness
  in `services/api/evals/` (see "AI quote pipeline" below).
- **`services/admin/`** — the Django admin back-office.
- **`services/data-pipeline/`** — the Apify/Screwfix cost-item scraper that feeds
  the Qdrant catalogue used by the quote pipeline.
- **`mobile/`** — the active React Native + Expo iOS app. It serves both the
tradesperson and homeowner/customer flows against the real FastAPI backend
(connected mode only — the old in-app demo/mock-data mode has been removed),
and uses a white-label theme system.
- **`web/app/`** — a React + Vite back-office SPA. It implements the tradesperson
dashboard, CRM, quotes, jobs, invoices, calendar, reviews, AI insights, and settings.
- **`web/landing/`** — the marketing site (active app: Vite + React at
  `web/landing/new design/app`; the old Next.js directory is unused). One bundle,
  host-aware: `www`/apex serves marketing, pricing, blog, the interactive quote
  demo, and the secure token pages (`/quote/:token`, `/invoice/:token`,
  `/pay/:token`, `/fair-use`, `/reset-password`); **`{tenant-slug}.mytradeportal.co.uk`
  serves the tenant-branded customer portal** (portal mode, `src/portal/`) —
  invisible magic-link auth, quote-request form with inline AI triage check,
  quote accept/decline/discuss, bookings, invoice pay, branded password reset.
  See `docs/decisions/ADR-004-tenant-subdomain-portal.md`.
- **`packages/shared/ts/`** — shared TypeScript design tokens and utilities used by
`mobile/` and `web/app/`.
- **`packages/shared/py/mtp_shared/`** — shared Python primitives (Pydantic models,
settings, logging, tenancy helpers), installed as an editable package via
`pyproject.toml` and used by the Python services.
- **`security/`** — security testing harness (OWASP, multi-tenancy, SOC2 evidence).
It targets the FastAPI API, so it is most useful when run against a live deployed
backend.
- **`docs/`** — active documentation: the Beta PRD (`prd-beta.md`), the October
beta test plan (`beta-test-plan.md` — the current verification map), the go-live
runbook, testing accounts/seeded estate, payments money model, data retention,
CI hard rules, the SOC2 controls catalogue, the RN stack report, and alert
runbooks in `docs/runbooks/`. Legacy docs remain in `docs/archived/`.

### AI quote pipeline

The Quote Agent (`services/api/app/rag/`) generates guide-priced, ex-VAT line
items from free-text job descriptions via LiteLLM against any OpenAI-compatible
endpoint (Kimi/Moonshot via `LLM_API_BASE`). Recent additions:

- `QuoteRead` now exposes AI metadata: `ai_generated`, `ai_confidence`,
`ai_warnings`, `ai_assumptions`, `ai_notes`, and `retrieval_status`
(derived from the per-line flag and `quote.extra_data["rag"]`).
- Photo observations (issue #186): photos attached to a quote request
(`MediaAsset`) are captioned by a vision call in `services/api/app/rag/vision.py`
(fail-open, model = `LLM_VISION_MODEL` or `LLM_MODEL`; MinIO objects are fetched
server-side and inlined as base64 data URLs since MinIO is private-network-only).
The captions are rendered into the generation prompt as confirmed site facts —
so the draft's assumptions must not contradict them — and stored on
`quote.extra_data["rag"]["observations"]`, surfaced on `QuoteRead` as
`ai_observations`.
- `POST /quotes/{id}/refine` accepts electrician instructions and regenerates the
AI-drafted line items, preserving any manually added/edited lines. Rate limited
like `/generate`.
- **Model routing** (issues #198/#217/#227): `LLM_MODEL` is the flagship model
used for full quote generation. Latency-sensitive paths route to cheaper fast
models via separate knobs — `LLM_REFINE_MODEL` for `/quotes/{id}/refine` and
`LLM_FOLLOWUP_MODEL` for the triage follow-up chat (each with its own
timeout/retry settings; empty inherits `LLM_MODEL`). `LLM_VISION_MODEL` covers
photo captioning (above), and `INTAKE_TRIAGE_MODEL` the portal form's inline
triage check.
- `services/api/evals/` is a golden-set eval harness: 15 representative UK
domestic jobs scored on kind coverage, keyword hit-rate, guide price band, and
line-count sanity. Offline mode replays canned fixtures (no API keys); `--live`
calls the real LLM. Run it from `services/api` with `python -m evals.run_evals`.
- Quotes carry `estimated_hours` (working hours): AI generation asks the LLM
for a quote-level estimate and falls back to summing time-billed line items
(hour/day units); manual quotes can set it via `POST/PATCH /quotes`.
`QuoteRead.is_multi_day` derives it against the tenant's daily working hours.
`services/api/app/work_blocks.py` is the shared planner: when the duration
exceeds the daily hours, job create/convert caps day 1 and books the
remaining consecutive working-day blocks as appointments; job reschedules
shift those block appointments by the same delta. `GET /jobs/suggest-schedule`
(`quote_id=` or `hours=`) returns the earliest start where the whole block
sequence fits around existing appointments and scheduled jobs.

### Quote acceptance date preferences and draft jobs (issue #179)

On the emailed quote page (`/quote/:token` on the landing site) the customer
picks up to 3 ranked date/time-window preferences against an
availability-aware calendar. The API behind it:

- `GET /public/quote/{token}/availability` — token-scoped free/busy summary
BY DATE (`available`/`partial`/`busy`/`closed` + the quote's
`estimated_hours`). Deliberately coarse: no booking details ever leave it.
- `POST /public/quote/{token}/preferences` — stores the ranked choices on
`quote.accepted_dates` ("YYYY-MM-DD" or "YYYY-MM-DD (morning)"; parser in
`app/preferred_dates.py`), usable before or after acceptance.
- Acceptance with preferences (`apply_quote_acceptance`) auto-creates a
tentative DRAFT job (`status="draft"`) pre-filled with the 1st choice;
`POST /convert-to-job` adopts and confirms it in place (other existing jobs
still 409). Draft jobs never block the calendar and never trigger the
booking-confirmed email — the free/busy math shared by staff and public
availability lives in `app/availability.py` and excludes them. The mobile
job-create screen shows the quote's preferences as tappable chips so the
electrician lands on the 2nd/3rd choice when the 1st doesn't fit.

### Team gating, invites and sole-staff auto-assignment (issues #190/#191/#192)

Plan tiers cap staff seats (`Plan.seats`: sole_trader 1, pro 5, team 15 —
enforced by `POST /users/invite`). Admins invite staff via
`POST /users/invite` (409 when the seat cap is reached); the invitee sets
their password from a single-use emailed link (`POST /users/accept-invite`,
links built on `PASSWORD_RESET_BASE_URL`, TTL `INVITE_TOKEN_TTL_DAYS`, and
requesting a fresh link via `POST /users/invite/magic-link` revokes earlier
ones). Invite emails embed the public TestFlight link when `TESTFLIGHT_URL`
is set. Assignment is only meaningful on multi-seat plans, so every
job-creation path (`POST /jobs`, quote convert-to-job, the acceptance-time
draft job) and `POST /appointments` defaults `assigned_user_id` to the
tenant's ONLY active user when none is supplied
(`app.dependencies.single_active_user`); explicit assignees are validated and
always win. Seat context reaches clients via `GET /billing/subscription`,
which now carries `seats` (plan catalog, legacy keys resolved) and
`seats_in_use` (active users + pending invites — the same count the invite
endpoint gates on). The mobile app gates its assignee pickers on the simpler
equivalent signal: the pickers (job create, job detail) render only when
`GET /users` returns more than one active user, and the calendar shows its
All/Me assignee filter only on multi-seat plans ("Me" narrows server-side).

### Telnyx SMS appointment reminders (issues #169/#243)

`services/api/app/appointment_reminders.py` texts the customer AND the
assigned electrician before each appointment (default windows 24h and 2h) via
the Telnyx Messaging API (`app/sms.py` — fail-open like the email layer;
UK-aware E.164 normalisation, tenant business name as alphanumeric sender ID,
bodies kept to one SMS segment for the fair-use cost model). Env vars:
`TELNYX_API_KEY` plus at least one of `TELNYX_FROM_NUMBER` /
`TELNYX_MESSAGING_PROFILE_ID`; when unset, reminders degrade to email/push.
`POST /webhooks/telnyx` (Ed25519 signature verified against
`TELNYX_PUBLIC_KEY`, 503 until configured) handles delivery receipts —
permanent customer-SMS failures page staff once per day via
`app/sms_alerts.py` (sharing the email-failure dedupe ledger) — and inbound
CTIA keywords: STOP opts the number out (`sms_opt_out` on the contact, sweep
falls back to email), START/UNSTOP re-enables.

### Dispatch guardrails (issue #237)

`services/api/app/dispatch.py` is the single server-side gate every
assignment path (job/appointment create/update, quote convert-to-job) passes
through. Three rules, each a structured 409 (`detail.code` +
human-toastable `detail.reason`): `schedule_conflict` (assignee already has
a blocking booking overlapping the window — shared `app.availability` math,
so drafts/cancellations never block and back-to-back slots are fine),
`daily_hours_cap` (more than `DAILY_SCHEDULE_CAP_HOURS` = 10 scheduled hours
on one calendar day), and `job_locked` (in-progress/completed jobs refuse
reschedule/reassignment).

### Stripe Connect onboarding and the public URL surface (issues #204/#218/#220/#230)

Tradesperson receivables run on Stripe Connect Express (ADR-003). Connect
onboarding happens in an in-app browser: Stripe's AccountLink API only
accepts http(s) URLs, so the API substitutes the landing site's
`/payments/stripe-bounce` page (`PUBLIC_DOCS_BASE_URL`) which bounces back
into the app's `mtp://` deep link (mobile mirrors the helper in
`mobile/src/api/payments.ts::stripeBounceUrl`). New connected accounts are
pre-filled from the tenant record — including the tenant's customer-portal
URL as the account's business website, so hosted onboarding doesn't block
tradespeople who have no site. `GET /payments/status` re-syncs the mirrored
account flags from Stripe on every read, so the app shows fresh state the
moment the tradie returns from onboarding (degrades to the last mirrored
flags on a Stripe outage).

`APP_PUBLIC_URL` is the back-office origin only — never used for
customer-facing links. The public URL surface resolves on
mytradeportal.co.uk via dedicated knobs: `PUBLIC_DOCS_BASE_URL` (quote/
invoice token pages and the Stripe bounce page), `PASSWORD_RESET_BASE_URL`
(`/reset-password`, `/accept-invite`), portal magic links on
`{slug}.PORTAL_BASE_DOMAIN`, and `CALENDAR_FEED_BASE_URL` (webcal/.ics feed
links — empty falls back to the request origin; brand it when the API custom
domain lands, issue #181).

### Tenant branding logo and offboarding (issues #232/#244)

Staff upload the tenant logo via `POST /tenants/me/logo` (multipart,
type/size validated, stored in MinIO under `tenants/{id}/branding/`;
`DELETE /tenants/me/logo` removes it). It is served unauthenticated at
`GET /businesses/{slug}/logo` and `settings.logo_url` carries the absolute
URL (built on `PUBLIC_API_BASE_URL` when set) so portal/landing pages render
it as a plain `<img>` src.

Tenant offboarding is self-service for the tenant admin:
`POST /tenants/me/offboard` with a `confirm_slug` body cancels the Paddle
subscription and deletes the Stripe connected account (best-effort — provider
outages never block), deactivates all staff/customer accounts, revokes
magic-link/invite/document/reset tokens, deactivates the tenant, and
anonymises PII in place while retaining financial records per
`docs/data-retention.md`.

### Reminder scheduler and tenant scheduling settings

`services/api/app/scheduler.py` is an in-process asyncio scheduler started from
the FastAPI lifespan (`REMINDER_SCHEDULER_ENABLED` / `REMINDER_TICK_SECONDS` env
vars; first sweep one tick after startup). It emails quote reminders (default 3,
then stop) and invoice reminders (recur until paid) via `app/email.py`, records
each send in the `reminders` table, and notifies staff in-app. Per-tenant
cadence lives in the tenant `settings` JSONB (`quote_reminders_enabled`,
`quote_reminder_max`, `quote_reminder_interval_days`,
`invoice_reminders_enabled`, `invoice_reminder_interval_days`) and is edited
from the mobile Follow-ups settings screen. Related tenant settings:
`quote_rounding` (0/5/10 — round quote totals up; `rounding_adjustment` column
on quotes/invoices carries the uplift) and `working_day_start` /
`working_day_end` / `working_days` (drive `/appointments/availability`).
Rounding flows through the quote → job → invoice chain by these rules: an
invoice created FROM a quote mirrors the quote's totals exactly (subtotal, VAT,
total, `rounding_adjustment` — never re-rounded, so a quote created before the
setting existed invoices unrounded); a scratch invoice (no quote) is rounded
once at creation; and editing a quote after invoice creation never
retro-changes the invoice. `POST /invoices` resolves the quote from
`job.quote_id` when only `job_id` is sent, so the invoice-from-job flow always
prefills the accepted quote lines (editable before send from the mobile
create-invoice page).
Per-document VAT opt-out (issue #110): `QuoteUpdate` and `InvoiceUpdate` accept
an optional `vat_rate` (a fraction, 0–1) so VAT-registered tenants can drop VAT
to 0 for zero-rated jobs (e.g. new builds), fulfilling the onboarding TaxVatStep
"you'll confirm per quote" promise. The override may only lower or remove VAT —
`vat_rate_within_tenant_limit` in `app/calculations.py` rejects (400) any rate
above the tenant's registered rate; for a non-registered tenant that means any
positive rate. Setting a rate re-runs the create-time totals math: quotes are
re-rounded via `apply_quote_rounding`, invoices keep their fixed creation-time
`rounding_adjustment`. The mobile QuoteEditScreen exposes this as a
"VAT x% / Zero-rated 0%" chip selector, shown only for VAT-registered tenants.
Electrician quote edits are captured as `quote_lines_edited` / `quote_refined`
rows in `events` (before/after snapshots) for AI fine-tuning; export via
`GET /quotes/training-events` or the SQL in that endpoint's docstring.

Deleted from the working tree:

- `services/ocerp` (OpenConstructionERP BoQ engine) — still referenced by the
commented-out block in `.railway/railway.ts`, the commented block in
`docker-compose.yml`, and a dead resource-limits block in
`docker-compose.prod-replica.yml`. The parked 501 BoQ path
(`services/api/app/clients/ocerp.py`) remains intentionally.
- `services/pwa` (old Expo app — replaced by `mobile/`); no config references
remain.
- `evals/` (old top-level golden-dataset evaluation — superseded by
`services/api/evals/`)
- `user-docs/` (Mintlify user docs)

> **Historical context:** most of the original specification, architecture diagram, and
> prior runbooks remain in `docs/archived/` or git history.

---

## Technology stack

### Active front-ends

| Concern | Mobile (`mobile/`) | Web (`web/app/`) |
|---|---|---|
| Framework | React Native 0.86.2 + Expo SDK 57 | React 19 + Vite 7 |
| Language | TypeScript 5 (target ~6.0.3) | TypeScript ~5.9.3 |
| Router | Expo Router v6 (file-based) | React Router v7 |
| Styling | NativeWind v4 (Tailwind CSS 3) | Tailwind CSS 3 + shadcn/ui |
| State | Zustand + TanStack Query | Zustand + TanStack Query |
| Forms | ad-hoc | React Hook Form + Zod |
| Icons | `@expo/vector-icons` | `lucide-react` |
| Charts | — | `recharts` |
| Test E2E | Playwright (drives web build) | Playwright |
| Test unit | (none configured) | Vitest + jsdom |

### Active/inherited shared code

- **`packages/shared/ts`** — theme tokens (`colors`, `spacing`, `radii`, `typography`).
Imported by `mobile/` as `@mtp/shared-ts` directly from `src/` (no build step —
Metro/tsc consume the TypeScript source; `dist/` is gitignored, so EAS builds
would fail if the package pointed at built output). `pnpm build` in the package
still emits `dist/` if a compiled artifact is ever needed.
- **`packages/shared/py`** — `mtp_shared` Python package with Pydantic settings,
tenancy, logging, and OCERP contract models. Installed via `pyproject.toml`.

### Infrastructure

The `docker-compose.yml` defines the full local stack, and every application
service it references now has its Dockerfile and source in the tree:

| Container | Image | Port | Purpose |
|---|---|---|---|
| `mtp_postgres` | PostgreSQL 16 | `5432` | Operational database |
| `mtp_redis` | Redis 7 | `6379` | Cache / broker |
| `mtp_qdrant` | Qdrant v1.11.5 | `6333` / `6334` | Vector search |
| `mtp_minio` | MinIO | `9000` / `9001` | Object storage |
| `mtp_mailpit` | Mailpit | `1025` / `8025` | Dev email capture |
| `mtp_api` | FastAPI (`services/api/Dockerfile`) | `8000` | Backend API |
| `mtp_web` | Vite dev server | `3000` | Back-office SPA |
| `mtp_admin` | Django (`services/admin/Dockerfile`) | `8001` | Admin back-office |
| `mtp_data_pipeline` | Python scraper (`services/data-pipeline/Dockerfile`) | — | Catalogue ingestion |

Only the commented-out `ocerp` block references a service that no longer exists.

### Observability tooling

An opt-in compose profile `observability` adds local BI/tracing without
bloating the default stack — `docker compose up` stays lean; start it with
`docker compose --profile observability up -d`:

- **Metabase** (`metabase/metabase:latest`, http://localhost:3001) — BI
  dashboards over the operational database. Its metadata store is a dedicated
  `metabase` database (`MB_DB_DBNAME`, owned by the BI role — its Liquibase
  migrations ALTER tables by name and clash with the app schema, so it must
  never point at the application database). App data is queried via the
  dedicated read-only **`mtp_metabase`** role created by `scripts/init_db.py`
  (`BYPASSRLS` + `SELECT`-only, because RLS is `FORCE`d on every tenant table;
  password from `METABASE_DB_PASSWORD`, dev-only default) — add the app
  database as a data source in the Metabase UI with that role.
- **Langfuse** (`langfuse/langfuse:2`, http://localhost:3002) with its own
  `langfuse-postgres` (host port 5440) and `clickhouse` (host ports 8124/9003
  — 8123/9000 clash with MinIO). Named volumes `langfuse_postgres_data` and
  `clickhouse_data`. API-side emission is guarded and off unless
  `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set.

Product analytics go through `app/analytics.py::track` (writes `analytics.*`
rows to the existing `events` table, fail-open, with an optional PostHog
passthrough when `POSTHOG_API_KEY` is set).

### Deployment target

- **Railway** via Infrastructure as Code in `.railway/railway.ts`.
- The IaC provisions `postgres`, `redis`, `qdrant`, `minio` plus the `api`, `web`,
`admin`, and `data-pipeline` services from this repo (`ocerp` is commented out),
which matches the current working tree.

---

## Project structure

```
mytradeportal/
├── AGENTS.md                 # This file
├── .env.example              # Environment variable template
├── .editorconfig             # 2-space default, 4-space Python
├── .gitignore
├── package.json              # Root workspace: Supabase CLI scripts only
├── pnpm-workspace.yaml       # Workspace globs + pnpm overrides/audit allow-list
├── pnpm-lock.yaml
├── pyproject.toml            # Root Python packaging + ruff/mypy/pytest config
├── docker-compose.yml        # Local stack (all referenced app services present)
├── conftest.py               # pytest path setup
│
├── .github/workflows/        # CI/CD
│   ├── ci.yml                # Python + mobile gates, schema-sync, Railway deploy on main
│   ├── pr-verify.yml         # PR preview env (Railway fork) smoke + dependency audit gate
│   ├── staging-e2e.yml       # Staging E2E suites (incl. signed-sandbox Paddle webhooks)
│   └── security-audit.yml    # Weekly cron + manual-dispatch security audit
│
├── .railway/
│   ├── railway.ts            # IaC for legacy Railway services
│   └── package.json          # IaC runner deps
│
├── mobile/                   # Active React Native + Expo iOS app
│   ├── app/                  # Expo Router routes
│   │   ├── (trade)/          # Tradesperson route group
│   │   ├── (customer)/       # Customer route group
│   │   ├── onboarding/         # Business onboarding
│   │   ├── _layout.tsx
│   │   ├── index.tsx
│   │   ├── trade-login.tsx
│   │   └── customer-login.tsx
│   ├── src/
│   │   ├── api/              # API clients (auth, onboarding, quotes, jobs, ...)
│   │   ├── components/
│   │   │   ├── navigation/   # Bottom tab bar
│   │   │   ├── onboarding/
│   │   │   ├── trade/
│   │   │   └── ui/           # Themed primitives (Button, Screen, Text, etc.)
│   │   ├── contexts/         # AuthContext wrapper around Zustand
│   │   ├── data/             # Mock businesses, customers, jobs, quotes, etc.
│   │   ├── hooks/            # Reusable hooks
│   │   ├── lib/              # apiClient, queryClient, tokenStorage, case helpers
│   │   ├── navigation/       # Navigation helpers
│   │   ├── screens/          # Screen components
│   │   │   ├── customer/
│   │   │   ├── entry/
│   │   │   ├── onboarding/
│   │   │   └── trade/
│   │   ├── stores/           # Zustand stores (authStore, businessStore)
│   │   ├── theme/            # ThemeProvider (white-label wrapper)
│   │   ├── types/            # Domain TypeScript types
│   │   └── utils/
│   ├── e2e/                  # Playwright connected-mode smoke tests
│   ├── scripts/              # iOS run scripts + demo video pipeline
│   ├── assets/
│   ├── ios/                  # Generated Xcode project (untracked)
│   ├── package.json
│   ├── app.json              # Expo config
│   ├── tailwind.config.js
│   ├── metro.config.js
│   ├── babel.config.js
│   └── tsconfig.json
│
├── packages/
│   └── shared/
│       ├── py/mtp_shared/    # Shared Python package
│       └── ts/               # Shared TypeScript theme tokens
│
├── scripts/                  # Python bootstrap scripts
│   ├── capture-screenshots.mjs # Playwright visual-record sweep into docs/screenshots/
│   ├── cleanup_test_data.py
│   ├── generate-prod-replica-env.sh
│   ├── green-deploy-check.sh
│   ├── init_api.py           # API preDeploy bootstrap wrapper
│   ├── init_db.py            # API schema + RLS init (single source of truth)
│   ├── prod-replica-up.sh
│   └── wait-for-local-prod.sh
│
├── security/                 # Security test suite (targets live backend)
│   ├── config.py
│   ├── conftest.py
│   ├── agents/
│   └── tests/
│
├── services/
│   ├── api/                  # FastAPI backend
│   │   ├── app/              # Application code (routers, models, rag/, ...)
│   │   ├── evals/            # AI quote golden-set eval harness
│   │   ├── tests/            # pytest integration tests
│   │   └── Dockerfile
│   ├── admin/                # Django admin back-office
│   └── data-pipeline/        # Apify/Screwfix cost-item scraper
│
├── supabase/                 # Supabase CLI local config
│   └── config.toml
│
├── web/
│   └── app/                  # Active React back-office SPA
│       ├── src/
│       │   ├── components/
│       │   │   ├── error/
│       │   │   ├── layout/
│       │   │   ├── shared/
│       │   │   └── ui/       # shadcn/ui primitives
│       │   ├── hooks/
│       │   ├── lib/
│       │   │   ├── api/      # API clients and TanStack Query hooks
│       │   │   ├── auth/
│       │   │   └── mock/     # Mock data and MSW-style handlers
│       │   ├── pages/          # Route pages
│       │   ├── stores/
│       │   ├── test/           # Test utilities
│       │   └── types/
│       ├── e2e/                # Playwright specs
│       ├── playwright/           # Auth fixtures
│       ├── public/
│       ├── dist/               # Built static assets (committed)
│       ├── package.json
│       ├── Dockerfile
│       ├── nginx.conf
│       └── playwright*.config.ts
│
├── docs/                     # Active documentation
│   ├── prd-beta.md           # Beta scope PRD (historical spec — see banner)
│   ├── beta-test-plan.md     # October-cohort verification map (current)
│   ├── go-live-runbook.md    # Deploy/runbook for go-live and redeploys
│   ├── testing-accounts.md   # Seeded demo estate + logins
│   ├── payments-model.md     # Money-flow description (Stripe Connect + Paddle)
│   ├── data-retention.md     # Retention schedule + offboarding behaviour
│   ├── ci-hard-rules.md      # CI invariants (no live LLM/Paddle, schema-sync)
│   ├── soc2-controls.md      # SOC2 controls catalogue
│   ├── runbooks/             # Alert runbooks
│   └── archived/             # Legacy documentation moved here
```

---

## Build, test and run commands

### Workspace setup

```bash
# Install all workspace dependencies (mobile, web/app, shared/ts, root)
pnpm install
```

The root `.npmrc` pins `node-linker=hoisted` — Expo's recommended pnpm layout.
Metro and Babel resolve presets/plugins by walking up from `mobile/`, which
breaks under pnpm's default isolated linker (EAS's Xcode bundling phase fails
with `Cannot find module 'babel-preset-expo'` → `'transformFile' undefined`).
Because of this, babel packages used by `mobile/babel.config.js` must be
declared in `mobile/package.json` (e.g. `babel-preset-expo`).

### Mobile app (`mobile/`)

> **Note:** the app was moved from `services/pwa` to `mobile/`; the shell scripts
> inside `mobile/` now resolve their paths from the new location.

```bash
cd mobile

# Start the Expo dev server (dev-client mode — there is no Expo Go)
pnpm start

# Run on iOS Simulator (macOS + Xcode required)
pnpm ios

# Type check
pnpm lint

# Install Playwright browsers for E2E
pnpm e2e:install

# Run connected-mode E2E against a live backend
pnpm test:e2e
```

Distribution via EAS (profiles in `mobile/eas.json`):

```bash
# Production build → TestFlight
npx eas-cli build --platform ios --profile production
npx eas-cli submit --platform ios --profile production

# Dev-client build for the simulator / QA device
npx eas-cli build --platform ios --profile development-simulator   # simulator
npx eas-cli build --platform ios --profile preview                 # device QA (internal)

# OTA hot fix (JS-only; no store resubmission)
npx eas-cli update --branch production --message "fix: ..."

# Quota-free local build (macOS + Xcode + fastlane; EAS runs the build on your
# machine via fastlane and prints the .ipa path — no EAS build minutes used)
npx eas-cli build --platform ios --profile production --local
npx eas-cli submit --platform ios --path <path-to>.ipa
```

Runtime modes:

- **Connected mode (only mode)** — set `EXPO_PUBLIC_API_BASE_URL=http://localhost:8000`.
The app calls the real FastAPI backend and stores the bearer token in iOS Keychain via
`expo-secure-store`. (The old in-app demo/mock-data mode was removed; the
`owner@demo.trade` / `demo123` accounts are real users seeded into the dev/e2e
backend, not client-side mocks.)
- **White-label** — set `EXPO_PUBLIC_BUSINESS_SLUG=<slug>` to fetch a tenant's public
config on launch.

### Web back-office (`web/app/`)

```bash
cd web/app

# Install dependencies
pnpm install

# Start Vite dev server
pnpm dev

# Type check + lint
pnpm lint

# Unit tests (Vitest)
pnpm test

# Build production bundle
pnpm build

# E2E tests against the Docker stack
pnpm test:e2e
```

### Shared TypeScript (`packages/shared/ts`)

```bash
cd packages/shared/ts
pnpm install
pnpm build      # compile src/ into dist/
pnpm dev        # watch mode
```

### Python (`services/api`, `services/data-pipeline`, `packages/shared/py`)

The Python virtual environment at `.venv` is present and the root package is
installed in editable mode.

```bash
source .venv/bin/activate

# Lint / format / type check
ruff check .
ruff format .
mypy services/api packages/shared/py

# API tests (require local Postgres: docker compose up -d postgres)
cd services/api && python -m pytest tests -q

# Offline eval-harness tests (fixtures only, marked `evals`)
cd services/api && python -m pytest tests/test_evals.py -q

# AI quote golden-set eval harness (offline by default; --live calls the LLM)
cd services/api && python -m evals.run_evals [--live] [--threshold 70]

pytest security/tests -v                  # subset that does not need services/api
```

### Local infrastructure

The whole stack builds and runs locally:

```bash
docker compose up -d postgres redis qdrant minio mailpit   # data infra only
docker compose up -d                                       # full stack
```

The `api`, `admin`, and `data-pipeline` services build from
`services/*/Dockerfile`; only the commented-out `ocerp` block cannot build.

---

## Code style guidelines

### General

- EditorConfig: `utf-8`, `lf`, 2-space indentation for most files, 4-space for
Python, 2-space for YAML.
- Keep comments and docstrings in English.
- Prefer small, incremental changes. The repository is in flux, so avoid large
refactors of deleted/legacy code.

### TypeScript / React

- Functional components and hooks.
- Server state via **TanStack Query**, client state via **Zustand**.
- Tailwind utility classes; use `cn()` from `clsx` + `tailwind-merge` where
available.
- API boundary: `web/app` uses `humps` to convert `camelCase` ↔ `snake_case`.
- Mobile app uses `snakeizeKeys`/`camelizeKeys` helpers in `mobile/src/lib/case.ts`.

### Mobile conventions

- `app/` — Expo Router file-based routes. Route groups: `(trade)`, `(customer)`,
`onboarding`.
- `src/screens/` — screen components grouped by audience (`trade/`, `customer/`,
`onboarding/`, `entry/`).
- `src/components/ui/` — themed primitives (`Button`, `Text`, `Screen`, `Header`,
`CodeInput`, etc.).
- `src/stores/` — Zustand stores (`authStore`, `businessStore`).
- `src/contexts/AuthContext.tsx` — compatibility wrapper that exposes the legacy
`useAuth()` hook backed by Zustand.
- Light mode only at launch; dark mode is post-MVP.
- Use shared theme tokens (`@mtp/shared-ts`) for colors, spacing, and typography.

### Python

- Python 3.11+; type hints everywhere.
- Formatting and linting by **ruff** (`target-version = "py311"`, line length 100,
double quotes, spaces).
- Static checking by **mypy** in strict mode.

---

## Testing instructions

### `web/app` — Vitest

```bash
cd web/app
pnpm test -- --run
```

Covers pages, components, hooks, API clients, and stores (the count grows
constantly — see `docs/test-coverage.md` for the journey map).

### `web/app` — Playwright E2E

```bash
cd web/app
pnpm exec playwright install chromium
pnpm test:e2e
```

The default config (`playwright.config.ts`) starts the Docker stack and runs the
local E2E suite. Additional configs exist for prod replica, prod smoke, and
video recording.

### `mobile/` — Playwright E2E

The mobile E2E suite drives the app as a web build. It is intended to run
against a live backend:

```bash
cd mobile
pnpm e2e:install
pnpm test:e2e
```

### Python tests

The API test suite lives in `services/api/tests/` and runs against a local
Postgres (start it with `docker compose up -d postgres`):

```bash
source .venv/bin/activate
cd services/api
python -m pytest tests -q          # full API suite
python -m pytest tests/test_evals.py -q   # offline eval-harness tests (marker: evals)
```

The root pytest config excludes the `eval` (legacy OCERP) and `security` markers
from default runs; the `evals` marker is offline-safe and runs by default.

### Security tests

Security tests are marked with `pytest.mark.security` and are **not** run by
default. They require live target credentials:

```bash
export SECURITY_API_BASE_URL=https://api-production-XXXX.up.railway.app
export SECURITY_TENANT_SLUG=demo
export SECURITY_ADMIN_EMAIL=admin@example.com
export SECURITY_ADMIN_PASSWORD=...
pytest -m security -v --no-cov
```

---

## Deployment and CI

### GitHub Actions

| Workflow | Status | Notes |
|---|---|---|
| `ci.yml` | Active | Python (ruff/mypy/pytest) + mobile tsc gates, schema-sync job, Railway IaC deploy on push to main; hard rules in `docs/ci-hard-rules.md` |
| `pr-verify.yml` | Active | Spins up a Railway PR preview env and smokes it (health, landing token pages, quote-request submit); `pnpm audit --audit-level=high` is a hard gate here |
| `staging-e2e.yml` | Active | Staging E2E suites; the write suite signs Paddle webhook payloads locally with the sandbox secret — never calls the live Paddle API |
| `security-audit.yml` | Weekly cron + manual | Runs the security suite against live backend |

### Railway IaC

`.railway/railway.ts` declares the Railway stack (`postgres`, `redis`, `qdrant`,
`minio`, plus `api`, `web`, `admin`, and `data-pipeline` built from this repo;
`ocerp` is commented out). It matches the current working tree.

---

## Security considerations

- **Secrets**: never commit API keys, database URLs, or payment/webhook
credentials. Use `.env` files (ignored by git) or a secrets manager.
- **Auth tokens**: the mobile app stores bearer tokens in `expo-secure-store`
(iOS Keychain). The web app uses cookie-based sessions.
- **Tenant header**: the web API client injects `X-Tenant-ID` on every request and
logs out on a tenant-mismatch 403.
- **Security suite**: `security/` contains read-only/code-analysis tests and an
agentic penetration-test orchestrator. It is safe to run but requires live target
credentials.
- **Dependency audits** (also run by the `dependency-audit` job in
`pr-verify.yml` — `pnpm audit` is a hard high/critical gate there, `pip-audit`
is report-only because it has no severity filter and some advisories against
our tree, e.g. ecdsa CVE-2024-23342, have no fixed release):

```bash
# Python (no severity filter; review output for high/critical)
pip-audit --desc

# Node (fails on high/critical; the only accepted advisories are the
# documented GHSA IDs in auditConfig.ignoreGhsas in pnpm-workspace.yaml)
pnpm audit --audit-level=high
```

Transitive Node packages with fixable advisories are pinned to patched
releases via `overrides` in `pnpm-workspace.yaml` — add new ones there rather
than bumping direct dependencies that aren't actually vulnerable.

---

## Environment variables

Key variables (see `.env.example` for the full template):

- `ENVIRONMENT`, `LOG_LEVEL`
- `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`
- `MINIO_ENDPOINT`, `MINIO_USE_SSL`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
- `AUTH_SECRET_KEY`, `AUTH_COOKIE_SECURE`
- `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_API_BASE`, `LLM_API_KEY`, `LLM_TEMPERATURE`,
  `LLM_TIMEOUT_SECONDS`
- `LLM_REFINE_MODEL`, `LLM_FOLLOWUP_MODEL` (+ per-route timeout/retry knobs),
  `LLM_VISION_MODEL`, `INTAKE_TRIAGE_MODEL` — fast/vision model routes (empty
  inherits `LLM_MODEL`)
- `EMBEDDING_MODEL`, `EMBEDDING_API_BASE`, `EMBEDDING_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_CLIENT_ID`,
  `STRIPE_PUBLISHABLE_KEY` — tradesperson receivables (Connect Express)
- `PADDLE_API_KEY`, `PADDLE_WEBHOOK_SECRET`, `PADDLE_CLIENT_TOKEN`, `PADDLE_SANDBOX`,
  `PADDLE_PRICE_ID_*` — SaaS billing (merchant of record)
- `TELNYX_API_KEY`, `TELNYX_FROM_NUMBER`, `TELNYX_MESSAGING_PROFILE_ID`,
  `TELNYX_PUBLIC_KEY` — SMS appointment reminders + inbound webhook
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_NO_REPLY_EMAIL`,
  `RESEND_WEBHOOK_SECRET` — transactional email + bounce/failure alerts
- Public URL knobs: `APP_PUBLIC_URL` (back-office origin only),
  `PUBLIC_DOCS_BASE_URL`, `PASSWORD_RESET_BASE_URL`, `PORTAL_BASE_DOMAIN`,
  `CALENDAR_FEED_BASE_URL`, `PUBLIC_API_BASE_URL`
- `INVITE_TOKEN_TTL_DAYS`, `TESTFLIGHT_URL` — staff team invites
- `VITE_API_BASE_URL` — web app backend URL
- `EXPO_PUBLIC_API_BASE_URL` — mobile backend URL (required; there is no offline demo mode)
- `EXPO_PUBLIC_BUSINESS_SLUG` — white-label target business
- `EXPO_PUBLIC_SETUP_TOKEN` — tenant bootstrap token

---

## Known issues and follow-up

1. **Calendar feed branded domain (issue #181).** Calendar subscription
(webcal/.ics) links fall back to the request origin until
`CALENDAR_FEED_BASE_URL` is pointed at a branded API domain
(`api.mytradeportal.co.uk`) — the custom domain has not landed yet.
2. **Live-verification residue.** Code-complete but only verifiable against
live providers, tracked in `docs/beta-test-plan.md` §3: a real-card payment
against live Stripe keys (go-live gate), live SMS delivery to a real handset
(needs provisioned Telnyx number/keys), and background push delivery on a
physical device (APNs cannot be simulated).
3. **Dead ocerp overlay block.** `docker-compose.prod-replica.yml` carries a
resource-limits block for the deleted `services/ocerp` (the base compose
entry is commented out, so the overlay is inert); remove it when the file is
next touched.
4. **Mobile TypeScript install.** `pnpm install` in the mobile workspace may leave
a broken `typescript` symlink on some machines; a clean `rm -rf mobile/node_modules`
followed by `pnpm install` usually resolves it.

---

## Reference material

- `mobile/AGENTS.md` — mobile-specific conventions.
- `mobile/README.md` — setup, run, and EAS build/submit instructions for the iOS app.
- `web/app/README.md` — Vite template README.
- `security/README.md` — security test suite documentation.
- `docs/prd-beta.md` — Beta scope PRD (historical spec; see the status banner).
- `docs/beta-test-plan.md` — current verification map for the October beta cohort.
- `docs/go-live-runbook.md` — deploy order, production env wiring, rollback.
- `docs/testing-accounts.md` — seeded demo estate, logins, manual test flows.
- `docs/payments-model.md` — how money moves (Stripe Connect + Paddle).
- `docs/data-retention.md` — retention schedule and tenant offboarding behaviour.
- `docs/ci-hard-rules.md` — CI invariants.
- `docs/runbooks/alerts.md` — alert runbooks.
- `docs/electrician-app-rn-stack-report.md` — React Native stack report.
- `docs/soc2-controls.md` — SOC2 controls catalogue.
- `docs/archived/` — legacy product specs, runbooks, and compliance docs.

---

*End of AGENTS.md*
