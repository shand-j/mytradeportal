# Getting started

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- Python 3.11+ (only if you want to run scripts outside the container)
- An [OpenAI](https://platform.openai.com/) API key (required by the AI quote engine)

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

## Initialise the database

In development the API creates tables on startup. For explicit control (and for
a fresh production-like install), run the single schema-init script:

```bash
python scripts/init_db.py
```

## Configure AI (OpenAI)

The AI quote engine uses OpenAI via LiteLLM in every environment, local
development included:

- Chat: `gpt-4o-mini` (`LLM_MODEL`)
- Embeddings: `text-embedding-3-small` (`EMBEDDING_MODEL`, 1536 dimensions)

Set your key in a `.env` file in the project root (or export it) before
starting the stack:

```bash
OPENAI_API_KEY=sk-...
```

`docker compose up` injects it into the API, OCERP and data-pipeline
containers. AI quote generation fails until a valid key is present.

## Seed data

Seed a local-dev tenant and admin user (credentials come from environment
variables — there are no defaults):

```bash
cd services/api
SEED_ADMIN_EMAIL=you@example.com SEED_ADMIN_PASSWORD=<choose-a-password> \
  python -m app.seed_admin_user
```

Populate the cost database by running the Screwfix data pipeline:

```bash
cd services/data-pipeline
python -m data_pipeline.loader
```

If you already have Apify dataset IDs, import them instead of scraping:

```bash
cd services/data-pipeline
python -m data_pipeline.import_apify_dataset <dataset-id>
```

Ingest the larger DDC CWICR UK electrical cost database:

```bash
cd services/api
python -m app.ingest_ddc_uk
```

> These scripts need the database and a valid `OPENAI_API_KEY` to be reachable.
> The first run may take a few minutes while descriptions are embedded.

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
which is owned by the SQLAlchemy models and `scripts/init_db.py`. By default no
superuser is created; create
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
