"""Dispatch guardrails tests (epic #233 phase 2, issue #235).

Covers the server-side assignment rules on job/appointment create and update
and quote convert-to-job: double-booking 409s (with boundary-touch allowed),
the 10h daily scheduled-hours cap, and the in-progress/completed lockdown on
reassignment/reschedule. Draft jobs and cancelled appointments never block;
unassigned work is never guarded.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from app.models import Job, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

# Fixed future Monday/Tuesday so the tests never depend on the run date.
DAY1 = datetime(2027, 1, 4, 9, 0)  # Monday
DAY2 = DAY1 + timedelta(days=1)


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


async def _add_user(db: AsyncSession, tenant_id: str, email: str) -> User:
    """Add a second active staff user to the tenant."""
    await set_tenant_in_session(db, UUID(tenant_id))
    user = User(
        tenant_id=UUID(tenant_id),
        email=email,
        full_name=email.split("@")[0].replace(".", " ").title(),
        role="manager",
        password_hash=get_password_hash("password-123"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _iso(start: datetime, hours: float) -> tuple[str, str]:
    end = start + timedelta(hours=hours)
    return start.isoformat(), end.isoformat()


async def _create_job(
    client: AsyncClient,
    contact_id: str,
    title: str,
    start: datetime,
    hours: float,
    assigned_user_id: str | None = None,
) -> Any:
    start_iso, end_iso = _iso(start, hours)
    payload: dict[str, Any] = {
        "contact_id": contact_id,
        "title": title,
        "scheduled_start": start_iso,
        "scheduled_end": end_iso,
    }
    if assigned_user_id is not None:
        payload["assigned_user_id"] = assigned_user_id
    return await client.post("/jobs", json=payload)


async def _create_appointment(
    client: AsyncClient,
    contact_id: str,
    title: str,
    start: datetime,
    hours: float,
    assigned_user_id: str | None = None,
) -> Any:
    start_iso, end_iso = _iso(start, hours)
    payload: dict[str, Any] = {
        "contact_id": contact_id,
        "title": title,
        "start_at": start_iso,
        "end_at": end_iso,
    }
    if assigned_user_id is not None:
        payload["assigned_user_id"] = assigned_user_id
    return await client.post("/appointments", json=payload)


# ---------------------------------------------------------------------------
# Double-booking
# ---------------------------------------------------------------------------


async def test_job_create_rejects_overlap(admin_client: AsyncClient, db: AsyncSession) -> None:
    """An overlapping job for the same assignee is a structured 409."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Overlap One")

    first = await _create_job(admin_client, contact["id"], "First job", DAY1, 2)
    assert first.status_code == 201, first.text
    # Sole-staff tenant: auto-assigned to the admin.

    overlap = await _create_job(
        admin_client, contact["id"], "Clashing job", DAY1 + timedelta(hours=1), 2
    )
    assert overlap.status_code == 409, overlap.text
    detail = overlap.json()["detail"]
    assert detail["code"] == "schedule_conflict"
    assert "First job" in detail["reason"]


async def test_job_create_allows_boundary_touch(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Back-to-back slots (end == start) do not conflict."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Boundary Touch")

    first = await _create_job(admin_client, contact["id"], "Morning job", DAY1, 2)
    assert first.status_code == 201, first.text

    adjacent = await _create_job(
        admin_client, contact["id"], "Afternoon job", DAY1 + timedelta(hours=2), 2
    )
    assert adjacent.status_code == 201, adjacent.text


async def test_overlap_only_counts_same_assignee(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Another team member's calendar is independent."""
    me = await _me(admin_client)
    second = await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "Other Assignee")

    first = await _create_job(admin_client, contact["id"], "Admin job", DAY1, 2)
    assert first.status_code == 201, first.text

    other = await _create_job(
        admin_client, contact["id"], "Second's job", DAY1, 2, assigned_user_id=str(second.id)
    )
    assert other.status_code == 201, other.text


async def test_draft_job_does_not_block(admin_client: AsyncClient, db: AsyncSession) -> None:
    """Draft jobs (quote-acceptance holds) never trigger the overlap guard."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Draft Holder")
    await set_tenant_in_session(db, UUID(me["tenant_id"]))
    draft = Job(
        tenant_id=UUID(me["tenant_id"]),
        contact_id=UUID(contact["id"]),
        title="Draft hold",
        status="draft",
        scheduled_start=DAY1,
        scheduled_end=DAY1 + timedelta(hours=2),
        assigned_user_id=UUID(me["id"]),
    )
    db.add(draft)
    await db.commit()

    response = await _create_job(admin_client, contact["id"], "Real job", DAY1, 2)
    assert response.status_code == 201, response.text


async def test_appointment_create_and_reschedule_reject_overlap(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Appointments guard the same window on create and on PATCH reschedule."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Appt Overlap")

    first = await _create_appointment(admin_client, contact["id"], "Site survey", DAY1, 1)
    assert first.status_code == 201, first.text

    clash = await _create_appointment(
        admin_client, contact["id"], "Clashing visit", DAY1 + timedelta(minutes=30), 1
    )
    assert clash.status_code == 409
    assert clash.json()["detail"]["code"] == "schedule_conflict"

    # A free appointment rescheduled INTO the busy window is rejected too.
    free = await _create_appointment(
        admin_client, contact["id"], "Later visit", DAY1 + timedelta(hours=4), 1
    )
    assert free.status_code == 201, free.text
    moved = await admin_client.patch(
        f"/appointments/{free.json()['id']}",
        json={"start_at": DAY1.isoformat()},
    )
    assert moved.status_code == 409
    assert moved.json()["detail"]["code"] == "schedule_conflict"


async def test_cancelled_appointment_does_not_block(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Cancelled Slot")

    first = await _create_appointment(admin_client, contact["id"], "Cancelled visit", DAY1, 2)
    assert first.status_code == 201, first.text
    cancel = await admin_client.patch(
        f"/appointments/{first.json()['id']}", json={"status": "cancelled"}
    )
    assert cancel.status_code == 200, cancel.text

    refill = await _create_appointment(admin_client, contact["id"], "Refilled visit", DAY1, 2)
    assert refill.status_code == 201, refill.text


async def test_job_reschedule_rejects_overlap_and_leaves_job_unchanged(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A rejected reschedule must not persist the new slot."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Reschedule Guard")

    first = await _create_job(admin_client, contact["id"], "Booked job", DAY1, 2)
    assert first.status_code == 201, first.text
    second = await _create_job(
        admin_client, contact["id"], "Moving job", DAY1 + timedelta(hours=4), 2
    )
    assert second.status_code == 201, second.text
    job_id = second.json()["id"]

    moved = await admin_client.patch(f"/jobs/{job_id}", json={"scheduled_start": DAY1.isoformat()})
    assert moved.status_code == 409
    assert moved.json()["detail"]["code"] == "schedule_conflict"

    fetched = await admin_client.get(f"/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["scheduled_start"].startswith(
        (DAY1 + timedelta(hours=4)).isoformat()[:16]
    )


async def test_job_reschedule_onto_own_slot_is_allowed(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Saving the same schedule never conflicts with itself."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Self Slot")
    created = await _create_job(admin_client, contact["id"], "Steady job", DAY1, 2)
    assert created.status_code == 201, created.text

    same = await admin_client.patch(
        f"/jobs/{created.json()['id']}", json={"scheduled_start": DAY1.isoformat()}
    )
    assert same.status_code == 200, same.text


async def test_multi_day_job_rejects_when_a_later_block_conflicts(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Every working-day block of a multi-day job is guarded, not just day 1."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Multi Day")

    blocker = await _create_appointment(
        admin_client, contact["id"], "Day 2 hold", DAY2.replace(hour=8), 1
    )
    assert blocker.status_code == 201, blocker.text

    # Default working hours are 08:00-18:00 (10h/day), so 12h splits into
    # 10h on day 1 plus a 2h day-2 block appointment at 08:00 — over the hold.
    start_iso, end_iso = _iso(DAY1.replace(hour=8), 12)
    response = await admin_client.post(
        "/jobs",
        json={
            "contact_id": contact["id"],
            "title": "Two-day rewire",
            "scheduled_start": start_iso,
            "scheduled_end": end_iso,
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "schedule_conflict"


# ---------------------------------------------------------------------------
# Daily cap
# ---------------------------------------------------------------------------


async def test_daily_cap_rejects_beyond_ten_hours(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """8h + 3h on one calendar day exceeds the 10h cap; 8h + 2h is allowed."""
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Cap Check")

    eight = await _create_job(admin_client, contact["id"], "Long job", DAY1.replace(hour=8), 8)
    assert eight.status_code == 201, eight.text

    # Boundary-touching (16:00 start), so only the cap can reject this.
    too_much = await _create_job(
        admin_client, contact["id"], "Overtime job", DAY1.replace(hour=16), 3
    )
    assert too_much.status_code == 409, too_much.text
    detail = too_much.json()["detail"]
    assert detail["code"] == "daily_hours_cap"
    assert "10h" in detail["reason"]

    exactly_ten = await _create_job(
        admin_client, contact["id"], "Top-up job", DAY1.replace(hour=16), 2
    )
    assert exactly_ten.status_code == 201, exactly_ten.text


async def test_daily_cap_counts_appointments_and_jobs_together(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Mixed Day")

    job = await _create_job(admin_client, contact["id"], "Six hour job", DAY1.replace(hour=8), 6)
    assert job.status_code == 201, job.text
    appt = await _create_appointment(
        admin_client, contact["id"], "Two hour visit", DAY1.replace(hour=14), 2
    )
    assert appt.status_code == 201, appt.text

    over = await _create_appointment(
        admin_client, contact["id"], "Three hour extra", DAY1.replace(hour=16), 3
    )
    assert over.status_code == 409
    assert over.json()["detail"]["code"] == "daily_hours_cap"


async def test_daily_cap_is_per_assignee(admin_client: AsyncClient, db: AsyncSession) -> None:
    me = await _me(admin_client)
    second = await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "Cap Split")

    eight = await _create_job(
        admin_client, contact["id"], "Admin's long day", DAY1.replace(hour=8), 8
    )
    assert eight.status_code == 201, eight.text

    other = await _create_job(
        admin_client,
        contact["id"],
        "Second's job",
        DAY1.replace(hour=16),
        3,
        assigned_user_id=str(second.id),
    )
    assert other.status_code == 201, other.text


# ---------------------------------------------------------------------------
# In-progress / completed lockdown
# ---------------------------------------------------------------------------


async def test_in_progress_job_rejects_reassignment_and_reschedule(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    me = await _me(admin_client)
    second = await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "Locked Job")

    created = await _create_job(admin_client, contact["id"], "Live job", DAY1, 2)
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    started = await admin_client.post(f"/jobs/{job_id}/start")
    assert started.status_code == 200, started.text

    reassigned = await admin_client.patch(
        f"/jobs/{job_id}", json={"assigned_user_id": str(second.id)}
    )
    assert reassigned.status_code == 409
    assert reassigned.json()["detail"]["code"] == "job_locked"

    rescheduled = await admin_client.patch(
        f"/jobs/{job_id}", json={"scheduled_start": DAY2.isoformat()}
    )
    assert rescheduled.status_code == 409
    assert rescheduled.json()["detail"]["code"] == "job_locked"

    # Notes remain editable while the job is live.
    notes = await admin_client.patch(f"/jobs/{job_id}", json={"notes": "Customer has a dog"})
    assert notes.status_code == 200, notes.text


async def test_completed_job_rejects_reschedule(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Done Job")

    created = await _create_job(admin_client, contact["id"], "Finished job", DAY1, 2)
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    await admin_client.post(f"/jobs/{job_id}/start")
    completed = await admin_client.post(f"/jobs/{job_id}/complete")
    assert completed.status_code == 200, completed.text

    rescheduled = await admin_client.patch(
        f"/jobs/{job_id}", json={"scheduled_start": DAY2.isoformat()}
    )
    assert rescheduled.status_code == 409
    assert rescheduled.json()["detail"]["code"] == "job_locked"


# ---------------------------------------------------------------------------
# Unassigned work is never guarded
# ---------------------------------------------------------------------------


async def test_unassigned_creation_unaffected(admin_client: AsyncClient, db: AsyncSession) -> None:
    """Multi-user tenant, no assignee: overlapping schedules are allowed."""
    me = await _me(admin_client)
    await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "Unassigned Work")

    first = await _create_job(admin_client, contact["id"], "Unassigned one", DAY1, 3)
    assert first.status_code == 201, first.text
    assert first.json()["assigned_user_id"] is None

    second_job = await _create_job(admin_client, contact["id"], "Unassigned two", DAY1, 3)
    assert second_job.status_code == 201, second_job.text

    appt = await _create_appointment(admin_client, contact["id"], "Unassigned visit", DAY1, 3)
    assert appt.status_code == 201, appt.text


async def test_explicit_assignee_flows_still_pass(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """The #191 explicit-assignment behaviour is unchanged by the guardrails."""
    me = await _me(admin_client)
    second = await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "Explicit Assign")

    job = await _create_job(
        admin_client, contact["id"], "Second's job", DAY1, 2, assigned_user_id=str(second.id)
    )
    assert job.status_code == 201, job.text
    assert job.json()["assigned_user_id"] == str(second.id)

    # Same assignee + same window → the new guardrail rejects the appointment.
    clash = await _create_appointment(
        admin_client,
        contact["id"],
        "Second's clashing visit",
        DAY1,
        2,
        assigned_user_id=str(second.id),
    )
    assert clash.status_code == 409
    assert clash.json()["detail"]["code"] == "schedule_conflict"

    # A free window for the same assignee is still accepted and respected.
    ok = await _create_appointment(
        admin_client,
        contact["id"],
        "Second's visit",
        DAY1 + timedelta(hours=2),
        1,
        assigned_user_id=str(second.id),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["assigned_user_id"] == str(second.id)


async def test_appointment_reassignment_respects_guardrails(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """PATCH assigned_user_id moves the booking onto another calendar."""
    me = await _me(admin_client)
    second = await _add_user(db, me["tenant_id"], "second@test.local")
    contact = await _create_contact(admin_client, me["tenant_id"], "Move Visit")

    admin_job = await _create_job(
        admin_client, contact["id"], "Admin's job", DAY1, 2, assigned_user_id=me["id"]
    )
    assert admin_job.status_code == 201, admin_job.text

    appt = await _create_appointment(
        admin_client, contact["id"], "Roving visit", DAY2, 1, assigned_user_id=str(second.id)
    )
    assert appt.status_code == 201, appt.text
    appt_id = appt.json()["id"]

    # Reassigning onto the admin's day-2 calendar: free → allowed.
    ok = await admin_client.patch(f"/appointments/{appt_id}", json={"assigned_user_id": me["id"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["assigned_user_id"] == me["id"]

    # Moving the appointment into the admin's booked day-1 window → conflict.
    clash = await admin_client.patch(
        f"/appointments/{appt_id}",
        json={"start_at": DAY1.isoformat(), "end_at": (DAY1 + timedelta(hours=1)).isoformat()},
    )
    assert clash.status_code == 409
    assert clash.json()["detail"]["code"] == "schedule_conflict"


# ---------------------------------------------------------------------------
# Quote convert-to-job
# ---------------------------------------------------------------------------


async def _create_approved_quote(
    client: AsyncClient, tenant_id: str, contact_id: str
) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Rewire quote",
            "line_items": [
                {"description": "Labour", "quantity": "2", "unit": "hours", "unit_price": "60.00"}
            ],
        },
    )
    assert response.status_code == 201, response.text
    quote: dict[str, Any] = response.json()
    approve = await client.post(
        f"/quotes/{quote['id']}/approve", headers={"X-Tenant-ID": tenant_id}, json={}
    )
    assert approve.status_code == 200, approve.text
    return quote


async def test_convert_to_job_rejects_overlap(admin_client: AsyncClient, db: AsyncSession) -> None:
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Convert Guard")

    existing = await _create_job(admin_client, contact["id"], "Booked job", DAY1, 3)
    assert existing.status_code == 201, existing.text

    quote = await _create_approved_quote(admin_client, me["tenant_id"], contact["id"])
    start_iso, end_iso = _iso(DAY1 + timedelta(hours=1), 2)
    response = await admin_client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        json={"scheduled_start": start_iso, "scheduled_end": end_iso},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "schedule_conflict"


async def test_convert_to_job_on_free_slot_still_works(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    me = await _me(admin_client)
    contact = await _create_contact(admin_client, me["tenant_id"], "Convert Free")

    existing = await _create_job(admin_client, contact["id"], "Morning job", DAY1, 2)
    assert existing.status_code == 201, existing.text

    quote = await _create_approved_quote(admin_client, me["tenant_id"], contact["id"])
    start_iso, end_iso = _iso(DAY1 + timedelta(hours=2), 2)
    response = await admin_client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        json={"scheduled_start": start_iso, "scheduled_end": end_iso},
    )
    assert response.status_code == 201, response.text
    assert response.json()["scheduled_start"].startswith(start_iso[:16])
