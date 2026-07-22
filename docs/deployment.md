# Deployment

## Local Docker Compose

The included `docker-compose.yml` is the primary local deployment target.

```bash
docker compose up -d
```

All images and required variables have defaults, so it works out of the box once
Ollama is running and reachable.

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
| `OPENAI_API_KEY` | *(empty)* | OpenAI key (optional) |
| `OLLAMA_API_BASE` | `http://host.docker.internal:11434` | Ollama endpoint |
| `EMBEDDING_MODEL` | `ollama/nomic-embed-text` | Embedding model |
| `LLM_MODEL` | `ollama/gpt-oss:latest` | Chat model |
| `EMBEDDING_DIMENSIONS` | *(auto)* | Override vector size |
| `QDRANT_COLLECTION_NAME` | `cost_items` | Vector collection |
| `RAG_TOP_K` | `10` | Number of items retrieved |

### Payments

| Variable | Default | Purpose |
|---|---|---|
| `PADDLE_API_KEY` | *(empty)* | Paddle API key |
| `PADDLE_WEBHOOK_SECRET` | *(empty)* | Paddle webhook verification secret |
| `PADDLE_SANDBOX` | `true` | Use Paddle sandbox |
| `PADDLE_DEFAULT_CURRENCY_CODE` | `GBP` | Default currency |

## Ollama in production

For real deployments, run Ollama on a separate GPU host or use a managed
OpenAI-compatible endpoint. Update `OLLAMA_API_BASE` to the reachable URL.

If you keep Ollama on the Docker host:

- Start it with `OLLAMA_HOST=0.0.0.0:11434` so containers can connect.
- On Linux, `host.docker.internal` is not enabled by default; use the host IP or
  add `--add-host=host.docker.internal:host-gateway`.

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
(TypeScript, evaluated by the Railway CLI). It defines 10 resources:

- `db` (Postgres) and `redis` — native Railway database plugins.
- `qdrant`, `minio`, `ollama` — Docker-image services with mounted volumes.
- `api`, `ocerp`, `web`, `admin`, `data-pipeline` — built from this repo's
  Dockerfiles; the Railway GitHub App auto-deploys them on push.

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
   - `api`: `AUTH_SECRET_KEY`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
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
4. **Pull the Ollama models** once (they persist on the volume):
   exec into the `ollama` service and run
   `ollama pull nomic-embed-text && ollama pull llama3.1:8b`.
5. **Seed the database**:
   `railway run --service api python -m app.seed_admin_user` and
   `python -m app.seed_cost_items`, plus
   `railway run --service data-pipeline python -m data_pipeline.knowledge_loader`.

Migrations run automatically: the API container executes `alembic upgrade
head` before starting uvicorn, and `alembic/env.py` honours the injected
`DATABASE_URL`.

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
- Ollama runs CPU-only: expect slow quote generation (several LLM calls per
  BoQ). `llama3.1:8b` needs 8–12GB RAM; scale the service accordingly.
