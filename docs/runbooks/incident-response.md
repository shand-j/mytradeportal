# Incident Response Runbook

This document provides the operational procedures for detecting, responding to, and recovering from production incidents in **My Trade Portal V2**. It is grounded in the actual production deployment on Railway, the GitHub Actions CI/CD pipeline, and the service architecture described in [`AGENTS.md`](../../AGENTS.md) and [`docs/deployment.md`](../../deployment.md).

## Current production context

| Item | Value |
|------|-------|
| Railway project | `MyTradePortal` (`30feaeee-9464-41ac-9b17-d07ae4cfcd09`) |
| Environment | `production` |
| Region target | `europe-west4-drams3a` (Amsterdam) via [`.railway/railway.ts`](../../.railway/railway.ts) |
| Known discrepancy | Native Postgres and Redis plugins are currently in `sfo`. Application services and MinIO are in Amsterdam. |
| Public services | `https://<api-domain>`, `https://<web-domain>`, `https://<admin-domain>` |
| Internal services | `ocerp`, `data-pipeline`, `minio`, `qdrant`, Postgres, Redis |

## 1. Severity classification

| Severity | Criteria | Initial response time | Examples |
|----------|----------|----------------------|----------|
| **P1 — Critical** | Complete outage, data loss, active security breach, or payment processing failure affecting all tenants | 15 minutes | API 500s for all requests, Postgres unavailable, RLS bypass suspected, Paddle webhooks failing en masse |
| **P2 — High** | Major feature degraded for multiple tenants, but core login/quote flows partially work | 1 hour | AI quote generation fails, MinIO uploads fail, OCERP down (manual quotes still work) |
| **P3 — Medium** | Single-tenant issue, non-core feature broken, or intermittent errors | 4 hours | Analytics dashboard fails, one tenant reports wrong VAT calculation |
| **P4 — Low** | Cosmetic, performance degradation, or minor warnings | Next business day | Slow page loads, elevated 4xx rate from scanners |

## 2. On-call and escalation

1. **Primary on-call**: Engineering lead who merged the latest `main` deploy or is designated for the week.
2. **Secondary on-call**: Another engineer with Railway CLI access and GitHub Actions permissions.
3. **Escalation path**: Primary → Secondary → Engineering manager → CTO.
4. **Communication channels**:
   - Internal incident channel: `#incidents` (or equivalent).
   - Customer status page: update if P1/P2 and customers are affected.
   - War room: start a video call for P1 incidents.

## 3. Standard incident response workflow

1. **Detect** (monitoring alert, customer report, smoke test failure, or CI error).
2. **Triage** within the severity SLA and assign an incident commander.
3. **Stabilize** by isolating the affected component (rollback, scale, disable feature flag, restart service).
4. **Investigate** using logs, metrics, and the procedures in this document.
5. **Communicate** internally and externally per the severity table.
6. **Recover** fully and verify with health checks and smoke tests.
7. **Review** within 48 hours (post-mortem for P1/P2, retrospective for P3).

## 4. Detection sources

| Source | What to watch | How to access |
|--------|---------------|---------------|
| Railway health checks | Service status, deployment failures, CPU/memory | `railway environment` or Railway dashboard |
| GitHub Actions | CI failures, deploy failures, smoke test failures | `https://github.com/shand-j/mytradeportal/actions` |
| Application logs | Structured `structlog` output in API and OCERP | `railway logs --service <service>` |
| Audit logs | `audit_logs` table in Postgres (`services/api/app/audit.py`) | Django admin or direct SQL with RLS bypass |
| Health endpoints | `GET /health` on API, OCERP, admin | `curl` commands below |
| Smoke tests | Playwright end-to-end production test | `.github/workflows/smoke-production.yml` |
| External APIs | OpenAI status, Paddle status, Apify status | Vendor status pages |

### Quick health checks

```bash
# API
export API_URL=https://<api-domain>
curl -s "$API_URL/health" | jq .

# OCERP
# Only if exposed publicly; otherwise use private networking or skip.
# curl -s https://<ocerp-public-domain>/health

# Admin
curl -s https://<admin-domain>/health

# Web (should return 200 on the SPA index)
curl -s -o /dev/null -w "%{http_code}" https://<web-domain>
```

## 5. Common incident procedures

### 5.1 Service is completely down (P1)

**Symptoms**: Health endpoint returns 5xx/timeout, web UI blank, customers cannot log in.

1. Check Railway service status:
   ```bash
   railway environment
   railway status --service api
   railway status --service web
   ```
2. View live logs:
   ```bash
   railway logs --service api --tail 200
   railway logs --service ocerp --tail 200
   railway logs --service admin --tail 200
   ```
3. Identify the most recent deploy:
   ```bash
   railway list deployments --service api --environment production
   ```
4. If the incident started with the latest deploy, **rollback immediately** (see section 7).
5. If the issue is a database connection failure, check Postgres status in Railway dashboard.
6. If `Settings.validate_production()` is blocking startup, verify preserved secrets are set (`AUTH_SECRET_KEY`, `SETUP_TOKEN`, `APP_ROLE_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `OPENAI_API_KEY`).

### 5.2 Admin returns 400 Bad Request

**Symptoms**: `/admin/login/` or `/admin/` returns HTTP 400; static files (`/static/...`) load fine.

**Root cause**: the Django container was deployed before the admin public domain existed, so `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are stale.

1. Confirm the admin public domain is generated:
   ```bash
   railway domain list --service admin --json
   ```
2. Trigger a redeploy so Django picks up the updated variables:
   ```bash
   railway service redeploy --service admin
   ```
3. If the problem persists, check the `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` variables in the Railway dashboard and compare them to the current domain.
4. Verify the fix:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://<admin-domain>/admin/login/
   ```

### 5.3 Database / PostgreSQL issues

**Symptoms**: API returns database errors, queries timeout, Django admin fails to load.

1. Check Postgres status and connection metrics in Railway dashboard.
2. Check API logs for `asyncpg` or `sqlalchemy` errors.
3. Run a manual connection test:
   ```bash
   railway run --service api python -c "
   import asyncio
   from services.api.app.database import engine
   from sqlalchemy import text
   async def t():
       async with engine.begin() as conn:
           result = await conn.execute(text('SELECT 1'))
           print(result.scalar())
   asyncio.run(t())
   "
   ```
4. If RLS appears misconfigured (e.g., users seeing other tenants' data), stop the affected endpoint and investigate:
   - `app.current_tenant` is set by `dependencies.py` on each request.
   - Verify the `mtp_app` role is being used and policies are enabled.
   - Re-run `scripts/init_db.py` only if you understand the impact; it is idempotent but does not restore data.
5. For data corruption or suspected loss, restore from Railway Postgres backup; do not attempt manual row edits in production without a ticket trail.

### 5.4 Multi-tenant isolation failure (P1)

**Symptoms**: A user sees another tenant's contacts, quotes, or invoices.

1. **Contain**: Immediately disable the affected endpoint or set the service to sleep via Railway dashboard if no safe fix is available.
2. **Verify**: Use the security test suite to confirm the breach scope:
   ```bash
   export SECURITY_API_BASE_URL=https://<api-domain>
   export SECURITY_ADMIN_BASE_URL=https://<admin-domain>
   export SECURITY_TENANT_SLUG=<affected-tenant>
   export SECURITY_ADMIN_EMAIL=<admin-email>
   export SECURITY_ADMIN_PASSWORD=<password>
   pytest -m security -v --no-cov security/tests/test_multitenancy.py
   ```
3. Inspect RLS policies:
   ```sql
   -- Run with a role that can bypass RLS or as schema owner
   SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
   FROM pg_policies
   WHERE schemaname = 'public'
   ORDER BY tablename, policyname;
   ```
4. Check for application-layer bypasses (e.g., a route missing `TenantDep` or `CurrentUserDep`) in `services/api/app/dependencies.py` and the relevant router.
5. Document affected tenants and data access; notify compliance lead for SOC2/CC6.1 review.
6. After remediation, run the full security suite before declaring the incident closed.

### 5.5 AI / OpenAI quote generation failure (P2)

**Symptoms**: `POST /quotes/generate` or `POST /quotes/generate-boq` returns 5xx or hangs; users cannot create AI quotes.

1. Check OpenAI status page and API key quota.
2. Verify the API service can reach OpenAI:
   ```bash
   railway logs --service api --tail 100 | grep -i openai
   ```
3. Check Qdrant health and collection state:
   ```bash
   railway logs --service qdrant --tail 50
   curl -s http://<qdrant-private-domain>:6333/collections/cost_items
   curl -s http://<qdrant-private-domain>:6333/collections/quoting_knowledge
   ```
4. If collections are empty or missing, trigger the data-pipeline Screwfix scrape:
   ```bash
   railway run --service data-pipeline python -m data_pipeline.loader
   ```
   > If Apify reports a monthly usage limit, AI quotes will only produce
   > labour-line items until the limit resets or the plan is upgraded.
5. If OCERP is down, the in-house RAG path (`/quotes/generate`) may still work. Verify the `OCERP_URL` variable in the API service points to the correct private domain.
6. As a temporary mitigation, disable AI generation in the UI and instruct users to create manual quotes.

### 5.6 Paddle payment / webhook failure (P2)

**Symptoms**: Invoices fail to mark paid, Paddle checkout errors, or webhook logs show HMAC failures.

1. Check Paddle sandbox status and API credentials:
   - `PADDLE_API_KEY` and `PADDLE_WEBHOOK_SECRET` must be set on the `api` service.
2. Verify webhook signature logic in `services/api/app/paddle_client.py` has not changed.
3. Check recent webhook records in `payments` table or API logs.
4. Replay a failed webhook only after verifying the payload authenticity.
5. If webhooks are broadly failing, contact Paddle support and switch to manual reconciliation via Django admin.

### 5.7 MinIO / file upload failure (P2)

**Symptoms**: Presigned upload URLs fail, uploads return 403, or uploaded files are unreachable.

1. Check MinIO service status and bucket existence:
   ```bash
   railway status --service minio
   ```
2. Verify environment variables on the `api` service:
   - `MINIO_ENDPOINT` must be the public Railway domain (not private).
   - `MINIO_USE_SSL` must be `true`.
   - `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` must match `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` on the `minio` service.
3. Verify the `mtp-uploads` bucket exists via the MinIO console (port 9001).
4. If credentials are rotated, redeploy both `minio` and `api` services so the changes propagate.

### 5.8 OCERP microservice failure (P2)

**Symptoms**: BoQ generation fails, but other API endpoints work.

1. Check OCERP health and logs:
   ```bash
   curl -s https://<ocerp-public-domain>/health
   railway logs --service ocerp --tail 100
   ```
2. If OCERP is the only failing service, the API can still serve manual quotes and the in-house RAG path. Consider routing AI traffic to `/quotes/generate` temporarily.
3. If the failure is data-related (Qdrant missing collections), re-run the loaders from section 5.4.
4. If OCERP fails to start with `validate_production` errors, check `OPENAI_API_KEY` and Qdrant connectivity.

### 5.9 Security incident (P1/P2)

**Symptoms**: Unauthorized access, suspicious API traffic, leaked secret, or agentic pen-test critical finding.

1. **Contain**: Rotate the affected secret or disable the affected service immediately.
2. **Assess scope**: Run the security test suite and review audit logs (`audit_logs` table via Django admin or SQL with RLS bypass).
3. **Rotate secrets** via Railway dashboard and GitHub Actions secrets:
   - `AUTH_SECRET_KEY` → force all users to re-login.
   - `SETUP_TOKEN` → prevent unauthorized tenant creation.
   - `PADDLE_WEBHOOK_SECRET` → reconfigure Paddle webhook endpoint.
   - `MINIO_ROOT_PASSWORD` / `MINIO_SECRET_KEY` → redeploy both services.
4. **Deploy a fix** via a hotfix branch and PR to `main`; CI will deploy automatically.
5. **Run full security audit** before closing the incident:
   ```bash
   pip-audit --desc --audit-level=high
   pnpm audit --audit-level=high
   pytest -m security -v --no-cov
   ```
6. Notify the compliance lead for SOC2/CC7.2/CC7.1 review.

### 5.10 Deploy failure or CI breakage (P2)

**Symptoms**: GitHub Actions CI fails, `railway config apply` fails, or service deploys but never becomes healthy.

1. Inspect the failed workflow run in GitHub Actions.
2. Common failures and fixes:
   - **Lint/type/test failure**: fix locally, push a new commit.
   - **`railway config apply` failure**: ensure `RAILWAY_TOKEN` is valid, Railway CLI is installed, and the linked project/environment matches.
   - **Admin fails to start with "relation does not exist"**: re-run the pre-deploy command manually:
     ```bash
     railway run --service api python scripts/init_db.py
     railway run --service admin python manage.py migrate --noinput
     ```
   - **Service never becomes healthy**: check that `PORT` matches the Dockerfile/healthcheck target (`api`/`ocerp`: 8000, `admin`: 8001, `web`: 80).
3. If the deploy is partially applied, redeploy the previous healthy deployment of the affected service from the Railway dashboard.

## 6. Incident communication template

### Internal update (every 30 minutes for P1, every 2 hours for P2)

```text
Incident: [short title]
Severity: P1/P2/P3/P4
Status: Investigating / Mitigated / Resolved
Impact: [which tenants/features are affected]
Lead: [name]
Next update: [time]
```

### Customer-facing status update (P1/P2 only)

```text
My Trade Portal is currently experiencing [brief description].
Some users may be unable to [log in / generate quotes / upload files / etc.].
We are actively working on a fix and will update this page in 30 minutes.
```

## 7. Rollback procedures

### Roll back a bad service deploy via Railway dashboard

1. Open the affected service in the Railway dashboard.
2. Go to **Deployments** and select the last known healthy deployment.
3. Click **Redeploy**.
4. Verify health endpoints return 200.
5. Trigger the production smoke test workflow in GitHub Actions.

### Roll back via Railway CLI

```bash
railway list deployments --service api --environment production
railway redeploy --service api --deployment <deployment-id> --environment production
```

### Revert a code change and redeploy

```bash
# Identify the bad commit
git log --oneline -10

# Revert and push to main
git revert <bad-commit-hash>
git push origin main

# CI will run tests and deploy automatically
```

### Disable a feature flag as a temporary mitigation

1. Ensure `RAILWAY_TOKEN` is set on the `api` service.
2. Toggle the flag in Railway project settings.
3. Note that feature flags are cached in-process for 60 seconds; expect a short delay.

## 8. Post-incident review

For every P1 and P2 incident, schedule a review within 48 hours.

**Required output**: A short document covering:

- Timeline of detection, response, and recovery.
- Root cause (preliminary if not fully determined).
- What went well and what could be improved.
- Action items with owners and due dates.
- Whether the incident affects SOC2 controls; update evidence if required.

Store the document in the internal incident tracker or `security/reports/` if it involves a security finding.

## 9. Quick reference commands

```bash
# Link to production environment
railway link --project 30feaeee-9464-41ac-9b17-d07ae4cfcd09 --environment production

# Service status
railway environment
railway status --service api

# Logs
railway logs --service api --tail 200
railway logs --service ocerp --tail 200
railway logs --service admin --tail 200
railway logs --service data-pipeline --tail 200
railway logs --service qdrant --tail 100
railway logs --service minio --tail 100

# Manual database init (idempotent; use with caution)
railway run --service api python scripts/init_db.py
railway run --service admin python manage.py migrate --noinput

# Populate cost data (ad-hoc pipeline run)
railway run --service data-pipeline python -m data_pipeline.loader

# Run tests locally
source .venv/bin/activate
pytest
pytest -m security -v --no-cov

# Run production smoke test manually
cd web/app
E2E_BASE_URL=https://<web-domain> \
E2E_ADMIN_BASE_URL=https://<admin-domain> \
E2E_DJANGO_ADMIN_USERNAME=<superuser-username> \
E2E_DJANGO_ADMIN_PASSWORD=<password> \
pnpm exec playwright test --config=playwright.config.prod-smoke.ts
```

## 10. Related documents

- [`AGENTS.md`](../../AGENTS.md) — architecture and service overview.
- [`docs/deployment.md`](../../deployment.md) — production deployment playbooks and secret management.
- [`docs/soc2-controls.md`](../../soc2-controls.md) — SOC2 control mapping and evidence locations.
- [`security/README.md`](../../security/README.md) — security test framework and agentic pen test.
- [`.railway/railway.ts`](../../.railway/railway.ts) — Infrastructure as Code definition.
- [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — CI/CD pipeline.
- [`.github/workflows/smoke-production.yml`](../../.github/workflows/smoke-production.yml) — production smoke test.
