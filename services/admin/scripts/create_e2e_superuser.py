"""Create a temporary Django superuser for E2E admin-onboarding tests."""
import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "admin_project.settings")

# Django admin project is one directory up from this script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django

django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get("E2E_DJANGO_ADMIN_USERNAME", "e2e-superadmin")
email = os.environ.get("E2E_DJANGO_ADMIN_EMAIL", "e2e-superadmin@example.com")
password = os.environ.get("E2E_DJANGO_ADMIN_PASSWORD")

if not password:
    raise RuntimeError("E2E_DJANGO_ADMIN_PASSWORD must be set")

user, created = User.objects.get_or_create(username=username, defaults={"email": email})
if created:
    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.save()
    print(f"Created Django superuser: {username}")
else:
    user.email = email
    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.save()
    print(f"Updated Django superuser: {username}")
