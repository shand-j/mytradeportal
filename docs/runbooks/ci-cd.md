# CI/CD Runbook

> How My Trade Portal V2 is built, tested, and deployed to production. This runbook is designed for engineers who need to operate or debug the pipeline without deep prior knowledge of the project.

- [Overview](#overview)
- [What the pipeline does](#what-the-pipeline-does)
- [GitHub Actions workflows](#github-actions-workflows)
- [Railway infrastructure as code](#railway-infrastructure-as-code)
- [Required secrets and environments](#required-secrets-and-environments)
- [Local CI simulation](#local-ci-simulation)
- [Production deployment flow](#production-deployment-flow)
- [Post-deploy verification](#post-deploy-verification)
- [Security and SOC2 considerations](#security-and-soc2-considerations)
- [Known issues and limitations](#known-issues-and-limitations)
- [Troubleshooting](#troubleshooting)
- [Escalation](#escalation)

---

## Overview

Production is hosted on **Railway** in the **`europe-west4-drams3a` (Amsterdam)** region, deployed automatically from the `main` branch of the GitHub repository `shand-j/mytradeportal`. The stack is declared as **Infrastructure as Code** in [`.railway/railway.ts`](../../.railway/railway.ts) and applied by GitHub Actions.

Current production environment:

| Item | Value |
|------|-------|
| Railway project | `MyTradePortal` (`30feaeee-9464-41ac-9b17-d07ae4cfcd09`) |
| Environment | `production` |
| Services | `api`, `web`, `admin`, `ocerp`, `data-pipeline`, `minio`, `qdrant`, `Postgres`, `Redis` |
| Public domains | `<api-domain>`, `<web-domain>`, `<admin-domain>` |

The platform is multi-tenant with PostgreSQL Row-Level Security (RLS), uses OpenAI for AI quote generation, Paddle for payments, Qdrant for vector search, and MinIO for file uploads.

---

## What the pipeline does

The CI/CD pipeline enforces three gates before production deploy:

1. **Python quality and tests**: lint, format, type check, and unit tests for the FastAPI backend, OCERP microservice, Django admin, data pipeline, shared packages, and evals.
2. **TypeScript quality and tests**: lint, unit tests, and production build for the React back-office UI in `web/app`.
3. **Infrastructure apply**: apply the Railway IaC to the `production` environment, then run a production smoke test.

No code reaches production unless both test jobs pass and the event is a push to `main`.

---

## GitHub Actions workflows

### `CI` — `.github/workflows/ci.yml`

Triggered on every push to `main` and every pull request targeting `main`.

#### `python` job

Runs on `ubuntu-latest` with PostgreSQL 16 and Qdrant v1.11.5 service containers.

| Step | Command |
|------|---------|
| Install dependencies | `pip install -e ".[dev]"` |
| Lint | `ruff check .` |
| Format check | `ruff format --check .` |
| Type check | `mypy services/api packages/shared/py` and `mypy --config-file mypy-admin.ini services/admin` |
| Test | `pytest` |

Environment variables used in CI:

```text
DATABASE_URL=postgresql+asyncpg://mtp:mtp@localhost:5432/mtp
QDRANT_URL=http://localhost:6333
```

#### `typescript` job

Runs on `ubuntu-latest` inside `web/app`.

| Step | Command |
|------|---------|
| Install dependencies | `pnpm install --frozen-lockfile` |
| Lint | `pnpm lint` |
| Test | `pnpm test` |
| Build | `pnpm build` |

Uses Node 22 and pnpm 10, caching `web/app/pnpm-lock.yaml`.

#### `deploy` job

Runs only on `main` pushes after the `python` and `typescript` jobs succeed. It is gated by the `MyTradePortal/Production` GitHub environment, which requires manual approval if configured.

| Step | What it does |
|------|--------------|
| Install Railway CLI | `npm install -g @railway/cli` |
| Install IaC runner | `npm ci` inside `.railway` |
| Set Django superuser password | `railway variable set DJANGO_SUPERUSER_PASSWORD=... --service admin --environment production` |
| Apply Railway configuration | `railway config apply --yes` using `.railway/railway.ts` |

Environment variables used in the deploy job:

```text
RAILWAY_ENVIRONMENT=production
RAILWAY_IAC_TS_BIN=.railway/node_modules/.bin/railway-iac-ts
```

### `Production Smoke Test` — `.github/workflows/smoke-production.yml`

Triggered automatically after a successful `CI` deploy, or manually via `workflow_dispatch`.

| Step | What it does |
|------|--------------|
| Install Python dependencies | `pip install -e ".[dev]"` |
| Install Playwright | `pnpm install --frozen-lockfile` and `pnpm exec playwright install chromium` |
| Run smoke test | `pnpm exec playwright test --config=playwright.config.prod-smoke.ts` |
| Upload artifacts on failure | Screenshots and traces from `web/app/playwright/.tmp` and `web/app/test-results` |
| Teardown test data | `python services/admin/scripts/cleanup_e2e_prod.py` using `DATABASE_URL` |

Environment variables used:

```text
E2E_BASE_URL
E2E_ADMIN_BASE_URL
E2E_DJANGO_ADMIN_USERNAME (defaults to superadmin)
E2E_DJANGO_ADMIN_PASSWORD
E2E_ARTIFACT_DIR=playwright/.tmp
DATABASE_URL
```

The smoke test creates a tenant with the slug prefix `prod-smoke-` and removes it at the end. It does **not** delete the production `superadmin` account.

---

## Railway infrastructure as code

The entire production stack is defined in [`.railway/railway.ts`](../../.railway/railway.ts). See [`docs/deployment.md`](../deployment.md) for a full ground-up deploy playbook.

### Resources declared

| Resource | Type | Purpose |
|----------|------|---------|
| `db` | `postgres` | Operational PostgreSQL 16 database |
| `redis` | `redis` | Cache and future task broker |
| `qdrant` | `service` with Docker image | Vector database on `qdrant/qdrant:v1.11.5` |
| `minio` | `service` with Docker image | S3-compatible object storage on `quay.io/minio/minio:RELEASE.2025-07-23T15-54-02Z` |
| `api` | GitHub repo build | FastAPI backend, built from `services/api/Dockerfile` |
| `ocerp` | GitHub repo build | BoQ / pricing engine, built from `services/ocerp/Dockerfile` |
| `web` | GitHub repo build | React back-office SPA, built from `web/app/Dockerfile` |
| `admin` | GitHub repo build | Django admin panel, built from `services/admin/Dockerfile` |
| `data-pipeline` | GitHub repo build | Price scraper / loader, built from `services/data-pipeline/Dockerfile` |

### IaC limitations

Railway IaC cannot create public service domains or register custom domains. After the first apply, generate public domains in the Railway dashboard for:

- `api`
- `web`
- `admin`
- `minio` (target port **9000**)

Once domains exist, cross-service references like `VITE_API_BASE_URL`, `ALLOWED_ORIGINS`, `MINIO_ENDPOINT`, and `CSRF_TRUSTED_ORIGINS` resolve automatically.

### Local IaC commands

```bash
cd .railway
npm install
railway login
railway link

# Preview the diff (safe, read-only)
railway config plan

# Apply after confirmation
railway config apply
```

---

## Required secrets and environments

### GitHub environment: `MyTradePortal/Production`

These secrets are required by the `deploy` and `smoke-production` workflows:

| Secret | Required by | Purpose |
|--------|-------------|---------|
| `RAILWAY_TOKEN` | `deploy` | Railway project token for `railway config apply` |
| `DJANGO_SUPERUSER_USERNAME` | `deploy` | Production Django superuser username |
| `DJANGO_SUPERUSER_EMAIL` | `deploy` | Production Django superuser email |
| `DJANGO_SUPERUSER_PASSWORD` | `deploy`, `smoke-production` | Production Django superuser password |
| `E2E_BASE_URL` | `smoke-production` | Public URL of the `web` service |
| `E2E_ADMIN_BASE_URL` | `smoke-production` | Public URL of the `admin` service |
| `DATABASE_URL` | `smoke-production` | Used to tear down smoke-test data |

Optional:

| Secret | Purpose |
|--------|---------|
| `PADDLE_API_KEY` | Enable Paddle payments |
| `PADDLE_WEBHOOK_SECRET` | Paddle webhook HMAC verification |

### Railway variables preserved by `preserve()`

These are set once in the Railway dashboard and are never overwritten by IaC applies:

| Service | Variable | Notes |
|---------|----------|-------|
| `api` | `OPENAI_API_KEY` | Required |
| `api` | `AUTH_SECRET_KEY` | Strong random string; required in production |
| `api` | `SETUP_TOKEN` | Strong random string; gates `POST /tenants` |
| `api` | `APP_ROLE_PASSWORD` | Strong random string; RLS-enforced DB role |
| `api` | `MINIO_ACCESS_KEY` | Required |
| `api` | `MINIO_SECRET_KEY` | Required |
| `api` | `RAILWAY_TOKEN` | Project token for feature flags |
| `api` | `NEW_RELIC_LICENSE_KEY` | Optional; New Relic APM |
| `minio` | `MINIO_ROOT_USER` | Must match `MINIO_ACCESS_KEY` |
| `minio` | `MINIO_ROOT_PASSWORD` | Must match `MINIO_SECRET_KEY` |
| `admin` | `SECRET_KEY` | Django secret |
| `admin` | `DJANGO_SUPERUSER_USERNAME` | Required |
| `admin` | `DJANGO_SUPERUSER_EMAIL` | Required |
| `admin` | `DJANGO_SUPERUSER_PASSWORD` | Set from GitHub secret on deploy |
| `admin` | `NEW_RELIC_LICENSE_KEY` | Optional; New Relic APM |
| `data-pipeline` | `OPENAI_API_KEY` | Required for embeddings |
| `data-pipeline` | `APIFY_API_TOKEN` | Required for Screwfix scraping |
| `data-pipeline` | `APP_ROLE_PASSWORD` | Same value as `api` service |

---

## Local CI simulation

Before pushing, run the same checks locally that CI runs.

### Python checks

```bash
source .venv/bin/activate
pip install -e ".[dev]"

ruff check .
ruff format --check .
mypy services/api packages/shared/py
mypy --config-file mypy-admin.ini services/admin
pytest
```

### TypeScript checks

```bash
cd web/app
pnpm install --frozen-lockfile
pnpm lint
pnpm test
pnpm build
```

### Security checks (not run in default CI)

```bash
# Python dependency audit
pip-audit --desc --audit-level=high

# Node dependency audit
pnpm audit --audit-level=high

# Security tests against production (requires live credentials)
export SECURITY_API_BASE_URL=https://<api-domain>
export SECURITY_ADMIN_BASE_URL=https://<admin-domain>
export SECURITY_TENANT_SLUG=demo
export SECURITY_ADMIN_EMAIL=owner@demo-electrical.example.com
export SECURITY_ADMIN_PASSWORD=...
pytest -m security -v --no-cov
```

---

## Production deployment flow

### Standard deploy

1. Open a pull request to `main`. The `CI` workflow runs the full test suite.
2. After review, merge the PR. The `CI` workflow runs again on `main`.
3. If tests pass, the `deploy` job runs automatically (or after GitHub environment approval).
4. The deploy job applies the Railway IaC to `production`.
5. On completion, the `Production Smoke Test` workflow runs automatically.

### Manual deploy (emergency or IaC-only change)

If you need to apply infrastructure changes without waiting for a merge:

```bash
cd .railway
railway login
railway link
railway config plan
railway config apply
```

Then trigger the production smoke test manually in the GitHub Actions UI.

### First-time production setup

See the full playbook in [`docs/deployment.md`](../deployment.md#playbook-1-clean-ground-up-production-deploy). At a high level:

1. Install the Railway GitHub App on the repo and set `GITHUB_REPO` in `railway.ts` or `MTP_GITHUB_REPO`.
2. Create the `MyTradePortal/Production` GitHub environment with the required secrets.
3. Set all `preserve()` variables in the Railway dashboard before the first deploy.
4. Apply the IaC with `railway config apply`.
5. Generate public domains in the Railway dashboard for `api`, `web`, `admin`, and `minio`.
6. Create the MinIO bucket `mtp-uploads`.
7. Run the database initialisation via the `api` pre-deploy command (the `admin` pre-deploy command runs Django migrations and creates the superuser separately).
8. Create the first tenant through the Django admin UI or the gated `POST /tenants` endpoint.
9. Populate cost data by running the data-pipeline:

   ```bash
   railway run --service data-pipeline python -m data_pipeline.loader
   ```

   > **Note:** AI quotes will only produce labour-line items until cost data is
   > available. If Apify reports a monthly usage limit, wait for the limit to reset
   > or upgrade the Apify plan.

---

## Post-deploy verification

### Automatic verification

After every deploy, the `Production Smoke Test` workflow:

- Creates a tenant via the Django admin UI.
- Exercises customer, quote, invoice, and job flows through the React UI.
- Tears down the test tenant using `services/admin/scripts/cleanup_e2e_prod.py`.

### Manual health checks

```bash
curl https://<api-domain>/health
curl https://<web-domain>/
curl https://<admin-domain>/health
```

OCERP does not have a public domain by default; check via the Railway private network or dashboard logs.

### Railway dashboard checks

1. Confirm all services show **Healthy**.
2. Review the **Deploy logs** for `api` and `admin` to confirm `scripts/init_db.py` ran without errors.
3. Confirm no unexpected public domains were requested.

---

## Security and SOC2 considerations

The CI/CD pipeline is part of the SOC2 change-management control (CC8.1). Evidence locations are documented in [`docs/soc2-controls.md`](../soc2-controls.md) and [`security/README.md`](../../security/README.md).

| Control | How it is enforced |
|---------|-------------------|
| **Code review** | Pull requests are required before merging to `main`. |
| **Quality gates** | `ruff`, `mypy`, and `pytest` run on every PR and `main` push. |
| **Secrets management** | Production secrets are stored in Railway variables or GitHub environment secrets; nothing is committed to the repo. |
| **Privileged access** | `DJANGO_SUPERUSER_PASSWORD` is rotated from the GitHub secret on every deploy. |
| **Infrastructure review** | IaC changes are visible in `.railway/railway.ts` and applied through `railway config apply`. |
| **Dependency scanning** | `pip-audit` and `pnpm audit` are available; run them locally or via the manual `Security Audit` workflow. |
| **Production defaults** | `Settings.validate_production()` blocks the API from starting with insecure defaults. |

### Security workflows

Two additional workflows exist but are manual dispatch only:

- **Security Audit** (`.github/workflows/security-audit.yml`) — runs OWASP, multi-tenancy, SOC2 tests, and dependency audits against production.
- **Agentic Penetration Test** (`.github/workflows/agentic-pen-test.yml`) — runs the multi-agent white-hat assessment.

---

## Known issues and limitations

1. **Admin service region discrepancy**: Resolved. All services are deployed in the IaC target region `europe-west4-drams3a` (Amsterdam). If Railway ever shows a region drift after an apply, verify the deployment region in the dashboard before assuming it is intentional.

2. **Empty TypeScript workspaces in CI**: The root `package.json` only contains Supabase scripts. The CI `typescript` job correctly targets `web/app` with pnpm, but the old workflow comments about `services/pwa` and `services/chatbot-widget` are stale — those directories are placeholders.

3. **MinIO domains must be generated manually**: Railway IaC cannot create public domains, so the first apply leaves `MINIO_ENDPOINT` empty until the MinIO public domain is created in the dashboard.

4. **Feature flags require `RAILWAY_TOKEN`**: Without it, `GET /feature-flags` serves the default off values for all flags.

---

## Troubleshooting

### CI fails on `ruff check .` or `ruff format --check .`

Fix locally, then commit:

```bash
ruff check . --fix
ruff format .
```

### CI fails on `mypy`

Run the same command locally and fix type errors. The admin service uses a separate config:

```bash
mypy --config-file mypy-admin.ini services/admin
```

### CI fails on `pytest`

Check the failing test output. If tests depend on the database or Qdrant, ensure you have the services running locally:

```bash
docker compose up -d postgres qdrant
```

### Deploy job fails during `railway config apply`

1. Verify `RAILWAY_TOKEN` is set and has access to the `MyTradePortal` project.
2. Run `railway config plan` locally to preview the diff and identify syntax errors.
3. Check that all `preserve()` variables are set in the Railway dashboard.
4. If a service references a public domain that does not exist yet, generate it in the dashboard first.

### API fails to start with "dev defaults refused"

`Settings.validate_production()` blocks the app when insecure defaults are present. Check that `AUTH_SECRET_KEY`, `SETUP_TOKEN`, `APP_ROLE_PASSWORD`, `MINIO_ACCESS_KEY`, and `MINIO_SECRET_KEY` are set to strong non-default values on the `api` service.

### Admin deploy fails with "relation does not exist"

The `admin` pre-deploy command must run after the `api` pre-deploy command has created the FastAPI schema. In practice they run in parallel, but `admin` retries automatically. If it persists, re-run:

```bash
railway run --service admin python scripts/init_db.py
```

### MinIO uploads fail

- Ensure `MINIO_ENDPOINT` is the public Railway domain, not the private one.
- Ensure `MINIO_USE_SSL=true`.
- Ensure the bucket `mtp-uploads` exists.
- Ensure `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` match `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`.

### Smoke test fails and leaves a tenant behind

The teardown step removes tenants with slug prefix `prod-smoke-` or `first-customer-`. If a run is cancelled, manually delete the tenant from the Django admin or via the database.

### Feature flags not applying

- Check that `RAILWAY_TOKEN` is set on the `api` service.
- Check Railway project logs for GraphQL errors.
- Remember flags are cached in-process for 60 seconds.

---

## Escalation

If the pipeline or deployment cannot be recovered through the steps above:

1. **Stop the bleeding**: pin the previous healthy deployment in the Railway dashboard for the affected service.
2. **Communicate**: open an incident channel and record the affected commit SHA and deployment ID.
3. **Investigate**: capture Railway deploy logs, GitHub Actions logs, and the output of `railway config plan`.
4. **Recover**: revert the commit on `main` and let CI redeploy, or apply a known-good IaC state from a previous branch.
5. **Post-incident**: update this runbook if a new failure mode was discovered.

---

*Related documents:*

- [`docs/deployment.md`](../deployment.md) — full ground-up and existing-environment deploy playbooks
- [`docs/soc2-controls.md`](../soc2-controls.md) — SOC2 control mapping and evidence
- [`security/README.md`](../../security/README.md) — security test framework and agentic pen tests
- [`.railway/railway.ts`](../../.railway/railway.ts) — authoritative Railway infrastructure definition
- [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — CI/CD workflow definition
- [`.github/workflows/smoke-production.yml`](../../.github/workflows/smoke-production.yml) — production smoke test definition
