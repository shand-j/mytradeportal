"""End-to-end tests that verify tenant isolation cannot be bypassed.

These tests exercise multiple layers of defence:

1. **JWT vs X-Tenant-ID** — a user authenticated for tenant A must not be
   able to act on tenant B just by flipping the ``X-Tenant-ID`` header.
2. **RLS policies** — even raw SQL run on the same connection cannot read
   another tenant's rows once ``app.current_tenant`` has been set.
3. **API behaviour** — listing endpoints and direct GETs never leak rows
   from another tenant.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.models import Contact, Tenant, User
from app.rls import bypass_rls_in_session, clear_rls_session, set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_tenant_with_admin(
    db: AsyncSession, slug: str, email: str, password: str = "admin-password-123"
) -> tuple[Tenant, User]:
    tenant = Tenant(slug=slug, name=f"{slug.title()} Electrical")
    db.add(tenant)
    await db.flush()
    # Switch the session into this tenant before inserting rows that the
    # RLS policy applies to.
    await set_tenant_in_session(db, tenant.id)
    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name=f"{slug} admin",
        role="admin",
        password_hash=get_password_hash(password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(user)
    return tenant, user


@pytest.mark.asyncio
async def test_cross_tenant_header_swap_is_rejected(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A user logged in to tenant A cannot act on tenant B by changing X-Tenant-ID."""
    tenant_a, user_a = await _create_tenant_with_admin(
        db, slug=f"a-{uuid4().hex[:6]}", email="a@example.com"
    )
    tenant_b, _user_b = await _create_tenant_with_admin(
        db, slug=f"b-{uuid4().hex[:6]}", email="b@example.com"
    )

    # Log in as tenant A's admin via tenant A's subdomain.
    response = await client.post(
        "/auth/login",
        headers={"host": f"{tenant_a.slug}.localhost"},
        json={"email": user_a.email, "password": "admin-password-123"},
    )
    assert response.status_code == 200

    # Sanity check: A's own tenant is reachable.
    ok = await client.get("/contacts", headers={"X-Tenant-ID": str(tenant_a.id)})
    assert ok.status_code == 200

    # Now flip the X-Tenant-ID header to tenant B. The JWT still claims tenant
    # A, so the request must be rejected with 403.
    cross = await client.get("/contacts", headers={"X-Tenant-ID": str(tenant_b.id)})
    assert cross.status_code == 403, cross.text


@pytest.mark.asyncio
async def test_listing_does_not_leak_other_tenants_rows(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A contact created for tenant A must not appear in tenant B's /contacts list."""
    tenant_a, user_a = await _create_tenant_with_admin(
        db, slug=f"a-{uuid4().hex[:6]}", email="a@example.com"
    )
    tenant_b, user_b = await _create_tenant_with_admin(
        db, slug=f"b-{uuid4().hex[:6]}", email="b@example.com"
    )

    # Insert a contact for tenant A directly via the DB.
    await set_tenant_in_session(db, tenant_a.id)
    contact_a = Contact(tenant_id=tenant_a.id, name="Alice (tenant A)", email="alice@a.test")
    db.add(contact_a)
    await db.commit()

    # Log in as tenant B and list contacts: must not see Alice.
    login = await client.post(
        "/auth/login",
        headers={"host": f"{tenant_b.slug}.localhost"},
        json={"email": user_b.email, "password": "admin-password-123"},
    )
    assert login.status_code == 200

    listing = await client.get(
        "/contacts", headers={"X-Tenant-ID": str(tenant_b.id)}
    )
    assert listing.status_code == 200
    body = listing.json()
    names = [c.get("name") for c in body]
    assert "Alice (tenant A)" not in names


@pytest.mark.asyncio
async def test_get_other_tenant_contact_returns_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Direct GET on another tenant's contact must return 404, not the row."""
    tenant_a, _user_a = await _create_tenant_with_admin(
        db, slug=f"a-{uuid4().hex[:6]}", email="a@example.com"
    )
    tenant_b, user_b = await _create_tenant_with_admin(
        db, slug=f"b-{uuid4().hex[:6]}", email="b@example.com"
    )

    await set_tenant_in_session(db, tenant_a.id)
    contact_a = Contact(tenant_id=tenant_a.id, name="Alice", email="alice@a.test")
    db.add(contact_a)
    await db.commit()
    await db.refresh(contact_a)
    contact_a_id = contact_a.id

    login = await client.post(
        "/auth/login",
        headers={"host": f"{tenant_b.slug}.localhost"},
        json={"email": user_b.email, "password": "admin-password-123"},
    )
    assert login.status_code == 200

    response = await client.get(
        f"/contacts/{contact_a_id}",
        headers={"X-Tenant-ID": str(tenant_b.id)},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rls_blocks_raw_sql_cross_tenant_reads(db: AsyncSession) -> None:
    """RLS, not just application-layer filtering, hides cross-tenant rows.

    This is the database-layer defence: even if a future bug forgets to add
    ``WHERE tenant_id = :id`` to a query, the policy makes the rows invisible.
    """
    # Tenants table is not tenant-scoped, so create both tenants first.
    tenant_a = Tenant(slug=f"a-{uuid4().hex[:6]}", name="Tenant A")
    tenant_b = Tenant(slug=f"b-{uuid4().hex[:6]}", name="Tenant B")
    db.add_all([tenant_a, tenant_b])
    await db.flush()

    # Insert a contact for tenant A.
    await set_tenant_in_session(db, tenant_a.id)
    db.add(Contact(tenant_id=tenant_a.id, name="Alice"))
    await db.flush()

    # Insert a contact for tenant B.
    await set_tenant_in_session(db, tenant_b.id)
    db.add(Contact(tenant_id=tenant_b.id, name="Bob"))
    await db.flush()

    # Now switch the session to tenant A and run a NO-FILTER raw SQL query.
    await set_tenant_in_session(db, tenant_a.id)
    result = await db.execute(text("SELECT name FROM contacts ORDER BY name"))
    names = [row[0] for row in result.all()]
    assert "Alice" in names
    assert "Bob" not in names, "RLS failed: tenant B's contact leaked to tenant A"

    # Switching to tenant B reverses the visibility.
    await set_tenant_in_session(db, tenant_b.id)
    result = await db.execute(text("SELECT name FROM contacts ORDER BY name"))
    names = [row[0] for row in result.all()]
    assert "Bob" in names
    assert "Alice" not in names, "RLS failed: tenant A's contact leaked to tenant B"


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_inserts(db: AsyncSession) -> None:
    """An attempt to insert a row for another tenant must be rejected.

    Defends against an application bug that takes a tenant_id from the
    request body or query string instead of the authenticated context.
    """
    tenant_a = Tenant(slug=f"a-{uuid4().hex[:6]}", name="Tenant A")
    tenant_b = Tenant(slug=f"b-{uuid4().hex[:6]}", name="Tenant B")
    db.add_all([tenant_a, tenant_b])
    await db.flush()

    # Set session to tenant A but try to insert into tenant B.
    await set_tenant_in_session(db, tenant_a.id)
    db.add(Contact(tenant_id=tenant_b.id, name="Mallory"))
    with pytest.raises(DBAPIError):
        await db.flush()
    await db.rollback()


@pytest.mark.asyncio
async def test_bypass_rls_session_setting_works_for_admin_tasks(
    db: AsyncSession,
) -> None:
    """The explicit bypass setting lets seed/admin scripts cross tenants.

    Without bypass, an unset tenant means zero rows; with bypass, the same
    query returns all rows. This guarantees we have an audited escape hatch
    for cross-tenant maintenance tasks.
    """
    tenant_a = Tenant(slug=f"a-{uuid4().hex[:6]}", name="Tenant A")
    tenant_b = Tenant(slug=f"b-{uuid4().hex[:6]}", name="Tenant B")
    db.add_all([tenant_a, tenant_b])
    await db.flush()

    await set_tenant_in_session(db, tenant_a.id)
    db.add(Contact(tenant_id=tenant_a.id, name="Alice"))
    await db.flush()
    await set_tenant_in_session(db, tenant_b.id)
    db.add(Contact(tenant_id=tenant_b.id, name="Bob"))
    await db.flush()

    # Clear tenant context; without bypass we see nothing.
    await clear_rls_session(db)
    result = await db.execute(text("SELECT name FROM contacts"))
    assert result.all() == []

    # With bypass on we see everything.
    await bypass_rls_in_session(db)
    result = await db.execute(text("SELECT name FROM contacts ORDER BY name"))
    names = [row[0] for row in result.all()]
    assert "Alice" in names
    assert "Bob" in names
    await clear_rls_session(db)
