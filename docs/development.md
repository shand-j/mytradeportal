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

## Database migrations

Migrations live in `services/api/alembic` and are driven by Alembic. The FastAPI
app also creates tables on startup in development, but Alembic is the source of
truth.

```bash
PYTHONPATH=services/api alembic revision --autogenerate -m "description"
PYTHONPATH=services/api alembic upgrade head
```

## Adding a new endpoint

1. Add SQLAlchemy models to `services/api/app/models.py` (and a migration).
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
