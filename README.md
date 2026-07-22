# My Trade Portal V2

AI-native field service management platform for tradespeople. The current MVP is
focused on **UK electricians**, with a RAG-powered quote engine, CRM, scheduling,
invoicing and payments.

> **Status:** Backend API + Django admin are implemented and testable. The
back-office UI (`web/app`) auth foundation is implemented. The customer PWA,
voice agent, web chatbot and WhatsApp integrations are planned for later phases
(see [`mtp_v2_product_spec.md`](mtp_v2_product_spec.md)).

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
| AI quote generation | ✅ | Local Ollama or OpenAI embeddings + LLM |
| Cost database | ✅ | Seed data + DDC CWICR UK ingestion |
| Jobs | ✅ | Work orders linked to quotes |
| Appointments | ✅ | Scheduling with start/end times |
| Invoicing | ✅ | Auto-numbering, VAT, quote conversion |
| Paddle payments | ✅ | Checkout creation + webhook recording |
| Django admin | ✅ | Read-only mirror of operational schema |
| Back-office UI | 🚧 | Auth + API client integrated; CRUD pages in progress |
| Customer PWA | 🚧 | Planned |
| Voice AI agent | 🚧 | Planned |
| Web chatbot | 🚧 | Planned |
| Accounting sync | 🚧 | Planned |

---

## Quick start

```bash
# 1. Start the local stack
docker compose up -d

# 2. Apply database migrations (or let the API create tables in development)
PYTHONPATH=services/api alembic upgrade head

# 3. Seed a demo tenant and admin user for the back-office UI
cd services/api
python -m app.seed_admin_user

# 4. Seed UK electrical cost items and embed them with your configured model
python -m app.seed_cost_items

# 5. Ingest the DDC CWICR UK cost database (~4k electrical items)
python -m app.ingest_ddc_uk
```

API: http://localhost:8000  
OpenAPI docs: http://localhost:8000/docs  
Back-office UI: http://localhost:3000  
Django admin: http://localhost:8001/admin  

Default back-office login:
- Business slug: `demo`
- Email: `admin@demo.local`
- Password: `password123`

See [`docs/getting-started.md`](docs/getting-started.md) for the full setup,
including Ollama configuration.

---

## Documentation

- [`docs/getting-started.md`](docs/getting-started.md) — install, run, seed data
- [`docs/architecture.md`](docs/architecture.md) — layers, services, multi-tenancy
- [`docs/api.md`](docs/api.md) — endpoints, auth and examples
- [`docs/ai-quote-engine.md`](docs/ai-quote-engine.md) — RAG flow and cost database
- [`docs/development.md`](docs/development.md) — tests, linting, migrations
- [`docs/deployment.md`](docs/deployment.md) — Docker Compose and production notes

---

## Project structure

```
.
├── docker-compose.yml            # Local stack
├── packages/shared/py/           # Shared config/logging/tenancy helpers
├── services/api/                 # FastAPI backend
│   ├── app/routers/              # REST endpoints
│   ├── app/rag/                  # RAG quote engine
│   ├── app/models.py             # SQLAlchemy models
│   ├── alembic/                  # Database migrations
│   └── tests/                    # Pytest suite
├── services/admin/               # Django admin panel
│   └── operations/admin.py       # Admin registrations
└── docs/                         # This documentation
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
