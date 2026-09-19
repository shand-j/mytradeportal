"""Integration tests for staff team invites (POST /users/invite + accept)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest_asyncio
from app.models import Subscription, Tenant, User, UserInviteToken
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from sqlalchemy import select

if TYPE_CHECKING:
    import pytest
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(loop_scope="function")
async def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture invite emails instead of sending them (transport never called)."""
    emails: list[dict[str, Any]] = []

    async def fake_send_event_email(**kwargs: Any) -> bool:
        emails.append(kwargs)
        return True

    monkeypatch.setattr("app.routers.users.send_event_email", fake_send_event_email)
    return emails


def _token_from_email(email: dict[str, Any]) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", email["text_body"] or "")
    assert match, f"no invite link in email body: {email['text_body']!r}"
    return match.group(1)


async def _tenant_id(client: AsyncClient) -> str:
    response = await client.get("/auth/me")
    assert response.status_code == 200, response.text
    return str(response.json()["tenant_id"])


async def _subscribe(db: AsyncSession, tenant_id: str, plan_key: str = "pro") -> None:
    db.add(Subscription(tenant_id=tenant_id, plan_key=plan_key, status="active"))
    await db.commit()


async def test_invite_creates_pending_user_in_tenant(
    admin_client: AsyncClient, db: AsyncSession, sent_emails: list[dict[str, Any]]
) -> None:
    tenant_id = await _tenant_id(admin_client)
    await _subscribe(db, tenant_id)

    response = await admin_client.post(
        "/users/invite",
        json={"email": "sparky@test.local", "full_name": "Sam Spark", "role": "engineer"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["is_active"] is False
    assert body["invite_pending"] is True
    assert body["tenant_id"] == tenant_id

    user = await db.scalar(select(User).where(User.email == "sparky@test.local"))
    assert user is not None
    assert str(user.tenant_id) == tenant_id
    assert user.password_hash is None
    assert user.is_active is False
    assert user.invited_at is not None

    # The invite email went to the invitee with a set-password link.
    assert len(sent_emails) == 1
    assert sent_emails[0]["to_email"] == "sparky@test.local"
    assert "Test Electrical" in sent_emails[0]["subject"]
    _token_from_email(sent_emails[0])

    # The pending invite shows up in the staff list for the tenant.
    listing = await admin_client.get("/users")
    assert listing.status_code == 200
    invites = {u["email"]: u for u in listing.json()}
    assert invites["sparky@test.local"]["invite_pending"] is True
    assert invites["admin@test.local"]["invite_pending"] is False


async def test_invite_enforces_seat_limit_default_plan(
    admin_client: AsyncClient, sent_emails: list[dict[str, Any]]
) -> None:
    """No subscription → sole_trader → 1 seat, already taken by the admin."""
    response = await admin_client.post(
        "/users/invite",
        json={"email": "extra@test.local", "full_name": "Extra Hand"},
    )
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["detail"] == "seat_limit_reached"
    assert detail["current_plan"] == "sole_trader"
    assert detail["seats"] == 1
    assert "Pro" in detail["upgrade_hint"]
    assert sent_emails == []


async def test_seat_limit_counts_pending_invites(
    admin_client: AsyncClient, db: AsyncSession, sent_emails: list[dict[str, Any]]
) -> None:
    """Pro (5 seats): admin + 4 pending invites fill the plan; the 5th 403s."""
    tenant_id = await _tenant_id(admin_client)
    await _subscribe(db, tenant_id, "pro")

    for i in range(4):
        response = await admin_client.post(
            "/users/invite",
            json={"email": f"hand{i}@test.local", "full_name": f"Hand {i}"},
        )
        assert response.status_code == 201, response.text

    response = await admin_client.post(
        "/users/invite",
        json={"email": "one-too-many@test.local", "full_name": "Too Many"},
    )
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["detail"] == "seat_limit_reached"
    assert detail["current_plan"] == "pro"
    assert detail["seats"] == 5
    assert "Team" in detail["upgrade_hint"]


async def test_invite_conflict_on_existing_email(
    admin_client: AsyncClient, db: AsyncSession, sent_emails: list[dict[str, Any]]
) -> None:
    tenant_id = await _tenant_id(admin_client)
    await _subscribe(db, tenant_id)
    response = await admin_client.post(
        "/users/invite",
        json={"email": "admin@test.local", "full_name": "Duplicate"},
    )
    assert response.status_code == 409, response.text


async def test_invite_requires_manager_role(
    client: AsyncClient, db: AsyncSession, admin_client: AsyncClient
) -> None:
    tenant_id = await _tenant_id(admin_client)
    tenant = await db.get(Tenant, UUID(tenant_id))
    assert tenant is not None

    await set_tenant_in_session(db, tenant.id)
    engineer = User(
        tenant_id=tenant.id,
        email="engineer@test.local",
        full_name="Eng Neer",
        role="engineer",
        password_hash=get_password_hash("engineer-password-123"),
        is_active=True,
    )
    db.add(engineer)
    await db.commit()

    login = await client.post(
        "/auth/login",
        json={
            "email": "engineer@test.local",
            "password": "engineer-password-123",
            "tenant_slug": tenant.slug,
        },
    )
    assert login.status_code == 200, login.text
    response = await client.post(
        "/users/invite",
        json={"email": "nope@test.local", "full_name": "Nope"},
    )
    assert response.status_code == 403, response.text


async def _invite_and_get_token(
    admin_client: AsyncClient,
    db: AsyncSession,
    sent_emails: list[dict[str, Any]],
    email: str = "newbie@test.local",
) -> str:
    tenant_id = await _tenant_id(admin_client)
    if await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id)) is None:
        await _subscribe(db, tenant_id)
    sent_emails.clear()
    response = await admin_client.post(
        "/users/invite", json={"email": email, "full_name": "New Bee"}
    )
    assert response.status_code == 201, response.text
    assert len(sent_emails) == 1
    return _token_from_email(sent_emails[0])


async def test_magic_link_request_reissues_and_revokes(
    admin_client: AsyncClient, db: AsyncSession, sent_emails: list[dict[str, Any]]
) -> None:
    first_token = await _invite_and_get_token(admin_client, db, sent_emails)

    # Unknown emails get the same generic response (no enumeration).
    response = await admin_client.post(
        "/users/invite/magic-link", json={"email": "ghost@test.local"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["detail"].startswith("If that email")
    assert len(sent_emails) == 1  # nothing new sent

    # A pending invite gets a fresh link; the earlier token is revoked.
    response = await admin_client.post(
        "/users/invite/magic-link", json={"email": "newbie@test.local"}
    )
    assert response.status_code == 200, response.text
    assert len(sent_emails) == 2
    second_token = _token_from_email(sent_emails[1])
    assert second_token != first_token

    stale = await admin_client.post(
        "/users/accept-invite", json={"token": first_token, "password": "password-123"}
    )
    assert stale.status_code == 401, stale.text

    fresh = await admin_client.post(
        "/users/accept-invite", json={"token": second_token, "password": "password-123"}
    )
    assert fresh.status_code == 200, fresh.text


async def test_accept_invite_activates_and_password_login_works(
    admin_client: AsyncClient,
    client: AsyncClient,
    db: AsyncSession,
    sent_emails: list[dict[str, Any]],
) -> None:
    token = await _invite_and_get_token(admin_client, db, sent_emails)

    # Before acceptance the account cannot log in (inactive, no password).
    early = await client.post(
        "/auth/token", json={"email": "newbie@test.local", "password": "password-123"}
    )
    assert early.status_code == 401, early.text

    accepted = await client.post(
        "/users/accept-invite",
        json={"token": token, "password": "password-123"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["email"] == "newbie@test.local"

    user = await db.scalar(select(User).where(User.email == "newbie@test.local"))
    assert user is not None
    assert user.is_active is True
    assert user.invited_at is None
    assert user.invite_pending is False
    assert user.password_hash is not None

    # The token is single-use.
    replay = await client.post(
        "/users/accept-invite", json={"token": token, "password": "password-123"}
    )
    assert replay.status_code == 401, replay.text

    # Garbage tokens fail identically (no oracle on token existence).
    garbage = await client.post(
        "/users/accept-invite",
        json={"token": "x" * 43, "password": "password-123"},
    )
    assert garbage.status_code == 401, garbage.text
    assert garbage.json() == replay.json()

    # Email + new password now authenticate.
    login = await client.post(
        "/auth/token", json={"email": "newbie@test.local", "password": "password-123"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


async def test_accept_frees_the_seat(
    admin_client: AsyncClient,
    client: AsyncClient,
    db: AsyncSession,
    sent_emails: list[dict[str, Any]],
) -> None:
    """sole_trader has 1 seat; accepting an invite leaves the count consistent."""
    tenant_id = await _tenant_id(admin_client)
    await _subscribe(db, tenant_id, "pro")
    token = await _invite_and_get_token(admin_client, db, sent_emails)
    accepted = await client.post(
        "/users/accept-invite", json={"token": token, "password": "password-123"}
    )
    assert accepted.status_code == 200, accepted.text
    # The accepted user is active and still holds a seat: 2 of 5 used, so
    # three more invites fit but a fourth fails.
    for i in range(3):
        response = await admin_client.post(
            "/users/invite", json={"email": f"f{i}@test.local", "full_name": f"F {i}"}
        )
        assert response.status_code == 201, response.text
    response = await admin_client.post(
        "/users/invite", json={"email": "overflow@test.local", "full_name": "Over Flow"}
    )
    assert response.status_code == 403, response.text


async def test_invites_are_tenant_isolated(
    admin_client: AsyncClient,
    client: AsyncClient,
    db: AsyncSession,
    sent_emails: list[dict[str, Any]],
) -> None:
    """Tenant B never sees tenant A's invite and can invite the same email."""
    await _invite_and_get_token(admin_client, db, sent_emails, email="shared@test.local")

    # Build a second tenant with its own admin and pro subscription.
    tenant_b = Tenant(slug=f"test-{uuid4().hex[:8]}", name="Other Electrical")
    db.add(tenant_b)
    await db.flush()
    await set_tenant_in_session(db, tenant_b.id)
    admin_b = User(
        tenant_id=tenant_b.id,
        email="admin-b@test.local",
        full_name="B Admin",
        role="admin",
        password_hash=get_password_hash("b-password-123"),
        is_active=True,
    )
    db.add(admin_b)
    db.add(Subscription(tenant_id=tenant_b.id, plan_key="pro", status="active"))
    await db.commit()

    # Switch identity: drop tenant A's session cookie and tenant header.
    client.cookies.clear()
    client.headers.pop("X-Tenant-ID", None)
    login = await client.post(
        "/auth/login",
        headers={"host": f"{tenant_b.slug}.localhost"},
        json={"email": "admin-b@test.local", "password": "b-password-123"},
    )
    assert login.status_code == 200, login.text
    client.headers["X-Tenant-ID"] = str(tenant_b.id)

    listing = await client.get("/users")
    assert listing.status_code == 200, listing.text
    emails = {u["email"] for u in listing.json()}
    assert emails == {"admin-b@test.local"}

    # The same email can be invited into tenant B — a separate user row.
    invited = await client.post(
        "/users/invite", json={"email": "shared@test.local", "full_name": "Shared Mailbox"}
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["tenant_id"] == str(tenant_b.id)

    # Tenant B's invite token points at tenant B's brand-new user only.
    b_user = await db.scalar(
        select(User).where(User.email == "shared@test.local", User.tenant_id == tenant_b.id)
    )
    assert b_user is not None
    b_token_rows = await db.execute(
        select(UserInviteToken).where(UserInviteToken.user_id == b_user.id)
    )
    assert len(b_token_rows.scalars().all()) == 1
