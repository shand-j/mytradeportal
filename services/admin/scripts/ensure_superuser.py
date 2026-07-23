"""Create a Django superuser on first production deploy if one is configured.

The admin service uses this as part of its preDeployCommand. It is safe to run
on every deploy: it only creates the superuser when the env vars are set and
no matching user exists yet. If the password var is not configured, it exits
quietly so the container can still boot.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "admin_project.settings")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django

django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "superadmin")
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

if not password:
    print("[ensure_superuser] DJANGO_SUPERUSER_PASSWORD not set; skipping superuser creation")
    sys.exit(0)

if User.objects.filter(username=username).exists():
    print(f"[ensure_superuser] Superuser already exists: {username}")
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"[ensure_superuser] Created superuser: {username}")
