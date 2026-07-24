FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/admin/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY services/admin ./

ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=admin_project.settings

EXPOSE 8001

# Collect static assets for whitenoise, then serve with gunicorn.
# Migrations are run via scripts/init_db.py (Railway preDeployCommand).
# Railway injects $PORT; default to 8001 locally.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && gunicorn admin_project.wsgi --bind 0.0.0.0:${PORT:-8001}"]
