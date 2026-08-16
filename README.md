# My Trade Portal V2

AI-native field service management platform for tradespeople. The current MVP is
focused on **UK electricians**, delivered as a **mobile-first, white-label iOS
app** (Expo/React Native) backed by a multi-tenant FastAPI service, with a React
web app as the desktop back-office companion.

> **Status:** Mid-pivot to mobile-first (see
> [`docs/pivot-migration-plan.md`](docs/pivot-migration-plan.md)). The FastAPI
> backend + Django admin are implemented and testable. The Expo iOS app
> (`services/pwa`) ships as an interactive, offline mock covering the business
> onboarding, customer quote-capture, trade dashboard and customer-portal
> journeys, and is the source for the marketing demo videos. For the MVP the
> OCERP/BoQ engine is **parked** (endpoints return HTTP 501) and the AI quote
> path is a lightweight line-item interpreter. Voice agent, web chatbot and
> WhatsApp integrations remain planned (see
> [`mtp_v2_product_spec.md`](mtp_v2_product_spec.md)).

---

## What it does

My Trade Portal V2 helps trade businesses run their operation from one place:

- **AI quote generation** — describe a job in plain English and get a draft quote
  grounded in a real cost database.
- **CRM** — manage contacts, properties and communication history per tenant.
- **Quotes → Jobs → Appointments → Invoices** — full job lifecycle with VAT
  calculation.
- **Payments** — create Paddle checkouts and record webhook payments against
  invoices.
- **Django admin panel** — staff can review quotes, jobs, invoices and the shared
  cost database.

The platform is **multi-tenant** from day one: every request carries an
`X-Tenant-ID` header and PostgreSQL Row-Level Security enforces isolation.

---

## Implemented capabilities

| Capability | Status | Notes |
|---|---|---|
| FastAPI REST API | ✅ | Auto-generated OpenAPI docs at `/docs` |
| Multi-tenant isolation | ✅ | `X-Tenant-ID` + PostgreSQL RLS |
| Contacts / CRM | ✅ | Create, list and manage customers |
| Manual quotes | ✅ | Create, approve, convert to invoice |
| AI quote generation | ✅ | OpenAI embeddings + LLM via LiteLLM |
| Cost database | ✅ | Seed data + DDC CWICR UK ingestion |
| Jobs | ✅ | Work orders linked to quotes |
| Appointments | ✅ | Scheduling with start/end times |
| Invoicing | ✅ | Auto-numbering, VAT, quote conversion |
| Paddle payments | ✅ | Checkout creation + webhook recording |
| Django admin | ✅ | Read-only mirror of operational schema |
| Back-office UI | ✅ | React SPA, all core pages implemented |
| Mobile iOS app (Expo) | ✅ | Interactive offline mock: onboarding, quote capture, dashboard, customer portal |
| Marketing demo videos | ✅ | Automated customer + electrician journey walkthroughs |
| Business onboarding / quote-request API | ✅ | Routers for onboarding, businesses, customers, pricing, quote requests |
| AI quote interpreter | 🚧 | MVP stub; structured-output model wiring planned |
| OCERP / BoQ engine | ⏸️ | Parked for the mobile pivot (endpoints return 501) |
| Voice AI agent | 🚧 | Planned (behind feature flag) |
| Web chatbot | 🚧 | Planned |
| Accounting sync | 🚧 | Planned |

---

## Quick start

```bash
# 1. Start the local stack
docker compose up -d

# 2. Initialise the database schema (or let the API create tables in development)
python scripts/init_db.py

# 3. Seed a demo tenant and admin user for the back-office UI (local dev only)
cd services/api
SEED_ADMIN_EMAIL=you@example.com SEED_ADMIN_PASSWORD=<choose-a-password> \
  python -m app.seed_admin_user

# 4. Populate the cost database (Screwfix via Apify, or import an existing dataset)
cd services/data-pipeline
python -m data_pipeline.loader
# or, if you already have Apify dataset IDs:
# python -m data_pipeline.import_apify_dataset <dataset-id>

# 5. Ingest the DDC CWICR UK cost database (~4k electrical items)
cd services/api
python -m app.ingest_ddc_uk
```

API: http://localhost:8000
OpenAPI docs: http://localhost:8000/docs
Back-office UI: http://localhost:3000
Django admin: http://localhost:8001/admin

Back-office login (as seeded in step 3):
- Business slug: `demo` (or your `SEED_TENANT_SLUG`)
- Email: the email you set via `SEED_ADMIN_EMAIL`
- Password: the password you set via `SEED_ADMIN_PASSWORD`

See [`docs/getting-started.md`](docs/getting-started.md) for the full setup,
including OpenAI configuration.

---

## Documentation

- [`docs/pivot-migration-plan.md`](docs/pivot-migration-plan.md) — mobile-first pivot plan and milestones
- [`docs/prd-business-onboarding.md`](docs/prd-business-onboarding.md), [`docs/prd-customer-quote-capture.md`](docs/prd-customer-quote-capture.md), [`docs/prd-trade-dashboard-operations.md`](docs/prd-trade-dashboard-operations.md), [`docs/prd-customer-portal.md`](docs/prd-customer-portal.md), [`docs/prd-automated-demo-video.md`](docs/prd-automated-demo-video.md) — PRDs for the pivot
- [`docs/demo-video-narration.md`](docs/demo-video-narration.md) — narration script for the marketing videos
- [`docs/getting-started.md`](docs/getting-started.md) — install, run, seed data
- [`docs/architecture.md`](docs/architecture.md) — layers, services, multi-tenancy
- [`docs/api.md`](docs/api.md) — endpoints, auth and examples
- [`docs/ai-quote-engine.md`](docs/ai-quote-engine.md) — RAG flow and cost database (OCERP path, parked)
- [`docs/development.md`](docs/development.md) — tests, linting, migrations
- [`docs/deployment.md`](docs/deployment.md) — local Docker Compose, Railway IaC, and production deploy playbooks
- [`docs/runbooks/`](docs/runbooks/) — operational runbooks (maintenance, incident response, custom domains, CI/CD, go-live)
- [`docs/compliance/gdpr-uk.md`](docs/compliance/gdpr-uk.md) — UK GDPR and data protection compliance
- [`docs/guides/business-owner-onboarding.md`](docs/guides/business-owner-onboarding.md) — non-technical onboarding for tradespeople
- [`docs/production-test-report.md`](docs/production-test-report.md) — latest pre-go-live production test results
- [`user-docs/`](user-docs/) — Mintlify customer help centre (quotes, jobs, invoices, payments)

---

## Project structure

```
.
├── docker-compose.yml            # Local stack
├── packages/shared/py/           # Shared config/logging/tenancy helpers
├── services/api/                 # FastAPI backend
│   ├── app/routers/              # REST endpoints
│   ├── app/rag/                  # RAG quote engine
│   ├── app/models.py             # SQLAlchemy models (schema source of truth)
│   └── tests/                    # Pytest suite
├── services/admin/               # Django admin panel
│   └── operations/admin.py       # Admin registrations
├── docs/                         # Engineering documentation
└── user-docs/                    # Mintlify customer help centre
```

---

## Product specification

The long-form product vision, roadmap and pricing strategy are in
[`mtp_v2_product_spec.md`](mtp_v2_product_spec.md).

---

## License & attribution

- Platform code is proprietary.
- The DDC CWICR cost database is used under CC BY 4.0 (OpenConstructionERP).
- See [`mtp_v2_product_spec.md`](mtp_v2_product_spec.md) Appendix A for the full
  list of open-source components.
