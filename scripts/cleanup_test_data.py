import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from data_pipeline.config import settings

url = settings.database_url
engine = create_async_engine(url)

TENANT_SCOPED_TABLES = (
    "users", "contacts", "quotes", "quote_line_items", "bills_of_quantities",
    "boq_line_items", "jobs", "appointments", "invoices", "invoice_line_items",
    "payments", "communications", "reviews", "audit_logs",
)

RLS_TEST_EMAILS = ("rls-test@example.com", "rls-test2@example.com", "rls-test3@example.com")


async def main() -> None:
    async with engine.begin() as conn:
        tenant_rows = (await conn.execute(
            text("SELECT id, slug FROM tenants WHERE slug LIKE 'ai-quote-test-%' OR slug LIKE 'admin-onboard-%' OR slug LIKE 'debug-test-%'")
        )).all()
        tenant_ids = [str(row[0]) for row in tenant_rows]
        print("Test tenants to remove:", tenant_rows)

        rls_contacts = (await conn.execute(
            text("SELECT id, tenant_id, name, email FROM contacts WHERE email = ANY(:emails)"),
            {"emails": list(RLS_TEST_EMAILS)},
        )).all()
        print("RLS test contacts to remove:", rls_contacts)

        if not tenant_ids and not rls_contacts:
            print("Nothing to clean")
            await engine.dispose()
            return

        # Disable FK triggers for this transaction so deletes can proceed in any order.
        await conn.execute(text("SET session_replication_role = replica"))

        if tenant_ids:
            for table in TENANT_SCOPED_TABLES:
                result = await conn.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id::text = ANY(:tenant_ids)"),
                    {"tenant_ids": tenant_ids},
                )
                print(f"Deleted {result.rowcount} rows from {table}")
            result = await conn.execute(
                text("DELETE FROM tenants WHERE id::text = ANY(:tenant_ids)"),
                {"tenant_ids": tenant_ids},
            )
            print(f"Deleted {result.rowcount} rows from tenants")

        if rls_contacts:
            result = await conn.execute(
                text("DELETE FROM contacts WHERE email = ANY(:emails)"),
                {"emails": list(RLS_TEST_EMAILS)},
            )
            print(f"Deleted {result.rowcount} RLS test contacts")

        await conn.execute(text("SET session_replication_role = DEFAULT"))

    await engine.dispose()


asyncio.run(main())
