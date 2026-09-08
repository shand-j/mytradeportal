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
- `POST /quotes/{id}/refine` accepts electrician instructions and regenerates the
AI-drafted line items, preserving any manually added/edited lines. Rate limited
like `/generate`.
- `services/api/evals/` is a golden-set eval harness: 15 representative UK
domestic jobs scored on kind coverage, keyword hit-rate, guide price band, and
line-count sanity. Offline mode replays canned fixtures (no API keys); `--live`
calls the real LLM. Run it from `services/api` with `python -m evals.run_evals`.

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

### Mobile app (`mobile/`)

> **Note:** the app was recently moved from `services/pwa` to `mobile/`. Several
> shell scripts inside `mobile/` still reference `services/pwa` paths and need to
> be updated before they work.

```bash
cd mobile

# Start the Expo dev server
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

Known issue: `mobile/e2e/run.sh` and `mobile/e2e/start-stack.sh` still point to
`services/pwa` and need path updates before the suite runs.

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
- **Dependency audits**:

```bash
# Python
pip-audit --desc --audit-level=high

# Node
pnpm audit --audit-level=high
```

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
2. **Mobile script paths.** `mobile/e2e/run.sh`, `mobile/e2e/start-stack.sh`, and
`mobile/scripts/run-ios.sh` reference `services/pwa`.
3. **Root README deleted.** The project currently has no root `README.md`.
4. **CI workflows stale.** `ci.yml` and `pwa-e2e.yml` need updating to match the
`mobile/` location.
5. **Mobile TypeScript install.** `pnpm install` in the mobile workspace may leave
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
