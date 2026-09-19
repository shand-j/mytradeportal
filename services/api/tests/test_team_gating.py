"""Team gating (issue #191): sole-staff auto-assignment and seat context.

Single-seat plans (sole_trader) have exactly one staff user, so assignment is
never a choice: job/appointment creation defaults ``assigned_user_id`` to the
tenant's only active user when none is supplied, while multi-staff tenants
keep explicit assignment (or none). ``GET /billing/subscription`` exposes the
plan's ``seats`` and the current ``seats_in_use`` so clients can gate
team-only UI.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from app.models import Subscription, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _me(client: AsyncClient) -> dict[str, Any]:
    response = await client.get("/auth/me")
    assert response.status_code == 200
    data: dict[str, Any] = response.json()
    return data


async def _create_contact(client: AsyncClient, tenant_id: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _add_user(db: AsyncSession, tenant_id: str, email: str, *, invited: bool = False) -> User:
    """Add a second staff user (active, or a pending invite) to the tenant."""
    await set_tenant_in_session(db, UUID(tenant_id))
    user = User(
        tenant_id=UUID(tenant_id),
        email=email,
        full_name=email.split("@")[0].replace(".", " ").title(),
        role="manager",
        password_hash=None if invited else get_password_hash("password-123"),
        is_active=not invited,
        invited_at=datetime.utcnow() if invited else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_single_user_tenant_job_auto_assigns(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A sole-staff tenant's job defaults to the only active user."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Auto Assign")

    response = await admin_client.post(
        "/jobs",
        json={"contact_id": contact["id"], "title": "Fuse board replacement"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["assigned_user_id"] == me["id"]
    assert data["assigned_to"] == me["full_name"]


async def test_single_user_tenant_appointment_auto_assigns(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Appointments get the same sole-staff default as jobs."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Auto Assign Appt")
    start = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0)

    response = await admin_client.post(
        "/appointments",
        json={
            "contact_id": contact["id"],
            "title": "Site visit",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["assigned_user_id"] == me["id"]


async def test_multi_user_tenant_job_defaults_unassigned(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """With two+ active users there is no implicit assignee."""
    me = await _me(admin_client)
    await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "No Default")

    response = await admin_client.post(
        "/jobs",
        json={"contact_id": contact["id"], "title": "Consumer unit"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["assigned_user_id"] is None
    assert data["assigned_to"] is None


async def test_multi_user_tenant_explicit_assignment_respected(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """An explicit assignee always wins over the default (job + appointment)."""
    me = await _me(admin_client)
    second = await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "Explicit Assign")

    job_response = await admin_client.post(
        "/jobs",
        json={
            "contact_id": contact["id"],
            "title": "EV charger",
            "assigned_user_id": str(second.id),
        },
    )
    assert job_response.status_code == 201, job_response.text
    assert job_response.json()["assigned_user_id"] == str(second.id)

    start = datetime.utcnow().replace(hour=11, minute=0, second=0, microsecond=0)
    appt_response = await admin_client.post(
        "/appointments",
        json={
            "contact_id": contact["id"],
            "title": "Follow-up visit",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "assigned_user_id": str(second.id),
        },
    )
    assert appt_response.status_code == 201, appt_response.text
    assert appt_response.json()["assigned_user_id"] == str(second.id)


async def test_appointment_rejects_foreign_or_inactive_assignee(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Appointment assignees are validated like job assignees."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Bad Assignee")
    start = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)

    response = await admin_client.post(
        "/appointments",
        json={
            "contact_id": contact["id"],
            "title": "Site visit",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "assigned_user_id": str(UUID(int=0)),
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid assignee"


async def test_subscription_read_exposes_seats_and_usage(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """GET /billing/subscription carries the plan seat cap and current usage."""
    me = await _me(admin_client)
    db.add(Subscription(tenant_id=UUID(me["tenant_id"]), plan_key="pro", status="active"))
    await db.commit()

    response = await admin_client.get("/billing/subscription")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["plan_key"] == "pro"
    assert data["seats"] == 5
    # Just the admin — pending invites would also hold a seat.
    assert data["seats_in_use"] == 1

    await _add_user(db, me["tenant_id"], "invited@test.local", invited=True)
    response = await admin_client.get("/billing/subscription")
    assert response.status_code == 200, response.text
    assert response.json()["seats_in_use"] == 2


async def test_subscription_read_resolves_legacy_plan_keys(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Beta-era plan keys map onto the catalog for the seat count."""
    me = await _me(admin_client)
    db.add(Subscription(tenant_id=UUID(me["tenant_id"]), plan_key="starter", status="active"))
    await db.commit()

    response = await admin_client.get("/billing/subscription")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["plan_key"] == "starter"
    # starter → sole_trader
    assert data["seats"] == 1
