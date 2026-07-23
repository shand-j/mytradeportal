# Deployment

## Local Docker Compose

The included `docker-compose.yml` is the primary local deployment target.

```bash
docker compose up -d
```

All images and required variables have defaults; the only required secret is
`OPENAI_API_KEY` in a `.env` file in the project root.

## Environment variables

The API and admin containers read variables from the shell or a `.env` file in
the project root.

### Core

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://mtp:mtp@postgres:5432/mtp` | Postgres connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant connection |
| `MINIO_ENDPOINT` | `minio:9000` | S3-compatible storage |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `ENVIRONMENT` | `development` | `development` / `production` |

### AI / RAG

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI key — mandatory in all environments |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `LLM_MODEL` | `gpt-4o-mini` | Chat model |
| `EMBEDDING_DIMENSIONS` | `1536` | Vector size (Qdrant collections) |
| `QDRANT_COLLECTION_NAME` | `cost_items` | Vector collection |
| `RAG_TOP_K` | `10` | Number of items retrieved |

### Payments

| Variable | Default | Purpose |
|---|---|---|
| `PADDLE_API_KEY` | *(empty)* | Paddle API key |
| `PADDLE_WEBHOOK_SECRET` | *(empty)* | Paddle webhook verification secret |
| `PADDLE_SANDBOX` | `true` | Use Paddle sandbox |
| `PADDLE_DEFAULT_CURRENCY_CODE` | `GBP` | Default currency |

## AI provider

OpenAI is the required AI provider in every environment, local development
included. Set `OPENAI_API_KEY` and keep the defaults `LLM_MODEL=gpt-4o-mini`
and `EMBEDDING_MODEL=text-embedding-3-small`; Qdrant collections are created
at 1536 dimensions.

## Production checklist

- Switch `ENVIRONMENT` to `production`.
- Use a managed PostgreSQL instance and Redis service.
- Set strong secrets for `PADDLE_WEBHOOK_SECRET`, `ADMIN_SECRET_KEY`, etc.
- Run migrations with Alembic before starting the API.
- Disable FastAPI's auto table creation (`ENVIRONMENT=production`).
- Configure TLS at the load balancer / reverse proxy.
- Set up off-site backups for PostgreSQL and Qdrant.

## Scaling notes

- The API is stateless and can be horizontally scaled.
- Qdrant can run as a cluster for high query volume.
- Use a CDN for the customer PWA and uploaded assets.

## Railway (Infrastructure as Code)

The whole Railway project is declared in [`.railway/railway.ts`](../.railway/railway.ts)
using the [Railway IaC DSL](https://docs.railway.com/infrastructure-as-code)
(TypeScript, evaluated by the Railway CLI). It defines 9 services:

- `db` (Postgres) and `redis` — native Railway database plugins.
- `qdrant` and `minio` — Docker-image services with mounted volumes
  (`minio/minio:latest`, volume at `/mnt/data`).
- `api`, `ocerp`, `web`, `admin`, `data-pipeline` — built from this repo's
  Dockerfiles; the Railway GitHub App auto-deploys them on push. `api` and
  `ocerp` pin `PORT=8000`.

### One-time setup

1. Push this repository to GitHub and install the **Railway GitHub App** on it.
2. Set the repo slug in `.railway/railway.ts` (`GITHUB_REPO`) or export
   `MTP_GITHUB_REPO=<owner>/<repo>`.
3. Install the [Railway CLI](https://docs.railway.com/guides/cli), then
   `railway login` and `railway link` this directory to a project/environment.
4. Install the IaC dependencies: `cd .railway && npm install`.

### Plan and apply

```bash
railway config plan    # preview the diff (safe, read-only)
railway config apply   # apply after confirmation
```

### After the first apply (manual steps)

1. **Set secrets in the dashboard** (variables marked `preserve()` in
   `railway.ts`, so later applies never overwrite them):
   - `api`: `OPENAI_API_KEY`, `SETUP_TOKEN`, `AUTH_SECRET_KEY`,
     `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
     (mandatory — `validate_production()` refuses dev defaults), optional
     `PADDLE_API_KEY` / `PADDLE_WEBHOOK_SECRET`.
   - `minio`: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` (same values as above).
   - `admin`: `SECRET_KEY`.
   - `data-pipeline`: `APIFY_API_TOKEN`.
2. **Generate public domains** in the dashboard (IaC cannot create these):
   `api`, `web`, `admin`, and `minio` (target port **9000**). Cross-service
   references (`VITE_API_BASE_URL`, `ALLOWED_ORIGINS`, `MINIO_ENDPOINT`,
   `CSRF_TRUSTED_ORIGINS`) resolve automatically once the domains exist.
3. **Create the MinIO bucket** `mtp-uploads` (e.g. via the MinIO console on
   port 9001, or `mc mb`).
4. **Bootstrap the first tenant**: in production, `POST /tenants` is gated by
   the `SETUP_TOKEN` variable (a `preserve()` env on `api`) and atomically
   creates the tenant plus its first admin user. Send the token in the
   `X-Setup-Token` header:

   ```bash
   curl -X POST https://<api-domain>/tenants \
     -H "Content-Type: application/json" \
     -H "X-Setup-Token: $SETUP_TOKEN" \
     -d '{"slug": "acme", "name": "ACME Electrical",
          "admin_email": "you@example.com", "admin_password": "..."}'
   ```

   Remove or rotate `SETUP_TOKEN` once the first tenant exists.
5. **Seed the database**:
   `railway run --service data-pipeline python -m data_pipeline.load_curated_seed`
   and
   `railway run --service data-pipeline python -m data_pipeline.knowledge_loader`.

   Do **not** run `app.seed_admin_user` in production — it is a local-dev
   bootstrap only and refuses to run when `ENVIRONMENT=production`; use the
   `POST /tenants` flow above for the first tenant.

Migrations run automatically: the API container executes `alembic upgrade
head` before starting uvicorn, and `alembic/env.py` honours the injected
`DATABASE_URL`.

### Feature flags (Railway Signals)

Unreleased features (voice AI insights, demand forecasting, external
integrations) are gated behind runtime flags served by `GET /feature-flags`
and default to **off**. To manage them: create a **project token** in the
Railway dashboard (Project Settings → Tokens) and set it as `RAILWAY_TOKEN`
on the `api` service (with `RAILWAY_PROJECT_ID` set to the project id), then
toggle flags (e.g. `voice_ai_insights`) under **Project Settings → Feature
Flags**. Without these variables (e.g. local dev) every flag resolves off.

### Railway-specific behaviour in the codebase

- `mtp_shared` rewrites plain `postgresql://` URLs to `postgresql+asyncpg://`.
- The auth cookie uses `SameSite=None; Secure` in production (web and API are
  on different sites).
- Generated `*.railway.app` hosts are treated as bare domains for tenant
  resolution (falls back to `default_tenant_slug`); use a custom domain with
  per-tenant subdomains for real multi-tenant hosting.
- MinIO presigned URLs honour `MINIO_USE_SSL=true` so browsers can upload over
  HTTPS.

### Caveats

- Railway IaC is **experimental**; verify with `railway config plan` after any
  edit and see the header comment in `.railway/railway.ts` for current
  limitations.
- Quote generation makes several OpenAI LLM calls per BoQ; monitor spend and
  set usage limits in the OpenAI dashboard.
