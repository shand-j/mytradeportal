"""Tests for account claiming and the "app" contact-preference flip.

The claim endpoint (POST /customer/auth/claim) turns an auto-provisioned
passwordless customer account into a full login account: the emailed
magic-link token proves inbox ownership, the customer chooses a password,
and the CRM contact's preferred contact method flips to "app" (app first,
email too). The same flip happens when a customer registers a push token —
the other strong 'has the app' signal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from app.models import Contact, Customer, CustomerPortalToken, Tenant
from app.portal_links import hash_portal_token, issue_portal_token
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.security import get_password_hash
from sqlalchemy import select, update

from tests.test_portal_auth import _exchange

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    tenant = Tenant(slug=slug, name=f"{slug} Electrical")
    db.add(tenant)
    await db.flush()
    return tenant


async def _create_customer(
    db: AsyncSession,
    tenant: Tenant,
    email: str,
    *,
    password: str | None = None,
    preferred: str | None = None,
) -> Customer:
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(
        tenant_id=tenant.id,
        name="Claim Casey",
        email=email,
        preferred_contact_method=preferred,
    )
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=email,
        full_name="Claim Casey",
        password_hash=get_password_hash(password) if password else None,
    )
    db.add(customer)
    await db.flush()
    return customer


async def _claim(
    client: AsyncClient, raw_token: str, password: str = "new-password-123", **kwargs: Any
) -> Any:
    return await client.post(
        "/customer/auth/claim",
        json={"token": raw_token, "password": password},
        **kwargs,
    )


async def _refresh_contact(db: AsyncSession, customer: Customer) -> Contact:
    await bypass_rls_in_session(db)
    assert customer.contact_id is not None
    contact = await db.get(Contact, customer.contact_id)
    assert contact is not None
    return contact


async def test_claim_round_trip(client: AsyncClient, db: AsyncSession) -> None:
    """Token → password set → JWT works → password login works → preference app."""
    slug = f"claim-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"casey-{uuid4().hex[:6]}@example.com"
    customer = await _create_customer(db, tenant, email, preferred="email")
    raw = await issue_portal_token(db, customer)
    await db.commit()

    resp = await _claim(client, raw, headers={"host": f"{slug}.localhost"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["customer"]["id"] == str(customer.id)
    assert body["customer"]["full_name"] == "Claim Casey"
    assert body["customer"]["email"] == email
    assert body["expires_at"]

    # The returned JWT authenticates against the customer API.
    me = await client.get(
        "/customer/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == email

    # And the chosen password now works on the normal customer login.
    login = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email, "password": "new-password-123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["accessToken"]

    # Claiming flips the contact preference to "app" on both records.
    contact = await _refresh_contact(db, customer)
    assert contact.preferred_contact_method == "app"
    await db.refresh(customer)
    assert customer.preferred_contact_method == "app"

    # One claim per token: the row is revoked, so a replay fails like any
    # invalid token.
    await bypass_rls_in_session(db)
    record = await db.scalar(
        select(CustomerPortalToken).where(CustomerPortalToken.token_hash == hash_portal_token(raw))
    )
    assert record is not None
    assert record.revoked_at is not None
    replay = await _claim(client, raw, headers={"host": f"{slug}.localhost"})
    assert replay.status_code == 401


async def test_claim_used_expired_unknown_uniform_401(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"claim-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    customer = await _create_customer(db, tenant, f"casey-{uuid4().hex[:6]}@example.com")

    used_raw = await issue_portal_token(db, customer)
    await db.execute(
        update(CustomerPortalToken)
        .where(CustomerPortalToken.token_hash == hash_portal_token(used_raw))
        .values(revoked_at=datetime.now(UTC))
    )
    expired_raw = await issue_portal_token(db, customer)
    await db.execute(
        update(CustomerPortalToken)
        .where(CustomerPortalToken.token_hash == hash_portal_token(expired_raw))
        .values(revoked_at=None, expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db.commit()

    unknown = await _claim(client, "not-a-real-token")
    used = await _claim(client, used_raw)
    expired = await _claim(client, expired_raw)
    assert unknown.status_code == 401
    assert used.status_code == 401
    assert expired.status_code == 401
    assert unknown.json() == used.json() == expired.json()


async def test_claim_rejected_on_wrong_tenant_subdomain(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug_a = f"claim-{uuid4().hex[:8]}"
    tenant_a = await _create_tenant(db, slug_a)
    customer = await _create_customer(db, tenant_a, f"casey-{uuid4().hex[:6]}@example.com")
    slug_b = f"claim-{uuid4().hex[:8]}"
    await _create_tenant(db, slug_b)
    raw = await issue_portal_token(db, customer)
    await db.commit()

    wrong = await _claim(client, raw, headers={"host": f"{slug_b}.localhost"})
    assert wrong.status_code == 401
    right = await _claim(client, raw, headers={"host": f"{slug_a}.localhost"})
    assert right.status_code == 200, right.text


async def test_claim_short_password_422(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"claim-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    customer = await _create_customer(db, tenant, f"casey-{uuid4().hex[:6]}@example.com")
    raw = await issue_portal_token(db, customer)
    await db.commit()

    resp = await _claim(client, raw, password="short")
    assert resp.status_code == 422
    # Detail names the failing field so the portal client can show it inline.
    detail = resp.json()["detail"]
    assert any("password" in str(error.get("loc", "")) for error in detail)

    # A rejected validation must not consume the token.
    ok = await _claim(client, raw)
    assert ok.status_code == 200, ok.text


async def test_claim_reclaim_for_customer_with_password(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A customer who already has a password can still claim: the token is
    proof of inbox ownership, so the claim doubles as a verified reset."""
    slug = f"claim-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"casey-{uuid4().hex[:6]}@example.com"
    customer = await _create_customer(db, tenant, email, password="old-password-123")
    raw = await issue_portal_token(db, customer)
    await db.commit()

    resp = await _claim(client, raw, password="reset-password-456")
    assert resp.status_code == 200, resp.text

    login = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email, "password": "reset-password-456"},
    )
    assert login.status_code == 200, login.text
    stale = await client.post(
        "/customer/login",
        json={"slug": slug, "email": email, "password": "old-password-123"},
    )
    assert stale.status_code == 401


async def test_customer_push_token_registration_flips_preference_to_app(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Registering a customer push token (first app login) flips the contact
    preference to "app" — the strongest 'has the app' signal."""
    slug = f"claim-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    email = f"casey-{uuid4().hex[:6]}@example.com"
    customer = await _create_customer(db, tenant, email, preferred="email")
    raw = await issue_portal_token(db, customer)
    await db.commit()

    # Sign in via the magic exchange (which does not itself flip preferences).
    exchange = await _exchange(client, raw)
    assert exchange.status_code == 200, exchange.text
    auth = {"Authorization": f"Bearer {exchange.json()['access_token']}"}

    contact = await _refresh_contact(db, customer)
    assert contact.preferred_contact_method == "email"

    register = await client.post(
        "/customer/notifications/push-token",
        headers=auth,
        json={"token": f"ExponentPushToken[{uuid4().hex}]", "platform": "ios"},
    )
    assert register.status_code == 201, register.text

    contact = await _refresh_contact(db, customer)
    assert contact.preferred_contact_method == "app"
    await db.refresh(customer)
    assert customer.preferred_contact_method == "app"
