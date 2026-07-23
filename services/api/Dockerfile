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

COPY services/api ./services/api

EXPOSE 8000

# Apply migrations, then serve. Railway injects $PORT; default to 8000 locally.
# --proxy-headers lets uvicorn honour X-Forwarded-For from Railway's edge proxy
# so slowapi sees real client IPs instead of the proxy's.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
