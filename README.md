# My Trade Portal

A field-service management product for UK electricians and trade businesses.
It covers quotes (including AI-drafted, guide-priced line items), jobs,
scheduling, invoices, reminders, CRM, reviews, and a tenant-branded customer
portal.

## Layout

| Path | What it is |
|---|---|
| `services/api/` | FastAPI backend (SQLAlchemy + asyncpg, RLS-enforced multi-tenancy), including the AI quote pipeline in `app/rag/` |
| `services/admin/` | Django admin back-office |
| `services/data-pipeline/` | Apify/Screwfix cost-item scraper feeding the Qdrant catalogue |
| `mobile/` | React Native + Expo iOS app (tradesperson and customer flows) |
| `web/app/` | React + Vite back-office SPA |
| `web/landing/` | Marketing site and tenant-subdomain customer portal |
| `packages/shared/` | Shared TypeScript design tokens (`ts/`) and Python primitives (`py/mtp_shared`) |
| `security/` | Security test suite (targets a live backend) |
| `docs/` | Active documentation; legacy material lives in `docs/archived/` |

## Running the stack

Local infrastructure (PostgreSQL, Redis, Qdrant, MinIO, Mailpit) plus the
application services run via Docker Compose:

```bash
docker compose up -d postgres redis qdrant minio mailpit   # data infra only
docker compose up -d                                       # full stack
```

Per-surface development:

```bash
# API (Python 3.11+, venv at .venv)
source .venv/bin/activate
cd services/api && python -m pytest tests -q

# Web back-office
cd web/app && pnpm install && pnpm dev

# Mobile (iOS Simulator, macOS + Xcode required)
cd mobile && pnpm install && pnpm ios
# Or one-shot: backend + simulator build via mobile/scripts/run-ios.sh
```

## Further reading

- `AGENTS.md` — the detailed contributor reference: stack, conventions,
  build/test/run commands, deployment, and known issues.
- `docs/` — product and architecture documentation.
- `.env.example` — environment variable template.
