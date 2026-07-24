# Go-Live Checklist — My Trade Portal V2

**Status:** pre-go-live  
**Target:** production-ready by tomorrow  
**Railway project:** `MyTradePortal` — `30feaeee-9464-41ac-9b17-d07ae4cfcd09`  
**Environment:** `production`  

This runbook covers the final checks and actions required before My Trade Portal V2 serves live UK electrician customers. It assumes the reader is technical but not already familiar with every component.

---

## Current production state

| Service | Type | Current public domain / note |
|---|---|---|
| `api` | FastAPI backend | `https://api-production-83b8.up.railway.app` |
| `web` | React back-office SPA | `https://web-production-0919a.up.railway.app` |
| `admin` | Django admin panel | `https://admin-production-5c08.up.railway.app` |
| `ocerp` | BoQ / pricing engine | Private service; no public domain. Used by `api` over internal Railway network |
| `data-pipeline` | Cost-data loader / scraper | No public domain; runs on demand |
| `minio` | Object storage (S3-compatible) | Public domain required; target port `9000` |
| `qdrant` | Vector database | No public domain |
| `db` | Railway Postgres | Native plugin |
| `redis` | Railway Redis | Native plugin |

**Region alignment:** All services are deployed in the `europe-west4-drams3a` (Amsterdam) region as declared in IaC, the closest Railway region to the UK market.

---

## 1. Final code readiness (must pass before any production change)

- [ ] All code is merged into `main` and the branch is green.
- [ ] CI has passed for the latest `main` commit: `ruff check .`, `ruff format --check .`, `mypy services/api packages/shared/py`, `mypy --config-file mypy-admin.ini services/admin`, `pytest`, and `pnpm --filter web lint / test / build`.
- [ ] No uncommitted local changes remain on the deploy machine.

Verify the latest commit status:

```bash
git checkout main
git pull origin main
git log --oneline -1
```

Then confirm the CI run is green in the GitHub Actions tab before moving on.

---

## 2. Infrastructure and IaC verification

### 2.1 Verify the Railway IaC plan

From the repository root, after `railway login` and `railway link`:

```bash
cd .railway
npm ci
railway config plan
```

Expected: the plan shows no unexpected deletions and the `api`, `ocerp`, `web`, `admin`, and `data-pipeline` services all target `europe-west4-drams3a` (Amsterdam).

If `admin` still shows `sfo` in the dashboard, reconcile it by updating the service region in the Railway UI or by re-applying the IaC and confirming the diff.

### 2.2 Confirm all services are deployed and healthy

Use the Railway dashboard or CLI:

```bash
railway status
railway logs --service api
railway logs --service admin
railway logs --service ocerp
railway logs --service web
```

Every service should show **Healthy**.

### 2.3 Verify public domains and TLS

Required domains:

- `api` — public domain generated, HTTPS working
- `web` — public domain generated, HTTPS working
- `admin` — public domain generated, HTTPS working
- `minio` — public domain generated, target port **9000**, HTTPS working

Quick checks:

```bash
curl -I https://api-production-83b8.up.railway.app/health
curl -I https://web-production-0919a.up.railway.app
curl -I https://admin-production-5c08.up.railway.app/health
```

All should return `200 OK` over TLS.

**Note:** Railway IaC cannot create domains. If any are missing, generate them manually in the Railway dashboard before continuing.

---

## 3. Secrets and environment variables

The following `preserve()` variables must be set in the Railway dashboard (not in the repo). Do not rely on defaults.

| Service | Variable | Status | Notes |
|---|---|---|---|
| `api` | `OPENAI_API_KEY` | Required | LLM + embeddings |
| `api` | `AUTH_SECRET_KEY` | Required | Strong random string, JWT signing |
| `api` | `SETUP_TOKEN` | Required | Strong random string; gates `POST /tenants` |
| `api` | `MINIO_ACCESS_KEY` | Required | Matches `MINIO_ROOT_USER` |
| `api` | `MINIO_SECRET_KEY` | Required | Matches `MINIO_ROOT_PASSWORD` |
| `api` | `RAILWAY_TOKEN` | Required | Project token for `GET /feature-flags` |
| `minio` | `MINIO_ROOT_USER` | Required | Same as `MINIO_ACCESS_KEY` |
| `minio` | `MINIO_ROOT_PASSWORD` | Required | Same as `MINIO_SECRET_KEY` |
| `admin` | `SECRET_KEY` | Required | Django secret key |
| `admin` | `DJANGO_SUPERUSER_PASSWORD` | Required | Set via GitHub secret / Railway dashboard |
| `data-pipeline` | `OPENAI_API_KEY` | Required | Embeddings |
| `data-pipeline` | `APIFY_API_TOKEN` | Required | Screwfix scraping |
| `api` | `PADDLE_API_KEY` | Optional | Payments; set if Paddle is enabled |
| `api` | `PADDLE_WEBHOOK_SECRET` | Optional | Webhook HMAC verification |
| `api` | `PADDLE_SANDBOX` | Optional | Default `true` in IaC; set `false` for live payments |

Also verify GitHub Actions environment `MyTradePortal/Production` secrets:

- `RAILWAY_TOKEN`
- `DJANGO_SUPERUSER_PASSWORD`
- `E2E_BASE_URL` (e.g. `https://web-production-0919a.up.railway.app`)
- `E2E_ADMIN_BASE_URL` (e.g. `https://admin-production-5c08.up.railway.app`)
- `DATABASE_URL`

Command to audit Railway variables for the `api` service:

```bash
railway variables --service api --environment production
```

(Use the same for `admin`, `data-pipeline`, and `minio`.)

---

## 4. Database and schema readiness

- [ ] The API pre-deploy command `python scripts/init_db.py` has run successfully on the latest deploy.
- [ ] The admin pre-deploy command `sh -c 'python scripts/init_db.py && python scripts/ensure_superuser.py'` has run successfully.
- [ ] The `mtp_app` role exists and cannot bypass Row-Level Security (RLS).
- [ ] All tenant-scoped tables (`users`, `contacts`, `quotes`, `quote_line_items`, `bill_of_quantities`, `boq_line_items`, `jobs`, `appointments`, `invoices`, `invoice_line_items`, `payments`, `communications`, `reviews`, `audit_logs`) have RLS enabled.

Check the latest deploy logs for the `api` and `admin` services. If the init step failed, re-run manually:

```bash
railway run --service api python scripts/init_db.py
railway run --service admin python scripts/init_db.py
```

Verify RLS is enabled at the database level:

```bash
railway run --service api psql "$DATABASE_URL" -c ""
SELECT schemaname, tablename, rowsecurity FROM pg_tables WHERE rowsecurity = true;
""
```

(The `api` and `admin` services both use the same Railway Postgres database.)

---

## 5. MinIO and uploads

- [ ] The `minio` console and S3 API are reachable over HTTPS.
- [ ] The bucket `mtp-uploads` exists.
- [ ] `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` on `api` exactly match `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` on `minio`.
- [ ] `MINIO_USE_SSL=true` on the `api` service.

Create the bucket if missing:

```bash
# via the MinIO console at the generated domain on port 9001
# or via the mc CLI once configured:
mc mb local/mtp-uploads
```

Test presigned upload generation by logging into the back office and uploading a file on a customer or quote record.

---

## 6. AI / RAG / cost data readiness

### 6.1 Seed the cost database and knowledge base

Run these from the Railway CLI once, or re-run if data appears missing:

```bash
railway run --service data-pipeline python -m data_pipeline.load_curated_seed
railway run --service data-pipeline python -m data_pipeline.knowledge_loader
```

These commands populate:

- Postgres `cost_items` table
- Qdrant `cost_items` collection
- Qdrant `quoting_knowledge` collection

### 6.2 Verify Qdrant collections and API health

```bash
railway run --service api curl "$QDRANT_URL/collections"
```

Expected collections: `cost_items` and `quoting_knowledge`.

### 6.3 OpenAI readiness

- [ ] `OPENAI_API_KEY` is set on `api`, `ocerp`, and `data-pipeline`.
- [ ] OpenAI account has billing enabled and a non-zero credit limit.
- [ ] A usage alert is configured in the OpenAI dashboard to avoid surprise overages.
- [ ] The embedding model (`text-embedding-3-small`) and chat model (`gpt-4o-mini`) are available in the account.

### 6.4 OCERP health

OCERP has no public domain. Check it via Railway private access or internal healthcheck:

```bash
railway run --service ocerp curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`.

---

## 7. First tenant and admin user

**Do not use `app.seed_admin_user` in production.** Create the first tenant manually.

### Option A: Django admin UI

1. Log in at `https://admin-production-5c08.up.railway.app/admin/` with username `superadmin` and the password from `DJANGO_SUPERUSER_PASSWORD`.
2. Go to **Operations → Tenants → Add**.
3. Create a slug (e.g. `demo`) and name.
4. Go to **Operations → Users → Add**.
5. Select the tenant, set the admin email, full name, role (`admin`), and password, then save.

### Option B: Gated `POST /tenants` endpoint

```bash
curl -X POST https://api-production-83b8.up.railway.app/tenants \
  -H "Content-Type: application/json" \
  -H "X-Setup-Token: $SETUP_TOKEN" \
  -d '{
    "slug": "demo",
    "name": "Demo Electrical Ltd",
    "admin_email": "owner@demo-electrical.example.com",
    "admin_password": "..."
  }'
```

After the first tenant is created, **rotate or remove `SETUP_TOKEN`** so the endpoint cannot be used to create further tenants without oversight.

---

## 8. Security and compliance verification

### 8.1 Run dependency audits

```bash
source .venv/bin/activate
pip-audit --desc --audit-level=high

cd web/app
pnpm audit --audit-level=high
```

Resolve any high-severity findings before go-live.

### 8.2 Run the security test suite against production

```bash
export SECURITY_API_BASE_URL=https://api-production-83b8.up.railway.app
export SECURITY_ADMIN_BASE_URL=https://admin-production-5c08.up.railway.app
export SECURITY_TENANT_SLUG=demo
export SECURITY_ADMIN_EMAIL=owner@demo-electrical.example.com
export SECURITY_ADMIN_PASSWORD=...
# Optional: a second tenant for cross-tenant isolation tests
export SECURITY_SECONDARY_TENANT_SLUG=demo2
export SECURITY_SECONDARY_ADMIN_EMAIL=owner2@demo2.example.com
export SECURITY_SECONDARY_ADMIN_PASSWORD=...

pytest -m security -v --no-cov
```

All tests should pass. Failures indicate a potential isolation or access-control regression that must be fixed before go-live.

### 8.3 Trigger the Security Audit GitHub Actions workflow

In the GitHub Actions tab, run `.github/workflows/security-audit.yml` manually (workflow dispatch) against production. Review the OWASP, multi-tenancy, SOC2, and dependency-audit results.

### 8.4 SOC2 evidence readiness

Confirm these evidence artifacts are current (see `docs/soc2-controls.md` and `security/README.md`):

- `security/tests/test_multitenancy.py` — logical access controls (CC6.1)
- `security/tests/test_soc2.py` — encryption and HTTPS (CC6.6)
- `services/api/tests/test_audit.py` — audit logging (CC7.2)
- `pip-audit` / `pnpm audit` outputs — vulnerability detection (CC7.1)
- IaC review and CI run history — change management (CC8.1)

---

## 9. Functional verification and smoke tests

### 9.1 Manual health checks

```bash
curl https://api-production-83b8.up.railway.app/health
curl https://web-production-0919a.up.railway.app
curl https://admin-production-5c08.up.railway.app/health
railway run --service ocerp curl http://localhost:8000/health
```

All should return `200`.

### 9.2 Back-office login

1. Open `https://web-production-0919a.up.railway.app/login`.
2. Enter the tenant slug (e.g. `demo`), admin email, and password.
3. Confirm the dashboard loads and the tenant selector resolves correctly.

### 9.3 Core business flow

In the back office, verify:

- [ ] Create a customer.
- [ ] Create a manual quote.
- [ ] Generate an AI quote (`/quotes/generate` or `/quotes/generate-boq` with `use_ocerp=true`) and confirm line items appear.
- [ ] Approve the quote and convert it to an invoice.
- [ ] Create a job and an appointment.
- [ ] Upload a file to a customer or quote record.
- [ ] Review the PDF export of the quote.

### 9.4 Production smoke test workflow

Trigger `.github/workflows/smoke-production.yml` in GitHub Actions (or let it run automatically after the CI deploy). It creates a temporary tenant with slug prefix `prod-smoke-`, exercises the customer, quote, invoice, and job flows, and tears the tenant down afterwards.

Required secrets: `E2E_BASE_URL`, `E2E_ADMIN_BASE_URL`, `DATABASE_URL`, and `DJANGO_SUPERUSER_PASSWORD`.

### 9.5 Manual Playwright smoke test (optional)

From the `web/app` directory:

```bash
cd web/app
E2E_BASE_URL=https://web-production-0919a.up.railway.app \
E2E_ADMIN_BASE_URL=https://admin-production-5c08.up.railway.app \
E2E_DJANGO_ADMIN_USERNAME=superadmin \
E2E_DJANGO_ADMIN_PASSWORD=... \
pnpm exec playwright test --config=playwright.config.prod-smoke.ts
```

---

## 10. Payments (if enabled before go-live)

Paddle is wired but currently sandboxed by default (`PADDLE_SANDBOX=true`). To go live with payments:

- [ ] Obtain live Paddle API key and webhook secret.
- [ ] Set `PADDLE_API_KEY`, `PADDLE_WEBHOOK_SECRET`, and `PADDLE_SANDBOX=false` on the `api` service.
- [ ] Configure the Paddle webhook endpoint to `https://api-production-83b8.up.railway.app/webhooks/paddle`.
- [ ] Verify webhook signature verification using HMAC-SHA256 (`services/api/app/paddle_client.py`).
- [ ] Run a small live checkout and refund it.

If payments are not enabled at go-live, keep `PADDLE_SANDBOX=true` and document the limitation.

---

## 11. Feature flags

The UI queries `GET /feature-flags` and hides unreleased capabilities by default. For go-live, confirm these are off unless explicitly ready:

| Flag | Go-live state |
|---|---|
| `voice_ai_insights` | `false` |
| `demand_forecasting` | `false` |
| `external_integrations` | `false` |

Check `GET https://api-production-83b8.up.railway.app/feature-flags` with an authenticated session and confirm only released features are enabled.

---

## 12. Go / No-Go decision

Before declaring go-live, confirm:

| Gate | Criterion | Owner |
|---|---|---|
| CI/CD | Latest `main` commit green and deployed | Engineering Lead |
| IaC | `railway config plan` shows no destructive drift | Platform Engineer |
| Regions | All services deployed in `europe-west4-drams3a` (Amsterdam) | Platform Engineer |
| Secrets | All required `preserve()` variables set and non-default | Security Lead |
| Database | `init_db.py` succeeded; RLS active on all tenant tables | Backend Engineer |
| Object storage | `mtp-uploads` bucket exists and uploads work | Backend Engineer |
| AI/RAG | Qdrant collections seeded; OpenAI billing healthy | ML Engineer |
| Tenant | At least one production tenant created; `SETUP_TOKEN` rotated | Backend Engineer |
| Security | Dependency audits and security pytest suite pass | Security Lead |
| Smoke test | Production smoke test workflow passes | QA/Engineering Lead |
| Rollback | Previous healthy deployment identified in Railway | Engineering Lead |

Only proceed when all gates are green.

---

## 13. Rollback plan

If anything fails after go-live, use the Railway dashboard to redeploy the previous healthy deployment for the affected service. Steps:

1. In the Railway dashboard, open the affected service.
2. Go to **Deployments**.
3. Select the last known healthy deployment.
4. Click **Redeploy**.

Alternatively, revert the commit on `main` and let the CI/CD pipeline redeploy:

```bash
git revert HEAD
git push origin main
```

For database issues, restore from the most recent Railway Postgres backup. Do not run `init_db.py` on a populated database unless you are certain it is safe and idempotent.

---

## 14. Post-go-live monitoring (first 24 hours)

- [ ] Watch Railway service health and deploy logs for all services.
- [ ] Monitor OpenAI usage dashboard for unexpected cost spikes.
- [ ] Monitor Paddle transaction webhooks (if enabled) and the `payments` / `webhook_logs` tables.
- [ ] Check `audit_logs` for failed logins, tenant access violations, and quote-generation errors.
- [ ] Verify daily/scheduled data-pipeline runs: `SCRAPE_FREQUENCY` is set to `monthly` or `daily` as intended.
- [ ] Confirm `slowapi` rate limits are not blocking legitimate traffic.
- [ ] Keep the production smoke test workflow ready to re-run after any hotfix.

Useful commands:

```bash
railway status
railway logs --service api --tail 100
railway logs --service web --tail 100
railway logs --service admin --tail 100
```

---

## 15. Known limitations and follow-up after go-live

- The `services/pwa`, `services/worker`, and `services/chatbot-widget` directories are empty placeholders; customer-facing PWA and chatbot are not live yet.
- OCERP takeoff endpoints (`/ocerp/v1/takeoff/pdf|cad|photo`) return `501 Not Implemented`.
- Advanced features (voice AI, WhatsApp/SMS, accounting sync, demand forecasting) are behind feature flags and disabled by default.
- All services are aligned to the IaC target region `europe-west4-drams3a` (Amsterdam).
- Email currently uses Mailpit in local development; production email delivery (SendGrid, Postmark, etc.) should be configured for customer notifications.

---

## Quick reference commands

```bash
# IaC plan and apply
cd .railway
npm ci
railway config plan
railway config apply

# Service status and logs
railway status
railway logs --service api
railway logs --service admin
railway logs --service ocerp
railway logs --service web

# Manual database init (if needed)
railway run --service api python scripts/init_db.py
railway run --service admin python scripts/init_db.py

# Seed data
railway run --service data-pipeline python -m data_pipeline.load_curated_seed
railway run --service data-pipeline python -m data_pipeline.knowledge_loader

# Security checks
pytest -m security -v --no-cov
pip-audit --desc --audit-level=high
cd web/app && pnpm audit --audit-level=high

# Production smoke test (manual)
cd web/app
E2E_BASE_URL=https://web-production-0919a.up.railway.app \
E2E_ADMIN_BASE_URL=https://admin-production-5c08.up.railway.app \
E2E_DJANGO_ADMIN_USERNAME=superadmin \
E2E_DJANGO_ADMIN_PASSWORD=... \
pnpm exec playwright test --config=playwright.config.prod-smoke.ts

# Health checks
curl https://api-production-83b8.up.railway.app/health
curl https://admin-production-5c08.up.railway.app/health
curl https://web-production-0919a.up.railway.app
```
