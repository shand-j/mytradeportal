"""WSGI config for admin_project."""

import os

from django.core.wsgi import get_wsgi_application

from admin_project.healthcheck import HealthCheckMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "admin_project.settings")

application = HealthCheckMiddleware(get_wsgi_application())
