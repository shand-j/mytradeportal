"""Tests for persistent notifications (staff + customer) and push tokens."""

from uuid import UUID, uuid4

import pytest
from app.models import Notification, PushToken, Tenant
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _seed_notification(db: AsyncSession, tenant_id: UUID, **kwargs: object) -> Notification:
    await set_tenant_in_session(db, tenant_id)
    notification = Notification(tenant_id=tenant_id, **kwargs)
    db.add(notification)
    await db.flush()
    return notification


def _staff_notification_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "recipient_type": "staff",
        "recipient_id": None,
        "type": "quote_ready",
        "title": "Quote ready for review",
        "body": "AI draft quote 'Rewire' is ready for your review.",
        "link": "/quotes/123",
    }
    kwargs.update(overrides)
    return kwargs


async def test_staff_list_read_and_unread_count(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    visible = await _seed_notification(db, tenant_id, **_staff_notification_kwargs())
    # Addressed to a different staff user → invisible to the current user.
    other_user = await _seed_notification(
        db, tenant_id, **_staff_notification_kwargs(recipient_id=uuid4())
    )
    # Customer notifications never appear in the staff list.
    await _seed_notification(
        db,
        tenant_id,
        **_staff_notification_kwargs(recipient_type="customer", recipient_id=uuid4()),
    )

    resp = await admin_client.get("/notifications")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [row["id"] for row in rows] == [str(visible.id)]
    assert rows[0]["recipient_type"] == "staff"
    assert rows[0]["type"] == "quote_ready"
    assert rows[0]["link"] == "/quotes/123"
    assert rows[0]["read_at"] is None

    count = await admin_client.get("/notifications/unread-count")
    assert count.status_code == 200
    assert count.json() == {"unread_count": 1}

    patch = await admin_client.patch(f"/notifications/{visible.id}/read")
    assert patch.status_code == 200, patch.text
    assert patch.json()["read_at"] is not None

    count = await admin_client.get("/notifications/unread-count")
    assert count.json() == {"unread_count": 0}

    # A notification addressed to another staff user cannot be read → 404.
    patch = await admin_client.patch(f"/notifications/{other_user.id}/read")
    assert patch.status_code == 404


async def test_staff_notifications_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/notifications")
    assert resp.status_code == 401


async def test_tenant_isolation(admin_client: AsyncClient, db: AsyncSession) -> None:
    """Another tenant's notifications are invisible to staff endpoints."""
    own = await _seed_notification(
        db, UUID(admin_client.headers["X-Tenant-ID"]), **_staff_notification_kwargs()
    )

    created = await admin_client.post(
        "/tenants", json={"slug": f"other-{uuid4().hex[:8]}", "name": "Other Ltd"}
    )
    assert created.status_code == 201
    other_tenant_id = UUID(created.json()["id"])
    foreign = await _seed_notification(db, other_tenant_id, **_staff_notification_kwargs())

    resp = await admin_client.get("/notifications")
    assert resp.status_code == 200
    assert [row["id"] for row in resp.json()] == [str(own.id)]

    count = await admin_client.get("/notifications/unread-count")
    assert count.json() == {"unread_count": 1}

    patch = await admin_client.patch(f"/notifications/{foreign.id}/read")
    assert patch.status_code == 404


async def _register_customer(
    client: AsyncClient, db: AsyncSession, tenant_id: UUID
) -> tuple[dict[str, str], str]:
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    email = f"jane-{uuid4().hex[:6]}@example.com"
    resp = await client.post(
        "/customer/register",
        json={
            "slug": tenant.slug,
            "full_name": "Homeowner Jane",
            "email": email,
            "phone": "07700 900888",
            "password": "homeowner-pass-123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['accessToken']}"}, body["customer"]["id"]


async def test_customer_list_read_and_unread_count(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    auth, customer_id = await _register_customer(admin_client, db, tenant_id)

    visible = await _seed_notification(
        db,
        tenant_id,
        recipient_type="customer",
        recipient_id=UUID(customer_id),
        type="quote_ready",
        title="Your quote is ready",
        body="Your quote 'Rewire' is ready to view.",
        link="/quotes/123",
    )
    # Another customer's notification → invisible.
    other = await _seed_notification(
        db,
        tenant_id,
        recipient_type="customer",
        recipient_id=uuid4(),
        type="quote_ready",
        title="Your quote is ready",
        body="...",
        link=None,
    )
    # Staff notifications never appear in the customer list.
    await _seed_notification(db, tenant_id, **_staff_notification_kwargs())

    resp = await admin_client.get("/customer/notifications", headers=auth)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [row["id"] for row in rows] == [str(visible.id)]
    assert rows[0]["recipient_type"] == "customer"
    assert rows[0]["read_at"] is None

    count = await admin_client.get("/customer/notifications/unread-count", headers=auth)
    assert count.json() == {"unread_count": 1}

    patch = await admin_client.patch(f"/customer/notifications/{visible.id}/read", headers=auth)
    assert patch.status_code == 200, patch.text
    assert patch.json()["read_at"] is not None

    count = await admin_client.get("/customer/notifications/unread-count", headers=auth)
    assert count.json() == {"unread_count": 0}

    # Another customer's notification cannot be read → 404.
    patch = await admin_client.patch(f"/customer/notifications/{other.id}/read", headers=auth)
    assert patch.status_code == 404


async def test_push_token_upsert(admin_client: AsyncClient, db: AsyncSession) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])

    first = await admin_client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[abc123]", "platform": "ios"},
    )
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["owner_type"] == "staff"
    assert first_body["platform"] == "ios"

    # Re-registering the same token updates the existing row instead of
    # violating the unique constraint.
    second = await admin_client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[abc123]", "platform": "android"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first_body["id"]
    assert second.json()["platform"] == "android"

    await set_tenant_in_session(db, tenant_id)
    count = await db.scalar(
        select(func.count(PushToken.id)).where(PushToken.tenant_id == tenant_id)
    )
    assert count == 1


async def test_upsert_push_token_repoints_row_hidden_by_rls(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Direct regression test for the prod 500: the existence check must see
    another tenant's row despite RLS.

    Exercises ``_upsert_push_token`` against the raw session (no HTTP request
    first) because the test harness shares one top-level transaction, where a
    transaction-local RLS bypass from any earlier bypassing endpoint (login,
    tenant bootstrap) would leak and mask the bug.
    """
    from app.routers.notifications import _upsert_push_token
    from app.schemas import PushTokenCreate

    tenant_a = Tenant(slug=f"a-{uuid4().hex[:8]}", name="A Ltd")
    tenant_b = Tenant(slug=f"b-{uuid4().hex[:8]}", name="B Ltd")
    db.add_all([tenant_a, tenant_b])
    await db.flush()

    # The device registered its token under tenant A previously.
    await set_tenant_in_session(db, tenant_a.id)
    existing = PushToken(
        tenant_id=tenant_a.id,
        owner_type="staff",
        owner_id=uuid4(),
        token="ExponentPushToken[rls-hidden]",
        platform="ios",
    )
    db.add(existing)
    await db.commit()

    # The same device now registers under tenant B. Under RLS the SELECT
    # cannot see tenant A's row; without the cross-tenant lookup the INSERT
    # violates the global unique constraint and the request 500s.
    await set_tenant_in_session(db, tenant_b.id)
    row = await _upsert_push_token(
        db,
        tenant_b.id,
        "staff",
        uuid4(),
        PushTokenCreate(token="ExponentPushToken[rls-hidden]", platform="android"),
    )

    assert row.id == existing.id
    assert row.tenant_id == tenant_b.id
    assert row.platform == "android"

    # One row globally, now owned by tenant B.
    count_b = await db.scalar(
        select(func.count(PushToken.id)).where(PushToken.tenant_id == tenant_b.id)
    )
    assert count_b == 1
    await set_tenant_in_session(db, tenant_a.id)
    count_a = await db.scalar(
        select(func.count(PushToken.id)).where(PushToken.tenant_id == tenant_a.id)
    )
    assert count_a == 0


async def test_upsert_push_token_sequential_reregister_is_idempotent(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Double-registering the same token under one tenant keeps a single row."""
    from app.routers.notifications import _upsert_push_token
    from app.schemas import PushTokenCreate

    tenant = Tenant(slug=f"t-{uuid4().hex[:8]}", name="T Ltd")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)

    owner = uuid4()
    first = await _upsert_push_token(
        db,
        tenant.id,
        "staff",
        owner,
        PushTokenCreate(token="ExponentPushToken[dup]", platform="ios"),
    )
    second = await _upsert_push_token(
        db,
        tenant.id,
        "staff",
        owner,
        PushTokenCreate(token="ExponentPushToken[dup]", platform="android"),
    )

    assert second.id == first.id
    assert second.platform == "android"
    count = await db.scalar(
        select(func.count(PushToken.id)).where(PushToken.tenant_id == tenant.id)
    )
    assert count == 1


async def test_push_token_repoints_across_tenants(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A token registered under tenant A re-registers under tenant B without a 500.

    Regression test: the RLS tenant policy hid tenant A's row from the SELECT,
    so the INSERT violated the global unique constraint on ``token``.
    """
    tenant_a = UUID(admin_client.headers["X-Tenant-ID"])

    # Seed the device token under tenant A directly (as if a previous
    # registration had happened while the device was logged into A).
    await set_tenant_in_session(db, tenant_a)
    existing = PushToken(
        tenant_id=tenant_a,
        owner_type="staff",
        owner_id=uuid4(),
        token="ExponentPushToken[cross-tenant]",
        platform="ios",
    )
    db.add(existing)
    await db.flush()

    # Bootstrap tenant B with its own staff admin and log in as them.
    slug = f"other-{uuid4().hex[:8]}"
    created = await admin_client.post(
        "/tenants",
        json={
            "slug": slug,
            "name": "Other Ltd",
            "admin_email": f"admin@{slug}.example.com",
            "admin_password": "bootstrap-pass-123",
            "admin_name": "Other Admin",
        },
    )
    assert created.status_code == 201, created.text
    tenant_b = UUID(created.json()["id"])
    login = await admin_client.post(
        "/auth/login",
        json={
            "email": f"admin@{slug}.example.com",
            "password": "bootstrap-pass-123",
            "tenant_slug": slug,
        },
    )
    assert login.status_code == 200, login.text

    # Re-register the SAME token as tenant B staff: must re-point, not 500.
    resp = await admin_client.post(
        "/notifications/push-token",
        headers={"X-Tenant-ID": str(tenant_b)},
        json={"token": "ExponentPushToken[cross-tenant]", "platform": "android"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(existing.id)
    assert body["tenant_id"] == str(tenant_b)
    assert body["platform"] == "android"

    # The row moved to tenant B; nothing remains under tenant A.
    await set_tenant_in_session(db, tenant_b)
    stored = await db.scalar(select(PushToken).where(PushToken.tenant_id == tenant_b))
    assert stored is not None
    assert stored.id == existing.id
    await set_tenant_in_session(db, tenant_a)
    count_a = await db.scalar(
        select(func.count(PushToken.id)).where(PushToken.tenant_id == tenant_a)
    )
    assert count_a == 0


async def test_customer_push_token_repoints_across_tenants(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """The customer endpoint shares the same cross-tenant re-point behavior."""
    tenant_a = UUID(admin_client.headers["X-Tenant-ID"])

    # Staff of tenant A registers the device token first.
    first = await admin_client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[shared-device]", "platform": "ios"},
    )
    assert first.status_code == 201, first.text

    # A customer of tenant B registers the same device token.
    created = await admin_client.post(
        "/tenants", json={"slug": f"other-{uuid4().hex[:8]}", "name": "Other Ltd"}
    )
    assert created.status_code == 201
    tenant_b = UUID(created.json()["id"])
    auth, customer_id = await _register_customer(admin_client, db, tenant_b)

    resp = await admin_client.post(
        "/customer/notifications/push-token",
        headers=auth,
        json={"token": "ExponentPushToken[shared-device]", "platform": "ios"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == first.json()["id"]
    assert body["tenant_id"] == str(tenant_b)
    assert body["owner_type"] == "customer"
    assert body["owner_id"] == customer_id

    await set_tenant_in_session(db, tenant_a)
    count_a = await db.scalar(
        select(func.count(PushToken.id)).where(PushToken.tenant_id == tenant_a)
    )
    assert count_a == 0


async def test_customer_push_token_upsert(admin_client: AsyncClient, db: AsyncSession) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    auth, customer_id = await _register_customer(admin_client, db, tenant_id)

    resp = await admin_client.post(
        "/customer/notifications/push-token",
        headers=auth,
        json={"token": "ExponentPushToken[customer1]", "platform": "ios"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["owner_type"] == "customer"
    assert body["owner_id"] == customer_id

    await set_tenant_in_session(db, tenant_id)
    stored = await db.scalar(select(PushToken).where(PushToken.tenant_id == tenant_id))
    assert stored is not None
    assert stored.owner_type == "customer"
    assert str(stored.owner_id) == customer_id


async def test_quote_ready_push_is_noop_without_tokens(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """send_expo_push returns immediately when there are no tokens."""
    from app.push import send_expo_push

    await send_expo_push([], "Title", "Body")  # must not raise or call out


async def test_customer_token_cannot_read_staff_notifications(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A customer bearer token is rejected by the staff notifications API."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    auth, _ = await _register_customer(admin_client, db, tenant_id)

    resp = await admin_client.get("/notifications", headers=auth)
    assert resp.status_code == 401


async def test_staff_user_cannot_read_customer_notifications(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A staff session is rejected by the customer notifications API."""
    await _seed_notification(
        db, UUID(admin_client.headers["X-Tenant-ID"]), **_staff_notification_kwargs()
    )
    # admin_client carries a staff cookie and no customer bearer token.
    resp = await admin_client.get("/customer/notifications")
    assert resp.status_code == 401


async def test_staff_mark_all_read(admin_client: AsyncClient, db: AsyncSession) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await _seed_notification(db, tenant_id, **_staff_notification_kwargs())
    # Addressed to a different staff user → must stay unread.
    other_user = await _seed_notification(
        db, tenant_id, **_staff_notification_kwargs(recipient_id=uuid4())
    )

    resp = await admin_client.post("/notifications/read-all")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"marked_read": 1}

    count = await admin_client.get("/notifications/unread-count")
    assert count.json() == {"unread_count": 0}

    await db.refresh(other_user)
    assert other_user.read_at is None

    # Idempotent: a second sweep marks nothing.
    resp = await admin_client.post("/notifications/read-all")
    assert resp.json() == {"marked_read": 0}


async def test_customer_mark_all_read(admin_client: AsyncClient, db: AsyncSession) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    auth, customer_id = await _register_customer(admin_client, db, tenant_id)
    for _ in range(2):
        await _seed_notification(
            db,
            tenant_id,
            recipient_type="customer",
            recipient_id=UUID(customer_id),
            type="quote_ready",
            title="Your quote is ready",
            body="...",
            link=None,
        )
    # Another customer's notification → must stay unread.
    other = await _seed_notification(
        db,
        tenant_id,
        recipient_type="customer",
        recipient_id=uuid4(),
        type="quote_ready",
        title="Your quote is ready",
        body="...",
        link=None,
    )

    resp = await admin_client.post("/customer/notifications/read-all", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"marked_read": 2}

    count = await admin_client.get("/customer/notifications/unread-count", headers=auth)
    assert count.json() == {"unread_count": 0}

    await db.refresh(other)
    assert other.read_at is None
