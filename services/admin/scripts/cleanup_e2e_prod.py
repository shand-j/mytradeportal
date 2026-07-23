"""Remove E2E tenants and the temporary Django superuser from production."""

import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "admin_project.settings")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django
from django.contrib.auth import get_user_model
from sqlalchemy import create_engine, text

django.setup()


def clean() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required")

    # Use sync engine for cleanup.
    engine = create_engine(db_url)

    test_tenant_slugs = [
        os.environ.get("E2E_TENANT_SLUG", "e2e-prod-"),
    ]
    # Also remove any first-customer-* tenants created by the admin-onboarding test.
    admin_onboarding_prefix = "first-customer-"

    with engine.begin() as conn:
        # Find tenant IDs to delete.
        result = conn.execute(
            text("SELECT id, slug FROM tenants WHERE slug = ANY(:slugs) OR slug LIKE :prefix"),
            {
                "slugs": test_tenant_slugs,
                "prefix": f"{admin_onboarding_prefix}%",
            },
        )
        tenant_ids = [(row.id, row.slug) for row in result]

        for tenant_id, slug in tenant_ids:
            print(f"Deleting tenant {slug} ({tenant_id}) and all related data")
            # Foreign keys should cascade, but delete core tenant-scoped tables
            # explicitly to be safe.
            for table in [
                "audit_logs",
                "reviews",
                "communications",
                "payments",
                "invoice_line_items",
                "invoices",
                "appointments",
                "jobs",
                "quote_line_items",
                "quotes",
                "bills_of_quantities",
                "boq_line_items",
                "contacts",
                "users",
            ]:
                conn.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                )
            conn.execute(
                text("DELETE FROM tenants WHERE id = :tenant_id"),
                {"tenant_id": tenant_id},
            )

    # Delete the Django superuser if it exists.
    user_model = get_user_model()
    django_username = os.environ.get("E2E_DJANGO_ADMIN_USERNAME", "e2e-superadmin")
    deleted, _ = user_model.objects.filter(username=django_username).delete()
    if deleted:
        print(f"Deleted Django superuser: {django_username}")
    else:
        print(f"Django superuser not found: {django_username}")

    print("Cleanup complete")


if __name__ == "__main__":
    clean()
