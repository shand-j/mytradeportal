"""Bootstrap a demo tenant and admin user for local development."""

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

DEFAULT_TENANT_SLUG = os.environ.get("SEED_TENANT_SLUG", "demo")
DEFAULT_TENANT_NAME = os.environ.get("SEED_TENANT_NAME", "Demo Electrical")
DEFAULT_ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@demo.local")
DEFAULT_ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "password123")
DEFAULT_ADMIN_NAME = os.environ.get("SEED_ADMIN_NAME", "Demo Admin")


async def seed() -> None:
    """Create the demo tenant and admin user if they do not already exist."""
    if settings.environment == "production":
        raise RuntimeError("This seed script must not be run in production")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        # Seed scripts legitimately cross tenant boundaries: opt out of RLS
        # explicitly for this connection so the User insert can supply any
        # tenant_id without depending on app.current_tenant being set.
        await bypass_rls_in_session(session)
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(slug=DEFAULT_TENANT_SLUG, name=DEFAULT_TENANT_NAME)
            session.add(tenant)
            await session.flush()
            await session.refresh(tenant)
            print(f"Created tenant: {tenant.name} ({tenant.slug}) — id={tenant.id}")
        else:
            print(f"Tenant already exists: {tenant.slug}")

        user_result = await session.execute(
            select(User).where(
                User.email == DEFAULT_ADMIN_EMAIL, User.tenant_id == tenant.id
            )
        )
        user = user_result.scalar_one_or_none()
        supabase_uid: str | None = None
        password_hash: str | None = None

        if is_supabase_configured():
            try:
                sb_user = admin_create_user(DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)
                supabase_uid = sb_user.get("id")
                print(f"Created Supabase auth user: {supabase_uid}")
            except RuntimeError as exc:
                # The user may already exist in Supabase; try to fetch by email.
                import httpx

                with httpx.Client() as client:
                    response = client.get(
                        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
                        params={"email": DEFAULT_ADMIN_EMAIL},
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
            password_hash = get_password_hash(DEFAULT_ADMIN_PASSWORD)

        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=DEFAULT_ADMIN_EMAIL,
                full_name=DEFAULT_ADMIN_NAME,
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

        print("\nLogin with:")
        print(f"  Tenant slug: {tenant.slug}")
        print(f"  Email:       {DEFAULT_ADMIN_EMAIL}")
        print(f"  Password:    {DEFAULT_ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
