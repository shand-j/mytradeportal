# Development guide

## Local Python environment

A virtual environment is already present at `.venv` and the project is installed
in editable mode.

```bash
source .venv/bin/activate
```

Run the API directly for faster iteration (Postgres/Qdrant still needed):

```bash
cd services/api
uvicorn app.main:app --reload --reload-dir /app/services/api --reload-dir /app/packages/shared/py
```

## Tests

```bash
pytest services/api/tests -v
```

The suite covers calculations, quote generation, invoices, tenancy, contacts and
webhooks.

## Linting and type checking

```bash
ruff check services/api/app packages/shared/py
ruff format --check services/api/app packages/shared/py
mypy services/api/app packages/shared/py
```

Auto-format:

```bash
ruff format services/api/app packages/shared/py
```

## Database schema

The API schema is defined solely by the SQLAlchemy models in
`services/api/app/models.py`. There are no Alembic migrations: the schema is
created (idempotently) from the models by `scripts/init_db.py`, which also
creates the non-privileged `mtp_app` role and applies the tenant-isolation RLS
policies. In development the API also creates tables on startup.

```bash
# Create/refresh the schema, app role and RLS policies for a fresh install
python scripts/init_db.py
```

To change the schema, edit the models and re-run the init script (or redeploy,
which runs it as the preDeploy step). For a clean first-time install, start
from an empty database.

## Adding a new endpoint

1. Add SQLAlchemy models to `services/api/app/models.py`.
2. Add Pydantic schemas to `services/api/app/schemas.py`.
3. Create a router in `services/api/app/routers/`.
4. Register the router in `services/api/app/main.py`.
5. Register the model in `services/admin/operations/admin.py` if staff should see
   it in Django admin.
6. Add tests in `services/api/tests/`.

## Useful commands

```bash
# View API logs
docker logs -f mtp_api

# Open a Postgres shell
docker exec -it mtp_postgres psql -U mtp -d mtp

# Reset the database
docker compose down -v && docker compose up -d
```
