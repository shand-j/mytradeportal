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
COPY scripts/init_data_pipeline.py ./scripts/init_data_pipeline.py
COPY docs ./docs

# Install the pipeline package in editable mode
RUN pip install --no-cache-dir -e ".[dev]"

ENV PYTHONPATH=/app/src:/app/packages/shared/py
ENV PYTHONUNBUFFERED=1

# Default command: run the scheduler and execute the pipeline on startup
CMD ["python", "-m", "data_pipeline.scheduler", "--run-on-start"]
