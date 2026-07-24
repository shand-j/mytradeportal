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

# Default command: run the pipeline once and exit.
# For scheduling, use Railway's Cron Schedule service setting.
# For ad-hoc runs, deploy/redeploy this service or trigger it manually.
CMD ["python", "-m", "data_pipeline.loader"]
