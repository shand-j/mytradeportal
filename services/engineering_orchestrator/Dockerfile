FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git nodejs npm \
    && npm install -g @railway/cli \
    && rm -rf /var/lib/apt/lists/*

COPY services/engineering_orchestrator/pyproject.toml ./
COPY services/engineering_orchestrator/src ./src

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

EXPOSE 8010
CMD ["sh", "-c", "uvicorn engineering_orchestrator.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8010}"]
