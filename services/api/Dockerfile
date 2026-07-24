FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/api

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY alembic.ini ./
COPY packages/shared/py ./packages/shared/py

RUN pip install --no-cache-dir -e ".[dev]"

COPY scripts/init_db.py ./scripts/init_db.py
COPY scripts/init_data_pipeline.py ./scripts/init_data_pipeline.py
COPY scripts/init_api.py ./scripts/init_api.py
COPY services/data-pipeline/src ./services/data-pipeline/src

COPY services/api ./services/api

EXPOSE 8000

# Serve only. Schema is created via scripts/init_db.py (Railway preDeployCommand).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
