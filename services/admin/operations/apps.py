"""Django app configuration for operations admin."""

from django.apps import AppConfig


class OperationsConfig(AppConfig):
    """Configuration for the operations admin app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "operations"
    verbose_name = "Operations"
