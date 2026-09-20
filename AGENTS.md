# AGENTS.md — My Trade Portal

This file is written for AI coding agents who need to understand the project as it
exists in the working tree. The repository is currently mid-pivot: the backend
services (`services/api`, `services/admin`, `services/data-pipeline`) are present
again after the provider-agnostic LLM / guide-priced AI quotes work, while the old
`services/pwa` Expo app has been replaced by a new React Native + Expo iOS app under
`mobile/`. Some root config files still reference genuinely deleted services
(`services/ocerp`, `services/pwa`), so treat this document as the source of truth
for the *current* layout.

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
- **`docs/`** — active documentation. Currently holds the React Native stack report
(`electrician-app-rn-stack-report.md`) and the SOC2 controls catalogue
(`soc2-controls.md`). Legacy docs remain in `docs/archived/`.

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

### Team gating and sole-staff auto-assignment (issue #191)

Plan tiers cap staff seats (`Plan.seats`: sole_trader 1, pro 5, team 15 —
enforced by `POST /users/invite`). Assignment is only meaningful on multi-seat
plans, so every job-creation path (`POST /jobs`, quote convert-to-job, the
acceptance-time draft job) and `POST /appointments` defaults
`assigned_user_id` to the tenant's ONLY active user when none is supplied
(`app.dependencies.single_active_user`); explicit assignees are validated and
always win. Seat context reaches clients via `GET /billing/subscription`,
which now carries `seats` (plan catalog, legacy keys resolved) and
`seats_in_use` (active users + pending invites — the same count the invite
endpoint gates on). The mobile app gates its assignee pickers on the simpler
equivalent signal: the pickers (job create, job detail) render only when
`GET /users` returns more than one active user.

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

Deleted from the working tree but still referenced in config:

- `services/ocerp` (OpenConstructionERP BoQ engine)
- `services/pwa` (old Expo app — replaced by `mobile/`)
- `evals/` (old top-level golden-dataset evaluation — superseded by
`services/api/evals/`)
- `user-docs/` (Mintlify user docs)

> **Historical context:** most of the original specification, architecture diagram, and
> prior runbooks remain in `docs/archived/` or git history. The two active docs in
> `docs/` were added back to the working tree.

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
├── pnpm-workspace.yaml       # Workspace globs (includes deleted services/pwa)
├── pnpm-lock.yaml
├── pyproject.toml            # Root Python packaging + ruff/mypy/pytest config
├── docker-compose.yml        # Local stack (all referenced app services present)
├── conftest.py               # pytest path setup (still references deleted services/ocerp)
│
├── .github/workflows/        # CI/CD (pwa-e2e.yml references deleted services/pwa)
│   ├── ci.yml                # Python + web CI + Railway deploy (deprecated note)
│   ├── pwa-e2e.yml           # References services/pwa
│   ├── smoke-test.yml        # Web production smoke
│   └── security-audit.yml    # Manual-dispatch security audit
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
│   ├── electrician-app-rn-stack-report.md
│   ├── soc2-controls.md
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

Currently 138 unit/integration tests pass across pages, components, hooks, API
clients, and stores.

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
Running bare `pytest` from the repo root still trips over `conftest.py` paths
for the deleted `services/ocerp`.

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
| `ci.yml` | Deprecated | Contains a FIXME noting it should be removed; targets `services/api` |
| `pwa-e2e.yml` | Stale path | References `services/pwa` instead of `mobile/` |
| `smoke-test.yml` | Active for `web/app` | Production smoke tests for the Vite SPA |
| `security-audit.yml` | Manual only | Runs security suite against live backend |

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
- `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_API_BASE`, `LLM_API_KEY`, `LLM_TEMPERATURE`
- `EMBEDDING_MODEL`, `EMBEDDING_API_BASE`, `EMBEDDING_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `VITE_API_BASE_URL` — web app backend URL
- `EXPO_PUBLIC_API_BASE_URL` — mobile backend URL (required; there is no offline demo mode)
- `EXPO_PUBLIC_BUSINESS_SLUG` — white-label target business
- `EXPO_PUBLIC_SETUP_TOKEN` — tenant bootstrap token

---

## Known issues and follow-up

1. **Mid-migration state.** `services/api`, `services/admin`, and
`services/data-pipeline` are present again; only `services/ocerp` and
`services/pwa` are deleted but still referenced by `pnpm-workspace.yaml`,
`.railway/railway.ts` (ocerp commented out), `.github/workflows/pwa-e2e.yml`,
`conftest.py` (ocerp path), and `pyproject.toml` (`testpaths` still lists the
old top-level `evals/`).
2. **CI workflows stale.** `ci.yml` and `pwa-e2e.yml` need updating to match the
`mobile/` location.
3. **Mobile TypeScript install.** `pnpm install` in the mobile workspace may leave
a broken `typescript` symlink on some machines; a clean `rm -rf mobile/node_modules`
followed by `pnpm install` usually resolves it.

---

## Reference material

- `mobile/AGENTS.md` — mobile-specific conventions (note: some paths still say
`services/pwa`).
- `mobile/README.md` — setup and run instructions for the iOS app (partially stale).
- `web/app/README.md` — Vite template README.
- `security/README.md` — security test suite documentation.
- `docs/prd-beta.md` — Beta scope PRD (mobile + existing backend integration).
- `docs/electrician-app-rn-stack-report.md` — React Native stack report.
- `docs/soc2-controls.md` — SOC2 controls catalogue.
- `docs/archived/` — legacy product specs, runbooks, and compliance docs.

---

*End of AGENTS.md*
