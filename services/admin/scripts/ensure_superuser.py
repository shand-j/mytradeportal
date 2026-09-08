"""Create or sync the Django superuser on production deploys.

The admin service uses this as part of its preDeployCommand. It is safe to run
on every deploy: it creates the superuser when none exists, and when one does
exist it re-syncs the password to DJANGO_SUPERUSER_PASSWORD (so rotating the
variable actually takes effect on the next deploy). If the password var is not
configured, it exits quietly so the container can still boot.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "admin_project.settings")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django
from django.contrib.auth import get_user_model

django.setup()

User = get_user_model()

username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

if not password:
    print("[ensure_superuser] DJANGO_SUPERUSER_PASSWORD not set; skipping superuser creation")
    sys.exit(0)

if not username or not email:
    print(
        "[ensure_superuser] DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_EMAIL "
        "must be set when DJANGO_SUPERUSER_PASSWORD is set"
    )
    sys.exit(1)

if User.objects.filter(username=username).exists():
    user = User.objects.get(username=username)
    if user.check_password(password):
        print(f"[ensure_superuser] Superuser already up to date: {username}")
    else:
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()
        print(f"[ensure_superuser] Synced password for existing superuser: {username}")
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"[ensure_superuser] Created superuser: {username}")
