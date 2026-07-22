# Getting started

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- Python 3.11+ (only if you want to run scripts outside the container)
- (Optional) [Ollama](https://ollama.com/) for local AI embeddings and chat

## Start the local stack

```bash
docker compose up -d
```

This starts:

| Service | Container | Port | Purpose |
|---|---|---|---|
| API | `mtp_api` | `8000` | FastAPI backend |
| Admin | `mtp_admin` | `8001` | Django admin panel |
| Postgres | `mtp_postgres` | `5432` | Operational database |
| Redis | `mtp_redis` | `6379` | Cache / broker |
| Qdrant | `mtp_qdrant` | `6333` | Vector database |
| MinIO | `mtp_minio` | `9000/9001` | Object storage |
| Mailpit | `mtp_mailpit` | `1025/8025` | Email capture |

## Run migrations

In development the API creates tables on startup. For explicit control:

```bash
PYTHONPATH=services/api alembic upgrade head
```

## Configure AI (Ollama)

The default models are local Ollama models:

- Embeddings: `ollama/nomic-embed-text`
- Chat: `ollama/gpt-oss:latest`

1. Install and start Ollama so it listens on all interfaces (required for Docker):

   ```bash
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   ```

2. Pull the models:

   ```bash
   ollama pull nomic-embed-text
   ollama pull gpt-oss:latest
   ```

The API container already points to `http://host.docker.internal:11434` via the
`OLLAMA_API_BASE` variable in `docker-compose.yml`.

To use OpenAI instead, set `OPENAI_API_KEY`, `EMBEDDING_MODEL` and `LLM_MODEL` in
a `.env` file or export them before running `docker compose up`.

## Seed data

Seed the built-in UK electrical cost items and generate embeddings:

```bash
cd services/api
python -m app.seed_cost_items
```

Ingest the larger DDC CWICR UK electrical cost database:

```bash
python -m app.ingest_ddc_uk
```

> These scripts need the database and Ollama to be reachable. The first run may
> take a few minutes while descriptions are embedded.

## Verify the API

OpenAPI docs: http://localhost:8000/docs  
Health check: http://localhost:8000/health

Generate a quote from the command line:

```bash
curl -X POST http://localhost:8000/quotes/generate \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: <your-tenant-id>" \
  -d '{
    "description": "Install two extra double sockets in the kitchen",
    "customer_name": "Alice",
    "customer_email": "alice@example.com"
  }'
```

Create a tenant first if you do not have an ID:

```bash
curl -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{"slug": "demo", "name": "Demo Electrical"}'
```

## Access the admin panel

Django admin runs at http://localhost:8001/admin.

The admin models are unmanaged (`managed = False`) and mirror the FastAPI schema,
so migrations remain owned by Alembic. By default no superuser is created; create
one inside the `mtp_admin` container if you need it:

```bash
docker exec -it mtp_admin python manage.py createsuperuser
```

## Stop everything

```bash
docker compose down
```

To remove persistent data as well:

```bash
docker compose down -v
```
