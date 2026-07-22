FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/ocerp

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY packages/shared/py ./packages/shared/py

RUN pip install --no-cache-dir -e ".[dev]"

COPY services/ocerp ./services/ocerp

EXPOSE 8000

CMD ["uvicorn", "ocerp.main:app", "--host", "0.0.0.0", "--port", "8000"]
