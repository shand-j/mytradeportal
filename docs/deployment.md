# Deployment

This document covers local development deployment, production deployment on
Railway, and the operational playbooks for both a clean ground-up install and a
deploy onto an existing production environment.

- [Local development](#local-development)
- [Environment variables](#environment-variables)
- [Production overview](#production-overview)
- [Railway infrastructure](#railway-infrastructure)
- [Playbook 1: Clean ground-up production deploy](#playbook-1-clean-ground-up-production-deploy)
- [Playbook 2: Deploy onto existing production](#playbook-2-deploy-onto-existing-production)
- [Post-deploy verification](#post-deploy-verification)
- [Security and operations](#security-and-operations)
- [Troubleshooting](#troubleshooting)

---

## Local development

The included `docker-compose.yml` is the primary local deployment target.

```bash
docker compose up -d
```

All images and required variables have defaults; the only required secret is
`OPENAI_API_KEY` in a `.env` file in the project root. See
[`docs/getting-started.md`](getting-started.md) for the full local setup.

In development the API creates tables automatically on first boot, and the
admin service runs Django migrations. This is not used in production.

---

## Environment variables

The API and admin containers read variables from the shell or a `.env` file in
the project root. Values marked **Required in production** must be set before
the service will start in `ENVIRONMENT=production`.

### Core

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `production` |
| `DATABASE_URL` | `postgresql+asyncpg://mtp:mtp@postgres:5432/mtp` | Postgres connection (asyncpg for API, psycopg2 for admin) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant connection |
| `MINIO_ENDPOINT` | `minio:9000` | S3-compatible storage endpoint |
| `MINIO_USE_SSL` | `false` | Set `true` when MinIO is reached over HTTPS |
| `MINIO_ACCESS_KEY` | `minioadmin` | **Required in production** |
| `MINIO_SECRET_KEY` | `minioadmin` | **Required in production** |
| `MINIO_BUCKET` | `mtp-uploads` | Upload bucket name |

### AI / RAG

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | *(required everywhere)* | OpenAI API key for LLM + embeddings |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `LLM_MODEL` | `gpt-4o-mini` | Chat model |
| `EMBEDDING_DIMENSIONS` | `1536` | Vector size (Qdrant collections) |
| `QDRANT_COLLECTION_NAME` | `cost_items` | Vector collection for products |
| `QDRANT_KNOWLEDGE_COLLECTION_NAME` | `quoting_knowledge` | Vector collection for regulatory knowledge |
| `RAG_TOP_K` | `10` | Number of items retrieved |

### Auth and bootstrap

| Variable | Default | Purpose |
|---|---|---|
| `AUTH_SECRET_KEY` | `dev-auth-secret-key-change-in-production` | **Required in production** — JWT signing |
| `SETUP_TOKEN` | *(empty)* | **Required in production** — gates `POST /tenants` for first tenant creation |
| `AUTH_COOKIE_SECURE` | `true` | Set `false` only for local HTTP prod-like tests |

### Admin superuser (production)

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SUPERUSER_USERNAME` | `superadmin` | Django admin superuser username |
| `DJANGO_SUPERUSER_EMAIL` | `admin@example.com` | Superuser email |
| `DJANGO_SUPERUSER_PASSWORD` | *(empty)* | **Required in production** — set via GitHub / Railway secret |
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Django secret key |

### Payments

| Variable | Default | Purpose |
|---|---|---|
| `PADDLE_API_KEY` | *(empty)* | Paddle API key |
| `PADDLE_WEBHOOK_SECRET` | *(empty)* | Paddle webhook verification secret |
| `PADDLE_SANDBOX` | `true` | Use Paddle sandbox |
| `PADDLE_DEFAULT_CURRENCY_CODE` | `GBP` | Default currency |

### Data pipeline

| Variable | Default | Purpose |
|---|---|---|
| `APIFY_API_TOKEN` | *(empty)* | Apify token for Screwfix scraping |
| `PIPELINE_DEMO_MODE` | `false` | Run in demo-only mode |
| `SCRAPE_FREQUENCY` | `monthly` | `monthly` / `daily` |
| `SCREWFIX_START_URL` | Screwfix electrical category | Starting URL for Screwfix scrape |
| `TOOLSTATION_ENABLED` | `false` | Enable Toolstation scraper |

### Feature flags

| Variable | Default | Purpose |
|---|---|---|
| `RAILWAY_TOKEN` | *(empty)* | Project token to read Railway Signals |
| `RAILWAY_PROJECT_ID` | *(empty)* | Railway project id (also injected natively) |

---

## Production overview

Production is hosted on **Railway** in the **`europe-west4-drams3a` (Amsterdam)** region, the closest Railway region to the UK market. The stack is declared as Infrastructure as Code
in [`.railway/railway.ts`](../.railway/railway.ts) and deployed automatically by
GitHub Actions on every push to `main` after tests pass.

> **Region drift note:** the native Railway Postgres and Redis plugins are
> currently deployed in `sfo` while the rest of the stack is in Amsterdam. For
> the UK market this adds cross-continent latency. Because the platform is
> pre-go-live, the simplest fix is to recreate the `db` and `redis` services in
> `europe-west4-drams3a` from the Railway dashboard (or by removing and
> re-adding them in IaC) before the first real tenants are onboarded. Document
> any decision to defer this in the go-live checklist.

### Production-first principles

- **No demo or test data is seeded.** The `app.seed_admin_user` script refuses
to run in production. The first tenant and admin are created through the Django
admin UI or the gated `POST /tenants` endpoint.
- **Schema init, not migrations.** Because the platform is pre-go-live with no
consuming users, `scripts/init_db.py` creates the schema from the latest Alembic
revision on first deploy. This is the one-time database initialisation step; it
is safe to run on every deploy because it is idempotent.
- **Django admin deploys with a superuser.** The admin service pre-deploy command
creates a `superadmin` account from `DJANGO_SUPERUSER_PASSWORD` on first boot.
- **Partial features are behind feature flags.** The UI calls `GET /feature-flags`
and hides unreleased capabilities (voice AI, demand forecasting, external
integrations) by default.

### Services

| Service | Type | Purpose |
|---|---|---|
| `db` | Railway Postgres | Operational database |
| `redis` | Railway Redis | Cache and future broker |
| `qdrant` | Docker image + volume | Vector database |
| `minio` | Docker image + volume | S3-compatible object storage |
| `api` | GitHub repo build | FastAPI backend |
| `ocerp` | GitHub repo build | BoQ / pricing engine |
| `web` | GitHub repo build | React back-office SPA |
| `admin` | GitHub repo build | Django admin panel |
| `data-pipeline` | GitHub repo build | Price scraper / loader |

---

## Railway infrastructure

The whole Railway project is declared in [`.railway/railway.ts`](../.railway/railway.ts)
using the [Railway IaC DSL](https://docs.railway.com/infrastructure-as-code). The
Railway GitHub App builds each service from this repo when changes are pushed.

### One-time setup

1. Push this repository to GitHub and install the **Railway GitHub App** on it.
2. Set the repo slug in `.railway/railway.ts` (`GITHUB_REPO`) or export
   `MTP_GITHUB_REPO=<owner>/<repo>`.
3. Install the [Railway CLI](https://docs.railway.com/guides/cli), then
   `railway login` and `railway link` this directory to a project/environment.
4. Install the IaC runner dependencies:

   ```bash
   cd .railway && npm install
   ```

### Plan and apply

```bash
railway config plan    # preview the diff (safe, read-only)
railway config apply   # apply after confirmation
```

### IaC limitations

Railway IaC cannot create public service domains or register custom domains.
After the first apply, generate domains in the dashboard for:

- `api`
- `web`
- `admin`
- `minio` (target port **9000**)

You can also use the CLI:

```bash
railway domain --service api
railway domain --service web
railway domain --service admin
railway domain --service minio --port 9000
```

Cross-service references (`VITE_API_BASE_URL`, `ALLOWED_ORIGINS`,
`MINIO_ENDPOINT`, `CSRF_TRUSTED_ORIGINS`) resolve automatically once the
domains exist. If the admin panel returns **400 Bad Request** after a domain is
generated, the Django container was deployed before the domain existed. Trigger
a redeploy of the `admin` service so it picks up the updated `ALLOWED_HOSTS`:

```bash
railway service redeploy --service admin
```

### Secrets

Variables marked `preserve()` in `railway.ts` are set once as
environment-level variables in the Railway dashboard and are never
overwritten or deleted by later applies. They must be set before the first
deploy:

| Service | Variable | Notes |
|---|---|---|
| `api` | `OPENAI_API_KEY` | Required |
| `api` | `AUTH_SECRET_KEY` | Strong random string; required |
| `api` | `SETUP_TOKEN` | Strong random string; required |
| `api` | `MINIO_ACCESS_KEY` | Required |
| `api` | `MINIO_SECRET_KEY` | Required |
| `api` | `RAILWAY_TOKEN` | Project token for feature flags |
| `minio` | `MINIO_ROOT_USER` | Same as `MINIO_ACCESS_KEY` |
| `minio` | `MINIO_ROOT_PASSWORD` | Same as `MINIO_SECRET_KEY` |
| `admin` | `SECRET_KEY` | Django secret |
| `admin` | `DJANGO_SUPERUSER_PASSWORD` | Set from GitHub secret (see below) |
| `data-pipeline` | `OPENAI_API_KEY` | Required for embeddings |
| `data-pipeline` | `APIFY_API_TOKEN` | Required for Screwfix scraping |

### GitHub Actions secrets

The CI/CD pipeline expects these secrets in the `MyTradePortal/Production`
environment:

| Secret | Required | Purpose |
|---|---|---|
| `RAILWAY_TOKEN` | Yes | Project token used by `railway config apply` |
| `DJANGO_SUPERUSER_PASSWORD` | Yes | Production Django superuser password |
| `E2E_BASE_URL` | Yes | Public URL of the `web` service for smoke tests |
| `E2E_ADMIN_BASE_URL` | Yes | Public URL of the `admin` service for smoke tests |
| `DATABASE_URL` | Yes | Used by the smoke-test teardown step to clean up |

Optional:

| Secret | Purpose |
|---|---|
| `PADDLE_API_KEY` | Enable Paddle payments |
| `PADDLE_WEBHOOK_SECRET` | Paddle webhook HMAC verification |

---

## Playbook 1: Clean ground-up production deploy

Use this when Railway has no existing MyTradePortal project or when you want a
fresh production environment.

### 1. Prerequisites

- GitHub repository with the Railway GitHub App installed.
- Railway CLI installed and authenticated (`railway login`).
- GitHub Actions environment `MyTradePortal/Production` created with the secrets
  listed above.
- OpenAI API key with available credits.
- (Optional) Paddle account and API credentials if payments are enabled.

### 2. Create the Railway project

```bash
cd .railway
railway login
railway link
```

If no project exists yet, create one in the Railway dashboard first, then link
it. The environment should be named `production` (matching `RAILWAY_ENVIRONMENT`
in `.github/workflows/ci.yml`).

### 3. Configure secrets

In the Railway dashboard, set the `preserve()` variables for every service
before the first deploy. Do **not** rely on defaults in production.

Required minimum (set as **environment-level variables** in the Railway dashboard, and declared in `.railway/railway.ts` with `preserve()` so they are not deleted on later IaC applies):

1. `api` → `OPENAI_API_KEY`, `AUTH_SECRET_KEY`, `SETUP_TOKEN`,
   `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `RAILWAY_TOKEN`.
2. `minio` → `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` (same values as
   `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`).
3. `admin` → `SECRET_KEY`, `DJANGO_SUPERUSER_PASSWORD`.
4. `data-pipeline` → `OPENAI_API_KEY`, `APIFY_API_TOKEN`.

### 4. Apply the infrastructure

```bash
cd .railway
railway config plan
railway config apply
```

This creates the Postgres, Redis, Qdrant, MinIO and application services. The
services may fail their first healthchecks until domains and the MinIO bucket are
configured; this is expected.

### 5. Generate public domains

In the Railway dashboard, generate public domains for:

- `api`
- `web`
- `admin`
- `minio` (target port **9000**)

Wait for the services to redeploy and report healthy.

### 6. Create the MinIO bucket

Open the MinIO console at the generated `minio` domain on port **9001** (or use
the `mc` CLI) and create the bucket named `mtp-uploads`.

### 7. Initialise the database

The API and admin pre-deploy commands run `scripts/init_db.py`, which is
idempotent. On the very first deploy this creates the FastAPI schema and Django
admin tables. Verify it succeeded by checking the deploy logs for `api` and
`admin`.

If you ever need to re-run it manually:

```bash
railway run --service api python scripts/init_db.py
railway run --service admin python scripts/init_db.py
```

### 8. Create the production Django superuser

The admin service creates the superuser automatically on first deploy if
`DJANGO_SUPERUSER_PASSWORD` is set. Verify by logging in to:

```text
https://<admin-domain>/admin/
```

with username `superadmin` and the password from `DJANGO_SUPERUSER_PASSWORD`.

If you need to rotate the password later, set the new value in the Railway
dashboard and redeploy the admin service; the pre-deploy command will not
recreate the user, so use the Django admin UI or `createsuperuser` to rotate.

### 9. Create the first tenant

Use the Django admin UI:

1. Log in to `/admin/` as `superadmin`.
2. Go to **Operations → Tenants → Add**.
3. Enter a slug (e.g. `acme`) and name, then save.
4. Go to **Operations → Users → Add**.
5. Select the tenant, set the admin email, full name, role (`admin`) and
   password, then save.

Alternatively, use the gated `POST /tenants` endpoint once:

```bash
curl -X POST https://<api-domain>/tenants \
  -H "Content-Type: application/json" \
  -H "X-Setup-Token: $SETUP_TOKEN" \
  -d '{
    "slug": "acme",
    "name": "ACME Electrical",
    "admin_email": "you@example.com",
    "admin_password": "..."
  }'
```

Remove or rotate `SETUP_TOKEN` after the first tenant is created.

### 10. Seed the cost database and knowledge base

The data-pipeline pre-deploy command runs `scripts/init_data_pipeline.py` on
every deploy, which in turn runs the curated seed loader and the knowledge
loader. These create the `cost_items` and `quoting_knowledge` Qdrant
collections and populate the Postgres `cost_items` table. They are idempotent
and can be re-run if needed.

To run them manually:

```bash
railway run --service data-pipeline python -m data_pipeline.load_curated_seed
railway run --service data-pipeline python -m data_pipeline.knowledge_loader
```

### 11. Verify the deployment

1. Open the web UI at `https://<web-domain>/login` and log in with the first
   tenant slug and admin credentials.
2. Run the production smoke test workflow in GitHub Actions (see
   [Post-deploy verification](#post-deploy-verification)).
3. Check the API health endpoint: `https://<api-domain>/health`.
4. Check the OCERP health endpoint: `https://<ocerp-domain>/health`.

---

## Playbook 2: Deploy onto existing production

Use this when the Railway project, domains, and first tenant already exist.

### 1. Merge changes to `main`

All changes must pass the CI pipeline before deploy:

```bash
ruff check .
ruff format --check .
mypy services/api packages/shared/py
mypy --config-file mypy-admin.ini services/admin
pytest
pnpm --filter web lint
pnpm --filter web build
```

### 2. Push to `main`

```bash
git push origin main
```

### 3. CI deploys automatically

`.github/workflows/ci.yml` runs:

1. Python lint, format, type check and tests.
2. TypeScript lint, tests and build.
3. Railway `config apply` to the `production` environment (only on `main` push).

The deploy job sets `DJANGO_SUPERUSER_PASSWORD` from the GitHub secret and then
applies the configuration. Monitor the run in the GitHub Actions tab.

### 4. Verify the deploy in Railway

In the Railway dashboard:

1. Confirm all services show **Healthy**.
2. Check the **Deploy logs** for `api` and `admin` to confirm
   `scripts/init_db.py` ran without errors.
3. Confirm no new public domains were requested unexpectedly.

### 5. Verify the application

- `https://<api-domain>/health` returns 200.
- `https://<ocerp-domain>/health` returns 200.
- `https://<admin-domain>/admin/login/` loads.
- Log in to the back office with an existing tenant and smoke-test a quote.

### 6. Run the production smoke test

Trigger the **Production Smoke Test** workflow in GitHub Actions. It creates a
temporary tenant through the Django admin UI, exercises customer, quote, invoice
and job flows, and tears down the test data afterwards.

### 7. Rollback if needed

If a deploy causes issues, use the Railway dashboard to redeploy the previous
healthy deployment of the affected service. You can also pin a service image or
revert the commit on `main` and let CI redeploy.

---

## Post-deploy verification

### Production smoke test workflow

`.github/workflows/smoke-production.yml` runs automatically after a successful CI
deploy, or manually via `workflow_dispatch`.

It requires these environment variables:

| Variable | Source |
|---|---|
| `E2E_BASE_URL` | GitHub secret |
| `E2E_ADMIN_BASE_URL` | GitHub secret |
| `E2E_DJANGO_ADMIN_USERNAME` | Defaults to `superadmin` |
| `E2E_DJANGO_ADMIN_PASSWORD` | GitHub secret `DJANGO_SUPERUSER_PASSWORD` |
| `DATABASE_URL` | GitHub secret |

The test creates a tenant with slug prefix `prod-smoke-` and removes it at the
end. It does **not** delete the production `superadmin` account.

### Manual smoke test

```bash
cd web/app
E2E_BASE_URL=https://<web-domain> \
E2E_ADMIN_BASE_URL=https://<admin-domain> \
E2E_DJANGO_ADMIN_USERNAME=superadmin \
E2E_DJANGO_ADMIN_PASSWORD=... \
pnpm exec playwright test --config=playwright.config.prod-smoke.ts
```

### Health checks

```bash
curl https://<api-domain>/health
curl https://<ocerp-domain>/health
curl https://<admin-domain>/health
```

---

## Security and operations

### Multi-tenancy

- Every tenant-scoped request must include `X-Tenant-ID` or resolve through the
  subdomain.
- PostgreSQL Row-Level Security policies enforce isolation at the database layer.
- The application role (`mtp_app`) cannot bypass RLS.

### Secrets

- Never commit secrets to the repository.
- Rotate `AUTH_SECRET_KEY`, `SETUP_TOKEN`, `DJANGO_SUPERUSER_PASSWORD` and
  `PADDLE_WEBHOOK_SECRET` after any suspected leak.
- `DJANGO_SUPERUSER_PASSWORD` is set from the GitHub Actions environment and is
  preserved in Railway.

### Feature flags

Unreleased features are gated by `GET /feature-flags` and default to off. To
manage them:

1. Create a project token in Railway (**Project Settings → Tokens**).
2. Set `RAILWAY_TOKEN` on the `api` service.
3. Toggle flags under **Project Settings → Feature Flags** in Railway.

Known flags:

| Flag | Default | Feature |
|---|---|---|
| `voice_ai_insights` | `false` | Voice AI insights page |
| `demand_forecasting` | `false` | Demand forecasting dashboard |
| `external_integrations` | `false` | External accounting/messaging integrations |

### Backups

- Railway Postgres provides automated backups; configure retention and test
  restores regularly.
- Qdrant and MinIO data live on Railway volumes; schedule your own backups for
  these (e.g. Qdrant snapshots and MinIO bucket replication).

### Cost monitoring

- Quote generation makes OpenAI LLM and embedding calls. Monitor usage and set
  billing alerts in the OpenAI dashboard.
- The data pipeline runs monthly by default; verify `SCRAPE_FREQUENCY` and
  `APIFY_API_TOKEN` usage.

---

## Troubleshooting

### API or admin fails to start with "dev defaults refused"

`Settings.validate_production()` blocks the app when insecure defaults are
present. Check that `AUTH_SECRET_KEY`, `SETUP_TOKEN`, `MINIO_ACCESS_KEY`, and
`MINIO_SECRET_KEY` are set to strong non-default values on the `api` service.

### Admin deploy fails with "relation does not exist"

The `admin` pre-deploy command must run after the `api` pre-deploy command has
created the FastAPI schema. In practice they run in parallel, but `admin`
retries automatically. If it persists, re-run:

```bash
railway run --service admin python scripts/init_db.py
```

### MinIO uploads fail

- Ensure `MINIO_ENDPOINT` is the public Railway domain, not the private one.
- Ensure `MINIO_USE_SSL=true`.
- Ensure the bucket `mtp-uploads` exists.
- Ensure `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` match `MINIO_ROOT_USER` /
  `MINIO_ROOT_PASSWORD`.

### Quotes fail to generate

- Verify `OPENAI_API_KEY` is set and has credits.
- Verify Qdrant is healthy and collections exist.
- Verify the `cost_items` and `quoting_knowledge` collections are seeded.

### Feature flags not applying

- Check that `RAILWAY_TOKEN` is set on the `api` service.
- Check Railway project logs for GraphQL errors.
- Remember flags are cached in-process for 60 seconds.

### Smoke test leaves a tenant behind

The teardown step removes tenants with slug prefix `prod-smoke-` or
`first-customer-`. If a run is cancelled, manually delete the tenant from the
Django admin or via the database.
