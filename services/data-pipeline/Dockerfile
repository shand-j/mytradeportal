FROM python:3.11-slim

WORKDIR /app

# Install build dependencies and curl for healthchecks
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package manifest, source, shared init script, and knowledge-base docs
COPY services/data-pipeline/pyproject.toml ./
COPY services/data-pipeline/src ./src
COPY services/data-pipeline/config ./config
COPY packages/shared/py ./packages/shared/py

# Install the pipeline package in editable mode
RUN pip install --no-cache-dir -e ".[dev]"

ENV PYTHONPATH=/app/src:/app/packages/shared/py
ENV PYTHONUNBUFFERED=1

# Default command: run the scheduler loop continuously. The scheduler fires the
# pipeline on its configured schedule and exposes a /health endpoint for Railway.
# For a one-off manual run, use: python -m data_pipeline.loader
# New Relic APM wrapper is enabled automatically when NEW_RELIC_LICENSE_KEY is set.
# Note: railway.ts overrides this CMD via `start` — keep the wrapper in both.
CMD ["sh", "-c", "newrelic-admin run-program python -m data_pipeline.scheduler"]
