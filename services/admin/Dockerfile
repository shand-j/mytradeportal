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

CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
