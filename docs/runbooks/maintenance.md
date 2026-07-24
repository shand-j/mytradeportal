# Maintenance Runbook

This runbook covers the day-to-day care, feeding, and incident response for My Trade Portal V2 in production. It is intended for the on-call engineer who understands the stack but may not have the whole codebase memorised. All commands assume a local clone of the repo at `/Users/home/Projects/mytradeportal` and a Railway project linked to **MyTradePortal** (`30feaeee-9464-41ac-9b17-d07ae4cfcd09`) in the **production** environment.

## Quick Reference

| Service | Current Domain | Health Check |
|---|---|---|
| API | `https://api-production-83b8.up.railway.app` | `GET /health` |
| Web | `https://web-production-0919a.up.railway.app` | `GET /` |
| Admin | `https://admin-production-5c08.up.railway.app` | `GET /health` |
| OCERP | Internal (`${{ocerp.RAILWAY_PRIVATE_DOMAIN}}`) | `GET /health` |
| Data Pipeline | Internal | N/A (scheduled task) |
| PostgreSQL | Native Railway plugin | N/A |
| Redis | Native Railway plugin | N/A |
| Qdrant | Internal Docker service | Qdrant REST API |
| MinIO | Public domain required | Console + S3 API |

**Known infrastructure note:** all services are deployed in the IaC target region `europe-west4-drams3a` (Amsterdam). If Railway ever shows a region drift after an apply, verify the deployment region in the dashboard before assuming it is intentional.

---

## How to use this runbook

1. For **symptom-based** recovery, start in [Common incidents](#common-incidents).
2. For **routine care**, use the [Daily checks](#daily-checks) and [Weekly checks](#weekly-checks) sections.
3. For **infrastructure changes**, review [Railway operations](#railway-operations) and the deployment playbooks in `docs/deployment.md`.

---

## Daily checks

Run these every morning or before a planned release. Most checks can be done in the Railway dashboard or with the Railway CLI.

### 1. Verify service health

```bash
railway login
railway environment
railway status
```

In the dashboard, confirm:

- `api`, `web`, `admin`, `ocerp`, `data-pipeline` are **Healthy** (green).
- PostgreSQL, Redis, Qdrant and MinIO are shown as **Available**.

Then hit the public health endpoints:

```bash
curl -s https://api-production-83b8.up.railway.app/health
curl -s https://web-production-0919a.up.railway.app
curl -s https://admin-production-5c08.up.railway.app/health
```

Expected: HTTP 200 for each. If OCERP is exposed publicly for diagnostics, check:

```bash
# Only if you have generated a public domain for ocerp in the dashboard
curl -s https://<ocerp-domain>/health
```

### 2. Review recent deploys and logs

In the Railway dashboard, inspect the **Deploy logs** for the last deploy of `api` and `admin`. Confirm that the pre-deploy command ran successfully:

```text
python scripts/init_db.py
sh -c 'python scripts/init_db.py && python scripts/ensure_superuser.py'
```

Stream the API logs for a few minutes to spot repeated errors or exceptions:

```bash
railway logs --service api --environment production --tail
```

For a broader search, pull the last 500 lines:

```bash
railway logs --service api --environment production --limit 500 > /tmp/api.log
```

Look for:

- `ERROR` or `CRITICAL` from `structlog`.
- Repeated `tenant_id not found` or RLS policy failures.
- `Settings.validate_production refused` on startup (means a dev default leaked into production).
- OpenAI rate-limit or timeout errors.

### 3. Check the data pipeline status

The pipeline is scheduled monthly by default (`SCRAPE_FREQUENCY=monthly`). Confirm it is not stuck in a failed deploy loop:

```bash
railway logs --service data-pipeline --environment production --tail
```

Look for:

- `Apify scrape completed` or `seed loaded` messages.
- No repeated `APIFY_API_TOKEN` or `OPENAI_API_KEY` authentication failures.

### 4. Spot-check quote generation

Log in to the back office at `https://web-production-0919a.up.railway.app` with an existing tenant and create a quick test quote. This validates the full chain: web → API → OCERP → Qdrant → OpenAI. Any failure here is worth investigating before users report it.

---

## Weekly checks

### 1. Security and audit review

1. Open the Django admin panel at `https://admin-production-5c08.up.railway.app/admin/`.
2. Review the **Operations → Audit logs** entries for the last 7 days.
3. Look for:
   - Failed logins from unexpected IPs or tenants.
   - Unusual `POST /tenants` attempts (requires `X-Setup-Token`).
   - Bulk invoice/payment mutations outside normal hours.

Run the security test suite against production if you have the credentials:

```bash
source .venv/bin/activate
export SECURITY_API_BASE_URL=https://api-production-83b8.up.railway.app
export SECURITY_ADMIN_BASE_URL=https://admin-production-5c08.up.railway.app
export SECURITY_TENANT_SLUG=<tenant-slug>
export SECURITY_ADMIN_EMAIL=<admin-email>
export SECURITY_ADMIN_PASSWORD=<admin-password>
pytest -m security -v --no-cov
```

For a deeper review, run the agentic penetration test (read-only by default):

```bash
export OPENAI_API_KEY=...
export SECURITY_TARGET_URL=https://web-production-0919a.up.railway.app
export SECURITY_API_BASE_URL=https://api-production-83b8.up.railway.app
export SECURITY_ADMIN_BASE_URL=https://admin-production-5c08.up.railway.app
python -m security.agents.orchestrator
```

Reports are written to `security/reports/`.

### 2. Dependency audit

```bash
source .venv/bin/activate
pip-audit --desc --audit-level=high

cd web/app
pnpm audit --audit-level=high
```

If either reports a high-severity vulnerability, create a ticket and patch within the SLA defined by the security team. Do not commit a suppress rule without documenting the risk.

### 3. Cost and usage monitoring

- **OpenAI:** log in to the OpenAI dashboard and review LLM + embedding usage for the week. Set billing alerts if not already configured.
- **Railway:** review resource usage (CPU, memory, disk) for Postgres, Qdrant, and MinIO. Qdrant and MinIO volumes start at 5 GB each; monitor growth.
- **Paddle:** if payments are enabled, reconcile Paddle transactions against the `payments` table.

### 4. Backup verification

- Railway Postgres backups are automatic; confirm retention is configured in the dashboard.
- For Qdrant and MinIO, you must arrange your own backups. At minimum, create a Qdrant snapshot once a week and confirm the MinIO bucket contents are recoverable.

To create a Qdrant snapshot manually:

```bash
railway run --service qdrant \
  curl -X POST http://localhost:6333/snapshots
```

Download the snapshot from the Qdrant console or S3 target afterwards.

---

## Railway operations

### Connect to the project

All commands assume the Railway CLI is installed and linked:

```bash
railway login
railway link --project 30feaeee-9464-41ac-9b17-d07ae4cfcd09 --environment production
```

### Run a one-off command in a service

```bash
railway run --service api python scripts/init_db.py
railway run --service admin python scripts/ensure_superuser.py
railway run --service data-pipeline python -m data_pipeline.load_curated_seed
railway run --service data-pipeline python -m data_pipeline.knowledge_loader
```

These are idempotent; they are safe to run when you suspect the schema, seed data, or superuser has drifted. Always check the output before moving on.

### Restart a service

From the dashboard: click the service → **Deploy** → **Redeploy**.

From the CLI (does not fetch new code; restarts the same image):

```bash
railway service --service api redeploy
```

To restart with the latest commit on `main`, trigger the CI workflow or run:

```bash
railway config apply --yes
```

### Scale or resize a service

Currently the IaC pins each service to 1 replica in `europe-west4-drams3a` (Amsterdam). If you need to change this temporarily (for example during a launch event), edit `.railway/railway.ts` and apply:

```bash
cd .railway
railway config plan
railway config apply
```

You can also scale the Postgres or Redis native plugins through the Railway dashboard. Record any manual change in the team runbook so the IaC can be reconciled later.

### View and edit variables

List variables for a service:

```bash
railway variables --service api
```

Set a variable (triggers redeploy):

```bash
railway variable set LOG_LEVEL=DEBUG --service api --environment production
```

⚠️ **Never** set secrets in the CLI with a value that can be read from shell history. For sensitive values, use the Railway dashboard or the GitHub Actions workflow that sets `DJANGO_SUPERUSER_PASSWORD` from a repository secret.

### Domain management

Railway IaC cannot create public domains. To add or regenerate a domain:

1. Open the Railway dashboard.
2. Navigate to the service → **Settings** → **Networking** → **Generate Public Domain**.
3. For `minio`, generate the domain on **port 9000** (the S3 API port), not the console port 9001.

After generating domains, the cross-service references (`VITE_API_BASE_URL`, `ALLOWED_ORIGINS`, `MINIO_ENDPOINT`, `CSRF_TRUSTED_ORIGINS`) will resolve automatically on the next deploy.

---

## Database maintenance

### Schema and migrations

My Trade Portal V2 is pre-go-live and uses one-time schema initialisation via `scripts/init_db.py`. This script is idempotent and runs automatically in the `api` and `admin` pre-deploy commands.

If you need to re-run schema init manually:

```bash
railway run --service api python scripts/init_db.py
railway run --service admin python scripts/init_db.py
```

If you later switch to Alembic-driven migrations, the same command would run `alembic upgrade head` instead. Until then, schema changes are applied by editing the models and re-running the init script after deploy.

### Row-Level Security (RLS)

Never disable RLS in production. If you need to inspect data across tenants for an incident, use the application admin path or Django admin instead of running `SET bypass_rls = true` in a raw session.

If you must connect to Postgres for diagnostics, use the `DATABASE_URL` from the Railway dashboard and a SQL client over TLS. Always verify the tenant scoping of any query before running it.

```bash
# Example psql via Railway CLI (you are still bound by RLS if connecting as mtp_app)
railway run --service db psql $DATABASE_URL
```

### Seeding and re-indexing cost data

To refresh the cost database or knowledge base after a product data change:

```bash
railway run --service data-pipeline python -m data_pipeline.load_curated_seed
railway run --service data-pipeline python -m data_pipeline.knowledge_loader
```

These recreate the Qdrant collections and populate the Postgres `cost_items` table. Run them after any Qdrant data loss or when the knowledge base has been updated in the repo.

### Database restore from backup

If a database restore is required:

1. Contact Railway support or use the dashboard backup restore feature for the `db` service.
2. After restore, re-run schema init if needed:
   ```bash
   railway run --service api python scripts/init_db.py
   railway run --service admin python scripts/init_db.py
   ```
3. Re-seed Qdrant and MinIO data if the restore predates those backups.
4. Verify the first tenant can still log in and that RLS policies are intact.

---

## Feature flags

Feature flags are read from Railway Signals via `GET /feature-flags` on the `api` service. They default to off when `RAILWAY_TOKEN` is missing or the Signals call fails.

### Ensure the flag reader is working

```bash
curl -s https://api-production-83b8.up.railway.app/feature-flags
```

Expected: a JSON object with flags and their current values.

### Toggle a flag

1. Create or reuse a Railway project token (**Project Settings → Tokens**).
2. Confirm `RAILWAY_TOKEN` is set on the `api` service.
3. In the Railway dashboard, go to **Project Settings → Feature Flags** and toggle the flag.
4. Wait up to 60 seconds for the in-process cache to expire, or redeploy the API.

Known flags:

| Flag | Default | Feature |
|---|---|---|
| `voice_ai_insights` | `false` | Voice AI insights page |
| `demand_forecasting` | `false` | Demand forecasting dashboard |
| `external_integrations` | `false` | External accounting/messaging integrations |

If a flag is not applying, check the API logs for Railway GraphQL errors and confirm the token is scoped to the `MyTradePortal` project.

---

## Common incidents

### API will not start / health check fails

Symptoms: `api` service shows `UNHEALTHY` or deploy fails repeatedly.

1. Check the deploy logs for `Settings.validate_production refused`.
   - Confirm `AUTH_SECRET_KEY`, `SETUP_TOKEN`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` are set to non-default values on the `api` service.
2. Check `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL` are reachable from the service.
3. Check for a migration/schema error. Re-run:
   ```bash
   railway run --service api python scripts/init_db.py
   ```
4. If the container is running but the health check fails, ensure `PORT=8000` is set in the Railway variables (the Dockerfile uses `${PORT:-8000}`).

### Admin will not start / login page returns 500

Symptoms: `admin` service unhealthy or admin login page shows an error.

1. Check deploy logs for `relation does not exist` errors. The admin pre-deploy command needs the FastAPI schema to exist first. If the race failed, run:
   ```bash
   railway run --service api python scripts/init_db.py
   railway run --service admin python scripts/init_db.py
   ```
2. Verify `SECRET_KEY`, `DJANGO_SUPERUSER_PASSWORD` are set.
3. Verify `CSRF_TRUSTED_ORIGINS` matches the actual admin public domain (`https://admin-production-5c08.up.railway.app`).
4. Confirm `PORT=8001` is set in the admin variables (Django gunicorn binds to this port).

### Quote generation fails or returns bad results

1. Verify `OPENAI_API_KEY` is set on `api` and `ocerp` and has credits.
2. Check Qdrant health and confirm the collections exist:
   ```bash
   railway run --service ocerp curl http://$QDRANT_URL/collections
   ```
3. Check that the `cost_items` and `quoting_knowledge` collections are populated:
   ```bash
   railway run --service ocerp curl http://$QDRANT_URL/collections/cost_items
   railway run --service ocerp curl http://$QDRANT_URL/collections/quoting_knowledge
   ```
4. If the collections are empty, re-run:
   ```bash
   railway run --service data-pipeline python -m data_pipeline.load_curated_seed
   railway run --service data-pipeline python -m data_pipeline.knowledge_loader
   ```
5. Review the OCERP logs for deterministic rule failures or resolver errors.

### File uploads fail

1. In the Railway dashboard, confirm the `minio` service has a public domain on port **9000**.
2. Verify the `mtp-uploads` bucket exists in the MinIO console.
3. Confirm `MINIO_ENDPOINT` on the `api` service is the public domain (not the private domain) and `MINIO_USE_SSL=true`.
4. Confirm `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` on `api` match `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` on `minio`.
5. Check CORS settings if uploads fail from the browser. The browser must be allowed to POST to the presigned URL.

### Paddle webhooks not received or fail verification

1. Confirm the webhook endpoint is `https://api-production-83b8.up.railway.app/webhooks/paddle` and registered in Paddle.
2. Verify `PADDLE_WEBHOOK_SECRET` is set on `api` and matches the value in Paddle.
3. Verify `PADDLE_API_KEY` is set and the sandbox flag matches the environment.
4. Check the API logs for `HMAC verification failed` or `Paddle API error`.

### Smoke test leaves a tenant behind

The production smoke test creates tenants with slug prefix `prod-smoke-` or `first-customer-`. If a workflow run is cancelled, the teardown step may not run.

1. Log in to the Django admin at `https://admin-production-5c08.up.railway.app/admin/`.
2. Navigate to **Operations → Tenants**, filter by slug prefix `prod-smoke-`, and delete the leftover tenants.
3. Alternatively, run the cleanup script manually:
   ```bash
   railway run --service admin python services/admin/scripts/cleanup_e2e_prod.py
   ```

### Slow API responses or high latency

1. Check the Railway metrics for the `api` service (CPU, memory, response times).
2. Review the API logs for slow endpoints. The slowest paths are usually AI generation (`/quotes/generate`, `/quotes/generate-boq`) and OCERP calls.
3. Confirm `LLM_TIMEOUT_SECONDS` is high enough for complex BoQ generation (default 300s).
4. If Redis is unavailable, rate limiting and any cached feature flags will behave badly; check Redis status.

### Region drift

If Railway shows a service in a different region than `europe-west4-drams3a` (Amsterdam), check:

1. The `.railway/railway.ts` file still sets `TARGET_REGION = "europe-west4-drams3a"` and `regions: { [TARGET_REGION]: 1 }` for that service.
2. A manual dashboard change or a redeploy from an older branch is not overriding the IaC.
3. If you need to force reconciliation, run:
   ```bash
   cd .railway
   railway config plan
   railway config apply
   ```

Currently the `admin` service shows as `sfo` in the dashboard despite the IaC target. Treat this as a known discrepancy and do not re-apply unless it is causing a user-facing issue, because the apply may move the service and cause a brief outage.

---

## Release procedure

For the full ground-up and existing-environment playbooks, see `docs/deployment.md`. The routine release path is:

1. Open a pull request to `main`.
2. Confirm CI passes (`python`, `typescript`, and `deploy` jobs).
3. Merge.
4. CI deploys to production automatically after tests pass.
5. The smoke test workflow runs automatically after the deploy.
6. Verify the deploy:
   - All services healthy in Railway dashboard.
   - Health endpoints return 200.
   - Log in to the back office and create a test quote.

If a deploy breaks production, the fastest recovery is to roll back in the Railway dashboard (redeploy the previous healthy image) while you revert the code on `main`.

---

## Security and compliance maintenance

- Rotate `AUTH_SECRET_KEY`, `SETUP_TOKEN`, and `PADDLE_WEBHOOK_SECRET` after any suspected leak or annually, whichever comes first. Rotation requires a redeploy and invalidates active sessions.
- Keep `OPENAI_API_KEY`, `PADDLE_API_KEY`, `APIFY_API_TOKEN`, and database credentials in Railway variables or GitHub secrets only. Do not commit them.
- Review the SOC2 control mapping in `docs/soc2-controls.md` before an audit. Evidence is generated by:
  - `security/tests/test_multitenancy.py` (logical access)
  - `security/tests/test_soc2.py` (encryption)
  - `services/api/tests/test_audit.py` (audit logging)
  - CI/CD and IaC review (change management)
- Run dependency audits weekly (`pip-audit`, `pnpm audit`) and triage high-severity findings.

---

## Useful commands summary

```bash
# Link to the project
railway link --project 30feaeee-9464-41ac-9b17-d07ae4cfcd09 --environment production

# View service logs
railway logs --service <api|web|admin|ocerp|data-pipeline> --environment production --tail

# Re-run schema init
railway run --service api python scripts/init_db.py
railway run --service admin python scripts/init_db.py

# Re-seed cost and knowledge data
railway run --service data-pipeline python -m data_pipeline.load_curated_seed
railway run --service data-pipeline python -m data_pipeline.knowledge_loader

# Run security tests
pytest -m security -v --no-cov

# Run dependency audits
pip-audit --desc --audit-level=high
pnpm audit --audit-level=high

# Apply IaC changes
cd .railway
railway config plan
railway config apply
```

---

## Escalation

If an incident is not covered by this runbook or you cannot resolve it within 30 minutes:

1. Roll back the affected service to the last healthy deployment in Railway.
2. Notify the engineering lead and security contact.
3. Open a post-mortem issue documenting the symptom, timeline, and fix.
4. Update this runbook if the fix is repeatable.
