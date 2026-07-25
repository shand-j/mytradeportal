# Local Production-Like E2E from Railway Variables

This runbook describes a working path to run local production-like Playwright validation using variables pulled from hosted Railway `production`.

Validated on 2026-07-25 with a full suite execution (tests executed end-to-end; functional failures remained in app/test logic, not environment bootstrap).

## Goal

- Use real hosted production variable values as the local baseline.
- Keep local-only overrides explicit and minimal.
- Preserve repeatability for pre-go-live validation.

## Prerequisites

- Railway CLI installed and authenticated.
- Repository root available locally.
- Docker + Docker Compose available.
- `pnpm` installed.

## 1) Pull hosted variables

Run from [.railway](../../.railway):

```bash
RAILWAY_CALLER=skill:use-railway@1.3.6 RAILWAY_AGENT_SESSION=railway-skill-<id> \
  railway variable list --service api --environment production --json > /tmp/railway_api_prod_vars.json

RAILWAY_CALLER=skill:use-railway@1.3.6 RAILWAY_AGENT_SESSION=railway-skill-<id> \
  railway variable list --service admin --environment production --json > /tmp/railway_admin_prod_vars.json

RAILWAY_CALLER=skill:use-railway@1.3.6 RAILWAY_AGENT_SESSION=railway-skill-<id> \
  railway variable list --service web --environment production --json > /tmp/railway_web_prod_vars.json
```

Do not print these files in shared logs because they contain secrets.

## 2) Generate local runtime env file

Generate `/tmp/mytradeportal.e2e.prodlike.env` from the JSON files.

Required local-only overrides:

- `AUTH_COOKIE_SECURE=false` for local HTTP cookie flow.
- `SUPABASE_URL=`, `SUPABASE_ANON_KEY=`, `SUPABASE_SERVICE_ROLE_KEY=` for deterministic local password auth.
- `VITE_API_BASE_URL=` so local web targets local API host-derived URL.

## 3) Runtime compose override (not committed)

Create `/tmp/docker-compose.e2e-hosted-vars.override.yml` with API-only runtime injections that are not fully wired in [docker-compose.yml](../../docker-compose.yml):

```yaml
services:
  api:
    environment:
      APP_ROLE_NAME: ${APP_ROLE_NAME}
      APP_ROLE_PASSWORD: ${APP_ROLE_PASSWORD}
      AUTH_COOKIE_SECURE: ${AUTH_COOKIE_SECURE}
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
      SUPABASE_SERVICE_ROLE_KEY: ${SUPABASE_SERVICE_ROLE_KEY}
      ALLOWED_ORIGINS: http://demo.localhost:3000,http://localhost:3000
```

## 4) Align DB app-role password and start stack

From repository root:

```bash
export $(grep -v '^#' /tmp/mytradeportal.e2e.prodlike.env | xargs)

docker exec mtp_postgres psql -U mtp -d mtp \
  -c "ALTER ROLE ${APP_ROLE_NAME:-mtp_app} WITH PASSWORD '${APP_ROLE_PASSWORD}';"

VITE_API_BASE_URL= ENVIRONMENT=production \
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod-like.yml \
    -f /tmp/docker-compose.e2e-hosted-vars.override.yml \
    --env-file /tmp/mytradeportal.e2e.prodlike.env \
    up -d --build api web admin postgres redis qdrant
```

## 5) Bootstrap deterministic tenant

```bash
set -a && source /tmp/mytradeportal.e2e.prodlike.env && set +a

E2E_TENANT_SLUG=prodlocal-railway \
E2E_TENANT_NAME='Prod Local Railway' \
E2E_ADMIN_EMAIL=prodlocal-railway@example.com \
E2E_ADMIN_PASSWORD='e2e-password-123' \
E2E_ADMIN_NAME='Prod Local Railway Admin' \
./web/app/e2e/bootstrap-tenant.sh
```

## 6) Run Playwright

Use a config that does not auto-start stack via `webServer` (stack is already running in prod-like mode):

```bash
cd web/app
E2E_TENANT_SLUG='prodlocal-railway' \
E2E_ADMIN_EMAIL='prodlocal-railway@example.com' \
E2E_ADMIN_PASSWORD='e2e-password-123' \
E2E_DJANGO_ADMIN_USERNAME='superadmin' \
E2E_DJANGO_ADMIN_PASSWORD='<from hosted admin vars>' \
E2E_ADMIN_BASE_URL='http://localhost:8001' \
ENVIRONMENT=production \
pnpm exec playwright test --config=/tmp/playwright.prodlike.hosted-vars.config.ts
```

## Known local exceptions

These are expected and intentional for local parity runs:

- Hosted-origin values (for example, hosted web-to-api URL) are not used locally.
- Cookie `secure=true` is incompatible with local HTTP.
- CORS origins must include local web origins.
- API app-role password must match the local Postgres role password.

## Redacted snapshot (keys only)

Keys observed in hosted production env pulls during validation.

### API service

`ALLOWED_ORIGINS`, `APP_ROLE_NAME`, `APP_ROLE_PASSWORD`, `AUTH_SECRET_KEY`, `DATABASE_URL`, `EMBEDDING_MODEL`, `ENVIRONMENT`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `LOG_LEVEL`, `MINIO_ACCESS_KEY`, `MINIO_BUCKET`, `MINIO_ENDPOINT`, `MINIO_SECRET_KEY`, `MINIO_USE_SSL`, `NEW_RELIC_APP_NAME`, `NEW_RELIC_LICENSE_KEY`, `OCERP_URL`, `OPENAI_API_KEY`, `PADDLE_SANDBOX`, `PORT`, `QDRANT_COLLECTION_NAME`, `QDRANT_KNOWLEDGE_COLLECTION_NAME`, `QDRANT_URL`, `RAILWAY_ENVIRONMENT`, `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_PRIVATE_DOMAIN`, `RAILWAY_PROJECT_ID`, `RAILWAY_PROJECT_NAME`, `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_SERVICE_ADMIN_URL`, `RAILWAY_SERVICE_API_URL`, `RAILWAY_SERVICE_ID`, `RAILWAY_SERVICE_MINIO_URL`, `RAILWAY_SERVICE_NAME`, `RAILWAY_SERVICE_WEB_URL`, `RAILWAY_STATIC_URL`, `RAILWAY_TOKEN`, `REDIS_URL`, `SETUP_TOKEN`

### Admin service

`ALLOWED_HOSTS`, `APP_ROLE_NAME`, `APP_ROLE_PASSWORD`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `DEBUG`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`, `DJANGO_SUPERUSER_USERNAME`, `NEW_RELIC_APP_NAME`, `NEW_RELIC_LICENSE_KEY`, `PORT`, `RAILWAY_ENVIRONMENT`, `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_PRIVATE_DOMAIN`, `RAILWAY_PROJECT_ID`, `RAILWAY_PROJECT_NAME`, `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_SERVICE_ADMIN_URL`, `RAILWAY_SERVICE_API_URL`, `RAILWAY_SERVICE_ID`, `RAILWAY_SERVICE_MINIO_URL`, `RAILWAY_SERVICE_NAME`, `RAILWAY_SERVICE_WEB_URL`, `RAILWAY_STATIC_URL`, `SECRET_KEY`

### Web service

`PORT`, `RAILWAY_ENVIRONMENT`, `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_PRIVATE_DOMAIN`, `RAILWAY_PROJECT_ID`, `RAILWAY_PROJECT_NAME`, `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_SERVICE_ADMIN_URL`, `RAILWAY_SERVICE_API_URL`, `RAILWAY_SERVICE_ID`, `RAILWAY_SERVICE_MINIO_URL`, `RAILWAY_SERVICE_NAME`, `RAILWAY_SERVICE_WEB_URL`, `RAILWAY_STATIC_URL`, `VITE_API_BASE_URL`
