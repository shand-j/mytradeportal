"""Bootstrap a tenant and admin user for LOCAL DEVELOPMENT only.

This is a convenience script for spinning up a local dev environment. It is
not a production provisioning path: the script refuses to run when
ENVIRONMENT=production. In production, create the first tenant via
``POST /tenants`` gated by ``SETUP_TOKEN`` (see docs/deployment.md).

Required environment variables (no defaults are provided — the seed must not
bake in credentials):

- ``SEED_TENANT_SLUG`` — tenant slug.
- ``SEED_TENANT_NAME`` — tenant display name.
- ``SEED_ADMIN_EMAIL`` — login email for the seeded admin user.
- ``SEED_ADMIN_PASSWORD`` — password for the seeded admin user (never printed).
- ``SEED_ADMIN_NAME`` — admin full name.
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine
from app.models import Base, Tenant, User
from app.rls import bypass_rls_in_session
from app.security import get_password_hash
from app.supabase import admin_create_user, is_supabase_configured
from app.utils.tenant_code import generate_unique_tenant_code


def _require_env(name: str) -> str:
    """Return a required environment variable or fail fast with a clear message."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} must be set to run this seed script; no default credentials are provided"
        )
    return value


async def seed() -> None:
    """Create the tenant and admin user if they do not already exist."""
    if settings.environment == "production":
        raise RuntimeError("This seed script must not be run in production")

    tenant_slug = _require_env("SEED_TENANT_SLUG")
    tenant_name = _require_env("SEED_TENANT_NAME")
    admin_email = _require_env("SEED_ADMIN_EMAIL")
    admin_password = _require_env("SEED_ADMIN_PASSWORD")
    admin_name = _require_env("SEED_ADMIN_NAME")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        # Seed scripts legitimately cross tenant boundaries: opt out of RLS
        # explicitly for this connection so the User insert can supply any
        # tenant_id without depending on app.current_tenant being set.
        await bypass_rls_in_session(session)
        tenant_result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            tenant_code = await generate_unique_tenant_code(session)
            tenant = Tenant(slug=tenant_slug, code=tenant_code, name=tenant_name)
            session.add(tenant)
            await session.flush()
            await session.refresh(tenant)
            print(
                f"Created tenant: {tenant.name} ({tenant.slug}) — code={tenant.code} — id={tenant.id}"
            )
        else:
            print(f"Tenant already exists: {tenant.slug}")

        user_result = await session.execute(
            select(User).where(User.email == admin_email, User.tenant_id == tenant.id)
        )
        user = user_result.scalar_one_or_none()
        supabase_uid: str | None = None
        password_hash: str | None = None

        if is_supabase_configured():
            try:
                sb_user = admin_create_user(admin_email, admin_password)
                supabase_uid = sb_user.get("id")
                print(f"Created Supabase auth user: {supabase_uid}")
            except RuntimeError as exc:
                # The user may already exist in Supabase; try to fetch by email.
                import httpx

                with httpx.Client() as client:
                    response = client.get(
                        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
                        params={"email": admin_email},
                        headers={
                            "apikey": settings.supabase_service_role_key,
                            "Authorization": f"Bearer {settings.supabase_service_role_key}",
                        },
                    )
                    if response.status_code == 200:
                        users = response.json().get("users", [])
                        if users:
                            supabase_uid = users[0]["id"]
                            print(f"Linked existing Supabase auth user: {supabase_uid}")
                        else:
                            raise exc
                    else:
                        raise exc
        else:
            password_hash = get_password_hash(admin_password)

        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=admin_email,
                full_name=admin_name,
                role="admin",
                password_hash=password_hash,
                supabase_uid=supabase_uid,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            print(f"Created admin user: {user.email} / role={user.role}")
        else:
            # Ensure the existing user is linked to Supabase if we just created one.
            if supabase_uid and not user.supabase_uid:
                user.supabase_uid = supabase_uid
                await session.commit()
                print(f"Linked admin user to Supabase: {user.email}")
            else:
                print(f"Admin user already exists: {user.email}")

        print("\nSeed complete.")
        print(f"  Tenant slug: {tenant.slug}")
        print(f"  Tenant code: {tenant.code or 'N/A'}")
        print(f"  Admin email: {admin_email}")


if __name__ == "__main__":
    asyncio.run(seed())
