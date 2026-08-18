# AGENTS.md — My Trade Portal V2

> This file is written for AI coding agents who need to understand the project. It describes the repository as it currently exists, not the future roadmap.

---

## Project overview

**My Trade Portal V2** is an AI-native field service management platform. The current implementation is focused on **UK electricians** and provides:

- A multi-tenant **FastAPI** backend with PostgreSQL Row-Level Security.
- A **React + Vite + Tailwind** back-office web application (`web/app`) for tradespeople.
- A **React Native + Expo iOS app** (`services/pwa`) that white-labels for each trade business and serves both tradesperson and customer profiles.
- A **Django 5** admin panel (`services/admin`) that mirrors the operational schema read-only.
- A **data pipeline** (`services/data-pipeline`) that scrapes electrical supplier pricing and loads it into Postgres/Qdrant.
- An **OpenConstructionERP (OCERP)** BoQ microservice that is currently parked for the mobile-pivot MVP (BoQ endpoints return HTTP 501).

Planned but not yet implemented: customer PWA, Celery worker service, embeddable chatbot widget, voice AI agent, accounting sync, WhatsApp integration, Android app.

The authoritative product vision is in [`mtp_v2_product_spec.md`](mtp_v2_product_spec.md) and the system diagram is in [`mtp_v2_architecture.png`](mtp_v2_architecture.png). Day-to-day engineering docs live in [`docs/`](docs/).

---

## Current delivery priority (pre-go-live)

For now, the first priority is high-confidence, production-like validation from local runs, then fast iteration with minimal debt.

- Treat `web/app/e2e/prod-validation.spec.ts` as the broad local release-confidence suite.
- Treat `web/app/e2e/prod-smoke.spec.ts` + `.github/workflows/smoke-production.yml` as the hosted production sanity gate.
- Prefer running E2E against near-production configuration (`ENVIRONMENT=production` + `docker-compose.prod-like.yml`) when touching user-critical flows.
- Keep fixes incremental and low-risk; avoid introducing refactors that exceed ~0.5 dev day debt budget during pre-go-live iteration.
- If a defect is found in a core flow, fix it and add/adjust an E2E assertion in the same change when practical.

Reference docs:
- [`docs/deployment.md`](docs/deployment.md)
- [`docs/runbooks/ci-cd.md`](docs/runbooks/ci-cd.md)
- [`docs/production-test-report.md`](docs/production-test-report.md)

---

## Technology stack

| Concern | Technology |
|---|---|
| API backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Admin panel | Python 3.11+, Django 5, psycopg2 |
| OCERP microservice | Python 3.11+, FastAPI, SQLAlchemy 2, Qdrant |
| Data pipeline | Python 3.11+, FastAPI, Apify, schedule, SQLAlchemy 2 |
| Back-office UI | React 19, TypeScript 5.9, Vite 7, Tailwind CSS 3, shadcn/ui |
| Database | PostgreSQL 16 |
| Vector search | Qdrant (default embedding model `text-embedding-3-small`, 1536 dims) |
| Cache / broker | Redis 7 |
| Object storage | MinIO (S3-compatible) |
| Email (dev) | Mailpit |
| LLM routing | LiteLLM against any OpenAI-compatible endpoint. Default OpenAI (`LLM_MODEL=gpt-4o-mini`); Kimi/Moonshot supported via `LLM_API_BASE`/`LLM_API_KEY` + `openai/kimi-k2.6`. Embeddings stay OpenAI (Kimi has none) and are optional |
| Payments | Paddle Billing (checkout + webhooks) |
| Auth | Local bcrypt/JWT session cookies; optional Supabase Auth |
| Containerisation | Docker + Docker Compose |
| Package manager (Python) | pip / setuptools editable installs |
| Package manager (Node) | pnpm |

---

## Runtime architecture

The local stack is defined in [`docker-compose.yml`](docker-compose.yml):

| Container | Service | Port | Purpose |
|---|---|---|---|
| `mtp_postgres` | PostgreSQL 16 | `5432` | Operational database |
| `mtp_redis` | Redis 7 | `6379` | Cache / future task broker |
| `mtp_qdrant` | Qdrant | `6333` / `6334` | Vector database |
| `mtp_minio` | MinIO | `9000` / `9001` | Object storage |
| `mtp_mailpit` | Mailpit | `1025` / `8025` | Email capture |
| `mtp_api` | FastAPI API | `8000` | Main REST API |
| `mtp_web` | React back-office UI | `3000` | Back-office SPA |
| `mtp_admin` | Django admin | `8001` | Staff admin panel |
| `mtp_data_pipeline` | Data pipeline | — | Scheduled scraper/loader |
| `mtp_ocerp` | OCERP microservice (parked) | `8002` (host) → `8000` (container) | BoQ / pricing engine (commented out in `docker-compose.yml`) |

Additional directories:

- `packages/shared/py/mtp_shared/` — shared Python settings, logging, tenancy, event schemas, and OCERP API contracts (`BoQGenerateRequest`/`BoQGenerateResponse` etc. in `ocerp.py`).
- `packages/shared/ts/` — shared TypeScript primitives (theme tokens, etc.).
- `services/pwa/` — React Native + Expo iOS app for the pivot (trade + customer flows).
- `services/worker/`, `services/chatbot-widget/` — empty placeholders.
- `supabase/` — Supabase CLI local config; optional alternative to the Compose-managed Postgres.

---

## Project structure

```
mytradeportal/
├── AGENTS.md                       # This file
├── README.md
├── mtp_v2_product_spec.md          # Product specification
├── mtp_v2_architecture.png         # Architecture diagram
├── pyproject.toml                  # Root Python deps + tool config (ruff, mypy, pytest)
├── alembic.ini                     # Alembic config (script_location = services/api/alembic)
├── docker-compose.yml              # Local stack
├── package.json                    # Root workspace (Supabase CLI scripts only)
├── pnpm-lock.yaml
├── .github/workflows/ci.yml        # GitHub Actions CI
├── .pre-commit-config.yaml         # pre-commit hooks
├── conftest.py                     # Root pytest path setup
├── packages/
│   └── shared/
│       ├── py/mtp_shared/          # Shared Python primitives
│       └── ts/src/                 # Placeholder
├── services/
│   ├── api/                        # FastAPI backend
│   │   ├── app/                    # Application code
│   │   │   ├── main.py             # FastAPI entrypoint
│   │   │   ├── models.py           # SQLAlchemy models
│   │   │   ├── schemas.py          # Pydantic request/response schemas
│   │   │   ├── database.py         # Async engine + session
│   │   │   ├── dependencies.py     # Tenant/auth dependencies
│   │   │   ├── config.py           # Settings wrapper
│   │   │   ├── security.py         # Password hashing + JWT cookies
│   │   │   ├── rls.py              # PostgreSQL RLS helpers
│   │   │   ├── calculations.py     # Quote/invoice VAT + totals
│   │   │   ├── audit.py            # Audit-log writer
│   │   │   ├── limiter.py          # slowapi rate limiter
│   │   │   ├── logging.py          # structlog wrapper
│   │   │   ├── qdrant.py           # Qdrant client
│   │   │   ├── supabase.py         # Supabase Auth client
│   │   │   ├── paddle_client.py    # Paddle checkout + webhooks
│   │   │   ├── email.py            # aiosmtplib email sender
│   │   │   ├── pdf.py              # FPDF quote PDF generator
│   │   │   ├── seed_admin_user.py  # Local-dev tenant + admin user seeder
│   │   │   ├── ingest_ddc_uk.py    # DDC CWICR UK cost database ingestion
│   │   │   ├── routers/            # Domain routers
│   │   │   │   ├── health.py
│   │   │   │   ├── tenants.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── users.py
│   │   │   │   ├── contacts.py
│   │   │   │   ├── quotes.py
│   │   │   │   ├── jobs.py
│   │   │   │   ├── appointments.py
│   │   │   │   ├── invoices.py
│   │   │   │   ├── payments.py
│   │   │   │   ├── webhooks.py
│   │   │   │   ├── analytics.py
│   │   │   │   ├── reviews.py
│   │   │   │   ├── communications.py
│   │   │   │   └── files.py
│   │   │   ├── rag/                # In-house RAG quote engine
│   │   │   │   ├── retrieval.py
│   │   │   │   ├── generation.py
│   │   │   │   └── validation.py
│   │   │   └── clients/ocerp.py    # HTTP client for OCERP service
│   │   ├── alembic/                # Database migrations
│   │   ├── tests/                  # pytest suite (20+ modules)
│   │   └── Dockerfile
│   ├── admin/                      # Django admin panel
│   │   ├── admin_project/          # Django project
│   │   ├── operations/             # Django app with unmanaged models
│   │   ├── manage.py
│   │   └── Dockerfile
│   ├── ocerp/                      # OCERP / BoQ estimation microservice
│   │   ├── ocerp/
│   │   │   ├── main.py
│   │   │   ├── routers/            # boq, pricing, standards, takeoff, knowledge, health
│   │   │   ├── services/           # agent_graph, intake, boq_engine, requirements,
│   │   │   │                       # resolver, pricing, labour, compliance,
│   │   │   │                       # knowledge_store, standards, boq_models
│   │   │   ├── data/
│   │   │   ├── retrieval.py / generation.py  # RAG helpers
│   │   ├── tests/
│   │   └── Dockerfile
│   ├── data-pipeline/              # Domestic electrical data scraper + loader
│   │   ├── src/data_pipeline/
│   │   │   ├── scrapers/           # Apify supplier scrapers
│   │   │   ├── normalizer/         # Product normalisation
│   │   │   ├── scripts/            # One-off loader and cleanup scripts
│   │   │   ├── loader.py           # Postgres/Qdrant upserts
│   │   │   ├── knowledge_loader.py # Regulatory/quoting knowledge base loader
│   │   │   └── scheduler.py        # Daily/monthly schedule
│   │   ├── config/suppliers.yaml
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   ├── worker/                     # Placeholder
│   ├── pwa/                        # React Native + Expo iOS app
│   └── chatbot-widget/             # Placeholder
├── web/
│   └── app/                        # React back-office SPA
│       ├── src/
│       │   ├── pages/              # Dashboard, Calendar, AiInsights, Reviews,
│       │   │                       # customers/, quotes/, jobs/, invoices/,
│       │   │                       # settings/, login/
│       │   ├── components/         # shadcn/ui primitives + app components
│       │   ├── hooks/  lib/  stores/  types/  test/
│       ├── e2e/                    # Playwright specs
│       ├── package.json
│       ├── vite.config.ts
│       ├── vitest.config.ts
│       ├── playwright.config.ts
│       └── Dockerfile
├── evals/                          # Golden-dataset evaluation
│   ├── golden_dataset.yaml
│   ├── scorer.py
│   ├── test_golden_dataset.py
│   └── results/                    # Per-case JSON + summary.json
├── docs/                           # Engineering documentation
└── supabase/                       # Supabase CLI local config
```

---

## Multi-tenancy

Every tenant represents a trade business. Isolation is enforced at **two layers**:

1. **Application layer**: each request must include `X-Tenant-ID: <tenant-uuid>` (or resolve via `Host` subdomain). FastAPI dependencies load the tenant, verify the JWT `tenant_id` claim, and set `app.current_tenant` in the Postgres session.
2. **Database layer**: PostgreSQL Row-Level Security policies on all tenant-scoped tables allow rows only when `tenant_id::text = current_setting('app.current_tenant', true)`. A `bypass_rls` setting is available for seeds/admin tasks.

The `mtp_app` Postgres role (created by migration `b7e1c0f4_enable_rls.py`) is a non-superuser that cannot bypass RLS, so application connections are forced through the policies.

Tenant-scoped tables include `users`, `contacts`, `quotes`, `quote_line_items`, `bill_of_quantities`, `boq_line_items`, `jobs`, `appointments`, `invoices`, `invoice_line_items`, `payments`, `communications`, `reviews`, and `audit_logs`. The global tables are `tenants` and `cost_items`.

---

## Key implemented modules

### FastAPI API (`services/api`)

- **Auth**: `/auth/login` returns an HTTP-only `session` cookie; supports local bcrypt or Supabase Auth.
- **Tenants**: create, read, and update tenant settings/branding/pricing.
- **Contacts / CRM**: full CRUD with audit logging.
- **Quotes**: manual CRUD, approve/reject/send, convert to invoice, PDF export, and two AI generation paths:
  - `POST /quotes/generate` — in-house RAG (Qdrant retrieval → LLM → validation).
  - `POST /quotes/generate-boq` and `use_ocerp=true` — call the OCERP BoQ engine.
- **Jobs / Appointments**: work orders and scheduling with availability lookup.
- **Invoices / Payments**: auto-numbered invoices, VAT calculation, Paddle checkout, Paddle webhook recording.
- **Files**: presigned MinIO uploads.
- **Analytics**: dashboard KPIs and AI insights.

### OCERP (`services/ocerp`)

HTTP endpoints:

- `POST /ocerp/v1/boq/generate` — end-to-end BoQ generation.
- `POST /ocerp/v1/price/lookup` — cost item lookup.
- `GET /ocerp/v1/standards/list` — supported estimating standards.
- `POST /knowledge/search` — semantic search over the quoting knowledge base.
- `POST /ocerp/v1/takeoff/{pdf,cad,photo}` — document takeoff placeholders (currently return HTTP 501).
- `GET /health`, `GET /health/ready` — liveness/readiness.

Core services (`ocerp/services/`):

- `agent_graph.py` — code-first agent graph for BoQ generation: a sequence of small deterministic nodes where the LLM is only used to parse free text into structured requirements; all pricing, compliance decisions, and citations are produced by explicit Python functions.
- `intake.py` — parses free text/form data into a typed `SiteSurvey` and gates on missing critical data with targeted follow-up questions.
- `boq_engine.py`, `boq_models.py` — BoQ assembly and models.
- `requirements.py` — deterministic rule engine (e.g. circuit counts, accessory schedules).
- `resolver.py` — catalogue mapping of required items to cost items.
- `pricing.py`, `labour.py` — material pricing and labour estimation.
- `compliance.py`, `standards.py` — regulatory citations and estimating standards.
- `knowledge_store.py` — quoting knowledge base search.

### Data pipeline (`services/data-pipeline`)

- Scrapes Screwfix via Apify (`datasaurus~screwfix-event`); Toolstation support exists but is disabled (`TOOLSTATION_ENABLED=false`).
- Normalises products into a `UnifiedProduct` schema (`normalizer/`).
- Upserts `cost_items` into Postgres and indexes embeddings in Qdrant (`cost_items` and `quoting_knowledge` collections).
- Loads a regulatory/quoting knowledge base (`knowledge_loader.py`).
- Runs on a daily/monthly schedule inside the `mtp_data_pipeline` container (`scheduler.py`).

### Back-office UI (`web/app`)

- React SPA with subdomain-based tenant resolution.
- `X-Tenant-ID` is injected on every API request from the authenticated user's tenant.
- Pages implemented: Dashboard, Calendar, AI Insights, Reviews, Customers (directory + detail), Quotes (list + detail), Jobs, Invoices, Settings, Login.
- Server state via TanStack Query; client state via Zustand.
- shadcn/ui component library, Recharts charts, React Hook Form + Zod.
- Unit tests with Vitest/jsdom; E2E tests with Playwright against the Docker Compose stack.

---

## Build, test and run commands

### Local stack

```bash
# Start everything
docker compose up -d

# View API logs
docker logs -f mtp_api

# Reset the database (destroys data)
docker compose down -v && docker compose up -d
```

### Python backend

```bash
# Activate the existing venv and install editable source
source .venv/bin/activate
pip install -e ".[dev]"

# Run database initialisation (Alembic + Django tables)
python scripts/init_db.py

# Seed local-dev tenant + admin user (env vars required; local dev only)
cd services/api
SEED_ADMIN_EMAIL=you@example.com SEED_ADMIN_PASSWORD=<choose-a-password> \
  python -m app.seed_admin_user

# Load Screwfix data via the Apify pipeline
cd services/data-pipeline
python -m data_pipeline.loader

# Or import an existing Apify dataset
cd services/data-pipeline
python -m data_pipeline.import_apify_dataset <dataset-id>

# Ingest DDC CWICR UK cost database
cd services/api
python -m app.ingest_ddc_uk

# Run the API directly (Postgres/Qdrant still required)
cd services/api
uvicorn app.main:app --reload --reload-dir /app/services/api --reload-dir /app/packages/shared/py
```

Back-office login after seeding:
- Business slug: `demo` (or your `SEED_TENANT_SLUG`)
- Email: the email you set via `SEED_ADMIN_EMAIL`
- Password: the password you set via `SEED_ADMIN_PASSWORD`

### Lint / format / type check / test

```bash
# Python lint/format
ruff check .
ruff format .

# Python type check (as configured in CI)
mypy services/api packages/shared/py

# Python tests
pytest

# Run only the API tests
pytest services/api/tests -v

# Run evaluation harness
pytest -m eval

# Per-case evaluation (slower; one LLM call per case)
EVAL_PER_CASE=1 pytest -m eval
```

### OCERP service (parked)

The OCERP / BoQ service is commented out in `docker-compose.yml` and `.railway/railway.ts`
for the mobile-pivot MVP. The corresponding API endpoints return HTTP 501. To re-enable,
uncomment the service blocks and set `OCERP_ENABLED=true` in the API environment.

```bash
# If re-enabled, the service runs in Docker on host port 8002
# Run tests locally:
pytest services/ocerp/tests -v
```

### Data pipeline

```bash
# The scheduler runs in Docker; to run one-off loader scripts:
cd services/data-pipeline
python -m src.data_pipeline.loader
python -m src.data_pipeline.import_apify_dataset <dataset-id>
python -m src.data_pipeline.knowledge_loader

# Tests
pytest services/data-pipeline/tests -v
```

### Back-office UI

```bash
cd web/app

# Install dependencies
pnpm install

# Start dev server (redirects localhost:3000 → demo.localhost:3000)
pnpm dev

# Build for production
pnpm build

# Lint
pnpm lint

# Unit tests
pnpm test

# E2E tests
pnpm test:e2e
```

### Mobile iOS app (Expo)

```bash
cd services/pwa

# Install dependencies
pnpm install

# Start the Expo dev server (iOS simulator / Expo Go / web)
pnpm start          # or: pnpm ios / pnpm web

# Lint (type check)
pnpm lint
```

To build and run the app in **Xcode / iOS Simulator** (generates the native
`ios/` project via `expo prebuild`, then opens the workspace), follow
[`docs/runbooks/ios-xcode.md`](docs/runbooks/ios-xcode.md).

#### Marketing demo videos

The interactive mock doubles as the source for two marketing walkthrough videos
(customer + electrician journeys). They are generated automatically from the
live Expo web build via Playwright + ffmpeg:

```bash
# Records both journeys and composites framed, captioned MP4s
# into services/pwa/demo-video/ (starts the Expo web server if needed).
services/pwa/scripts/build-demo-videos.sh all
```

See [`services/pwa/demo-video/README.md`](services/pwa/demo-video/README.md) and
the narration script in
[`docs/demo-video-narration.md`](docs/demo-video-narration.md).

### Django admin

```bash
# Create a superuser inside the running container
docker exec -it mtp_admin python manage.py createsuperuser
```

Admin panel: http://localhost:8001/admin

### Supabase CLI (optional)

```bash
# Root package.json only contains Supabase scripts
pnpm supabase:start
pnpm supabase:stop
pnpm supabase:status
```

---

## Code style guidelines

### Python

- Python 3.11+ syntax; type hints everywhere.
- `pydantic` v2 models for API contracts and settings.
- `sqlalchemy` 2 async patterns.
- Formatting and linting by **ruff** (`target-version = "py311"`, line length 100, double quotes, spaces).
- Static checking by **mypy** in strict mode (with `django-stubs` for `services/admin`).
- `structlog` for structured logging.
- Domain code is organised by FastAPI routers; shared primitives live in `packages/shared/py`.

### FastAPI

- Pydantic v2 schemas in `app/schemas.py`.
- Dependency injection for tenant/auth context (`TenantDep`, `CurrentUserDep`, etc.).
- Explicit HTTP exception handling.
- Routers registered in `app/main.py`.

### Django

- Standard Django app layout (`services/admin/admin_project`, `services/admin/operations`).
- Models are **unmanaged** (`managed = False`) and mirror the Alembic-owned schema.
- Register new models in `operations/admin.py`.

### React / TypeScript

- Functional components and hooks.
- Server state via **TanStack Query**, client state via **Zustand**.
- Tailwind utility classes; `cn()` helper from `clsx` + `tailwind-merge`.
- shadcn/ui primitives under `src/components/ui/`.
- API boundary automatically converts camelCase ↔ snake_case with `humps`.
- `credentials: 'include'` on all API calls for cookie-based sessions.

### Multi-tenancy

- Every tenant-scoped table must include `tenant_id`.
- Never rely on query filters alone; RLS + application-layer checks are both required.
- Tests connect through the `mtp_app` role so RLS policies are actually exercised.

### Configuration

- Secrets and per-environment config live in environment variables / `.env`.
- Never commit API keys, database URLs, or payment/webhook credentials.
- `Settings.validate_production()` refuses to boot if insecure defaults are used in production.

### Documentation

- Docstrings and comments are in **English**, matching the product specification.

---

## Testing instructions

### Python

- **Test runner**: `pytest`.
- **Configuration**: see `pyproject.toml` (`[tool.pytest.ini_options]`).
  - `asyncio_mode = "auto"`
  - `testpaths = ["services", "packages", "evals"]`
  - Default excludes eval tests (`-m 'not eval'`); include with `pytest -m eval`.
  - Coverage is configured for `services` and `packages`.
- **API tests** (`services/api/tests/`):
  - Use a fresh test database per session.
  - Connect as the `mtp_app` role so RLS policies are enforced.
  - Include tenancy/isolation, auth, quote lifecycles, invoice lifecycles, RAG, webhooks, calculations, rate limiting, and audit logging.
- **OCERP tests** (`services/ocerp/tests/`): currently parked; run only if the OCERP service is re-enabled.
- **Data-pipeline tests** (`services/data-pipeline/tests/`): loader normalisation and knowledge loader chunking.
- **Evals** (`evals/`): golden-dataset regression harness. The committed `evals/results/summary.json` shows the latest run as **16/17 cases passing (94.12%)**.

### TypeScript / React

- **Unit/integration**: **Vitest** with jsdom. Setup file mocks `matchMedia`, `ResizeObserver`, `IntersectionObserver`, and `recharts`.
- **E2E**: **Playwright** against Docker Compose stack (`web/app/e2e/`).
  - Default suite config: `web/app/playwright.config.ts` (starts stack via `web/app/e2e/start-stack.sh`, bootstraps tenant via `web/app/e2e/bootstrap-tenant.sh`, base URL `http://demo.localhost:3000`).
  - Local production-like validation suite: `web/app/e2e/prod-validation.spec.ts`.
  - Hosted production smoke suite: `web/app/playwright.config.prod-smoke.ts` + `web/app/e2e/prod-smoke.spec.ts`.
- Recommended commands from `web/app`:

```bash
# Fast local full e2e run
pnpm test:e2e

# Production-like local run (loads docker-compose.prod-like.yml)
ENVIRONMENT=production SETUP_TOKEN=<token> pnpm exec playwright test -g "production validation"

# Hosted production smoke run (normally done by GitHub Actions)
E2E_BASE_URL=<web-url> E2E_ADMIN_BASE_URL=<admin-url> \
E2E_DJANGO_ADMIN_USERNAME=superadmin E2E_DJANGO_ADMIN_PASSWORD=<password> \
pnpm exec playwright test --config=playwright.config.prod-smoke.ts
```

### CI

`.github/workflows/ci.yml` runs:

1. Python job:
  - Install with `pip install -e ".[dev]"` using Python 3.12.
  - `ruff check .`
  - `ruff format --check .`
  - `mypy services/api packages/shared/py`
  - `mypy --config-file mypy-admin.ini services/admin`
  - `pytest`

2. TypeScript job (in `web/app`):
  - `pnpm install --frozen-lockfile`
  - `pnpm lint`
  - `pnpm test`
  - `pnpm build`

3. Deploy job (on `main` push after tests):
  - Installs Railway CLI.
  - Runs `railway config apply` from `.railway/railway.ts`.
  - Triggers production smoke workflow (`.github/workflows/smoke-production.yml`).

Use [`docs/runbooks/ci-cd.md`](docs/runbooks/ci-cd.md) as the source of truth for pipeline operations and troubleshooting.

---

## Deployment

The local stack is Docker Compose (see above). For hosted deployment, the
Railway project is declared as Infrastructure as Code in
[`.railway/railway.ts`](.railway/railway.ts) (Railway CLI: `railway config
plan` / `railway config apply`), with app services built from GitHub via the
Railway GitHub App. Setup, secrets, and post-deploy steps are documented in
[`docs/deployment.md`](docs/deployment.md#railway-infrastructure-as-code).

---

## Security considerations

- **Multi-tenant isolation**: enforced via PostgreSQL RLS **and** application-layer tenant scoping. Do not rely on query filters alone.
- **Secrets**: API keys for OpenAI, Paddle, Supabase, Apify, Twilio, Stripe, accounting providers, and database credentials must be kept in environment variables or a secrets manager. Never commit them.
- **Auth**: JWT access tokens are delivered in HTTP-only `session` cookies. Verify `tenant_id` matches the request tenant.
- **RLS role separation**: the application connects as the `mtp_app` role, which cannot bypass RLS. Migrations/owners can own the schema while app connections respect policies.
- **Webhook verification**: Paddle webhook signatures are verified with HMAC-SHA256. Any future Twilio/Stripe/accounting webhooks must follow the same pattern.
- **File uploads**: use presigned MinIO/S3 URLs; restrict file types and sizes; scan uploaded content.
- **Rate limiting**: `slowapi` is configured on auth and AI generation endpoints.
- **VAT / tax**: calculate VAT per UK rules; launch market is the UK.
- **GDPR**: plan data export, right to erasure, consent tracking, and retention policies before handling real customer data.
- **AI guardrails**: the quote engine enforces price-floor validation (minimum margin) and compliance citations. Always disclose AI involvement to end users and provide human handoff.
- **OpenConstructionERP licence**: OCERP is AGPL-3.0. It is deployed as a separate microservice communicating via HTTP only; AGPL code is not embedded in the proprietary API.
- **Production defaults**: `Settings.validate_production()` refuses to start if default secrets or development defaults are present when `ENVIRONMENT=production`.

---

## External integrations

Currently wired or configured:

- **OpenAI** for embeddings and LLM generation via LiteLLM (`text-embedding-3-small`, `gpt-4o-mini`).
- **Qdrant** for vector search.
- **Paddle Billing** for checkout and payment webhooks.
- **MinIO** (local S3) for object storage.
- **Apify** for Screwfix scraping.
- **Supabase Auth** (optional).

Planned in later phases: Twilio (voice/SMS), WhatsApp Business API, Stripe, QuickBooks Online / Xero, SendGrid, Google APIs, ElevenLabs.

---

## Environment variables

Key variables (see `.env.example` for the full template):

- `ENVIRONMENT`, `LOG_LEVEL`
- `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`
- `QDRANT_COLLECTION_NAME`, `QDRANT_KNOWLEDGE_COLLECTION_NAME`
- `MINIO_ENDPOINT`, `MINIO_USE_SSL`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
- `AUTH_SECRET_KEY`
- `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_API_BASE`, `LLM_API_KEY`, `LLM_TEMPERATURE`, `EMBEDDING_MODEL`, `EMBEDDING_API_BASE`, `EMBEDDING_API_KEY`, `LLM_TIMEOUT_SECONDS`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `VITE_API_BASE_URL`
- `APIFY_API_TOKEN`, `PIPELINE_DEMO_MODE`, `SCREWFIX_*`, `TOOLSTATION_ENABLED`, `SCRAPE_FREQUENCY`

---

## Known placeholders and planned work

The following directories are empty placeholders:

- `services/worker/` — Celery task workers.
- `services/pwa/` — React Native + Expo iOS app (trade back-office + customer quote request).
- `services/chatbot-widget/` — Embeddable web chatbot widget.
- `packages/shared/ts/src/` — Shared TypeScript primitives (theme tokens, types).

The OCERP takeoff endpoints (`/ocerp/v1/takeoff/pdf|cad|photo`) are stubs that return HTTP 501.

Planned features not yet implemented: voice AI agent, WhatsApp/SMS messaging, review automation, accounting sync (QuickBooks Online / Xero), email notifications, demand forecasting, advanced analytics.

---

## Reference material

- [`mtp_v2_product_spec.md`](mtp_v2_product_spec.md) — full functional and technical specification.
- [`mtp_v2_architecture.png`](mtp_v2_architecture.png) — three-layer architecture diagram.
- [`README.md`](README.md) — project summary and quick start.
- [`docs/getting-started.md`](docs/getting-started.md) — detailed local setup.
- [`docs/development.md`](docs/development.md) — tests, linting, migrations.
- [`docs/architecture.md`](docs/architecture.md) — layers, services, multi-tenancy.
- [`docs/api.md`](docs/api.md) — REST API overview.
- [`docs/ai-quote-engine.md`](docs/ai-quote-engine.md) — RAG flow and cost database.
- [`docs/deployment.md`](docs/deployment.md) — Docker Compose, Railway (IaC), and production deploy playbooks.
- [`docs/runbooks/`](docs/runbooks/) — operational runbooks (maintenance, incident response, custom domains, CI/CD, go-live checklist).
- [`docs/compliance/gdpr-uk.md`](docs/compliance/gdpr-uk.md) — UK GDPR and data protection compliance.
- [`docs/guides/business-owner-onboarding.md`](docs/guides/business-owner-onboarding.md) — non-technical onboarding for tradespeople.
- [`docs/production-test-report.md`](docs/production-test-report.md) — latest pre-go-live production test results.
- [`docs/agent_knowledge_foundation.md`](docs/agent_knowledge_foundation.md) — knowledge-base design for the quoting agent.
- [`docs/boq_deterministic_rules_audit.md`](docs/boq_deterministic_rules_audit.md) — audit of the BoQ deterministic rules.
- [`docs/UK_Domestic_Electrical_Quoting_Knowledge_Base.md`](docs/UK_Domestic_Electrical_Quoting_Knowledge_Base.md) — curated UK electrical quoting knowledge.

---

*End of AGENTS.md*
