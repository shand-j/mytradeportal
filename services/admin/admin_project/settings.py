"""Django settings for the My Trade Portal admin panel."""

from pathlib import Path

import environ

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "dev-secret-key-change-in-production"),
    DATABASE_URL=(str, "postgresql://mtp:mtp@postgres:5432/mtp"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Defensive: always accept the Railway-assigned domains so the admin panel keeps
# working even if ALLOWED_HOSTS was baked into the image before a public domain
# was generated, or if the domain changes after a redeploy.
_ALLOWED_HOSTS_ENV = {
    *ALLOWED_HOSTS,
    env("RAILWAY_PUBLIC_DOMAIN", default=""),
    env("RAILWAY_PRIVATE_DOMAIN", default=""),
    env("RAILWAY_STATIC_URL", default=""),
}
ALLOWED_HOSTS = [h for h in _ALLOWED_HOSTS_ENV if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "operations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "admin_project.urls"
WSGI_APPLICATION = "admin_project.wsgi.application"

DATABASES = {"default": env.db()}
# The API uses asyncpg; Django expects the synchronous psycopg2 backend.
if DATABASES["default"]["ENGINE"] == "postgresql+asyncpg":
    DATABASES["default"]["ENGINE"] = "django.db.backends.postgresql"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    *env("CSRF_TRUSTED_ORIGINS"),
]
# Defensive: always trust the Railway public domain so admin login forms work
# even if the variable was baked before the public domain existed.
_railway_public = env("RAILWAY_PUBLIC_DOMAIN", default="")
if _railway_public:
    CSRF_TRUSTED_ORIGINS.append(f"https://{_railway_public}")
