"""Wave-2 job journey tests: assignee, editable notes, AI-notes carry-over,
photo carry-over on quote → job conversion, and job-aware availability."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import MediaAsset, QuoteRequest, User
from app.models import Quote as QuoteModel
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
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


async def _create_user(db: AsyncSession, tenant_id: str, name: str) -> User:
    await set_tenant_in_session(db, UUID(tenant_id))
    user = User(
        tenant_id=UUID(tenant_id),
        email=f"{name.lower().replace(' ', '.')}@staff.example.com",
        full_name=name,
        role="engineer",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_quote(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Consumer unit replacement",
            "line_items": [
                {"description": "Labour", "quantity": "10", "unit_price": "45.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _approve_quote(client: AsyncClient, tenant_id: str, quote_id: str) -> None:
    response = await client.post(
        f"/quotes/{quote_id}/approve",
        headers={"X-Tenant-ID": tenant_id},
        json={},
    )
    assert response.status_code == 200, response.text


async def test_create_job_with_notes_and_assignee(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Assign Creator")
    user = await _create_user(db, tenant["id"], "Spark One")

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Rewire kitchen",
            "notes": "Parking on driveway",
            "assigned_user_id": str(user.id),
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["notes"] == "Parking on driveway"
    assert job["assigned_user_id"] == str(user.id)
    assert job["assigned_to"] == "Spark One"
    assert job["photos"] == []

    # The assignee display name survives a fresh read.
    fetched = await client.get(f"/jobs/{job['id']}", headers={"X-Tenant-ID": tenant["id"]})
    assert fetched.status_code == 200
    assert fetched.json()["assigned_to"] == "Spark One"


async def test_list_jobs_filters_by_assignee(client: AsyncClient, db: AsyncSession) -> None:
    """?assigned_user_id narrows the list ("Me"); omitting it returns all ("All")."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "List Filter")
    spark_one = await _create_user(db, tenant["id"], "Spark One")
    spark_two = await _create_user(db, tenant["id"], "Spark Two")

    async def create(title: str, assignee: User | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"contact_id": contact["id"], "title": title}
        if assignee is not None:
            payload["assigned_user_id"] = str(assignee.id)
        response = await client.post("/jobs", headers={"X-Tenant-ID": tenant["id"]}, json=payload)
        assert response.status_code == 201, response.text
        data: dict[str, Any] = response.json()
        return data

    mine = await create("Job for one", spark_one)
    theirs = await create("Job for two", spark_two)
    unassigned = await create("Unassigned job", None)

    all_response = await client.get("/jobs", headers={"X-Tenant-ID": tenant["id"]})
    assert all_response.status_code == 200
    all_ids = {job["id"] for job in all_response.json()}
    assert all_ids == {mine["id"], theirs["id"], unassigned["id"]}

    filtered = await client.get(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"assigned_user_id": str(spark_one.id)},
    )
    assert filtered.status_code == 200
    assert {job["id"] for job in filtered.json()} == {mine["id"]}


async def test_create_job_merges_contact_notes(client: AsyncClient) -> None:
    """The CRM contact's notes are appended to the job notes at creation,
    keeping whatever the user typed on the create screen first."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact_response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"name": "Notes Carrier", "notes": "Gate code 4521; dog on site"},
    )
    assert contact_response.status_code == 201
    contact = contact_response.json()

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Rewire kitchen",
            "notes": "Parking on driveway",
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["notes"].startswith("Parking on driveway")
    assert "Gate code 4521; dog on site" in job["notes"]

    # No notes typed → the contact's notes alone seed the job notes.
    bare = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "EICR"},
    )
    assert bare.status_code == 201, bare.text
    assert "Gate code 4521; dog on site" in bare.json()["notes"]


async def test_create_job_rejects_unknown_assignee(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Bad Assignee")

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Rewire kitchen",
            "assigned_user_id": str(uuid4()),
        },
    )
    assert response.status_code == 400


async def test_create_job_rejects_cross_tenant_assignee(
    client: AsyncClient, db: AsyncSession
) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    other = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Cross Tenant")
    outsider = await _create_user(db, other["id"], "Outside Spark")

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Rewire kitchen",
            "assigned_user_id": str(outsider.id),
        },
    )
    assert response.status_code == 400


async def test_update_job_notes_and_assignee(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Editor")
    user = await _create_user(db, tenant["id"], "Spark Two")

    created = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    assert created.status_code == 201
    job = created.json()
    assert job["assigned_to"] is None

    updated = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"notes": "Customer has a dog", "assigned_user_id": str(user.id)},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["notes"] == "Customer has a dog"
    assert body["assigned_to"] == "Spark Two"

    # Unassigning (explicit null) is allowed.
    unassigned = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"assigned_user_id": None},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["assigned_user_id"] is None
    assert unassigned.json()["assigned_to"] is None


async def test_update_job_rejects_unknown_assignee(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Bad Patch")
    created = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    job = created.json()

    response = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"assigned_user_id": str(uuid4())},
    )
    assert response.status_code == 400


async def test_convert_to_job_copies_ai_assumptions_into_notes(
    client: AsyncClient, db: AsyncSession
) -> None:
    """N12: AI assumptions/footnotes on the quote land in the job notes."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "AI Convert")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    await set_tenant_in_session(db, UUID(tenant["id"]))
    await db.execute(
        sa_update(QuoteModel)
        .where(QuoteModel.id == UUID(quote["id"]))
        .values(
            extra_data={
                "rag": {
                    "assumptions": ["3-bed semi, easy loft access", "Standard 10-way board"],
                    "notes": "Guide-priced from catalogue; confirm cable runs on site.",
                }
            }
        )
    )
    await db.commit()
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"notes": "Ring ahead"},
    )
    assert response.status_code == 201, response.text
    notes = response.json()["notes"] or ""
    assert "Ring ahead" in notes
    assert "3-bed semi, easy loft access" in notes
    assert "Standard 10-way board" in notes
    assert "Guide-priced from catalogue" in notes


async def test_convert_to_job_carries_quote_request_media(
    client: AsyncClient, db: AsyncSession
) -> None:
    """N13: photos uploaded against the quote's quote request attach to the job."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Photo Convert")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    await set_tenant_in_session(db, UUID(tenant["id"]))
    quote_request = QuoteRequest(
        tenant_id=UUID(tenant["id"]),
        contact_id=UUID(contact["id"]),
        source="web_form",
    )
    db.add(quote_request)
    await db.flush()
    asset = MediaAsset(
        tenant_id=UUID(tenant["id"]),
        quote_request_id=quote_request.id,
        file_url="https://api.example.com/files/media/board.jpg",
        file_key="media/board.jpg",
        mime_type="image/jpeg",
    )
    db.add(asset)
    await db.execute(
        sa_update(QuoteModel)
        .where(QuoteModel.id == UUID(quote["id"]))
        .values(quote_request_id=quote_request.id)
    )
    await db.commit()
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["photos"] == ["https://api.example.com/files/media/board.jpg"]

    # Photos persist on subsequent reads of the job.
    fetched = await client.get(f"/jobs/{job['id']}", headers={"X-Tenant-ID": tenant["id"]})
    assert fetched.status_code == 200
    assert fetched.json()["photos"] == ["https://api.example.com/files/media/board.jpg"]


async def test_convert_to_job_with_assignee(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Assign Convert")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    user = await _create_user(db, tenant["id"], "Spark Three")
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"assigned_user_id": str(user.id)},
    )
    assert response.status_code == 201, response.text
    assert response.json()["assigned_to"] == "Spark Three"

    bad = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"assigned_user_id": str(uuid4())},
    )
    # The quote already converted → 409 takes precedence; a fresh quote with a
    # bogus assignee must 400 instead.
    assert bad.status_code == 409


async def test_availability_blocks_slots_with_scheduled_jobs(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Busy Diary")

    created = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Morning job",
            "scheduled_start": "2026-09-14T09:00:00",
            "scheduled_end": "2026-09-14T12:00:00",
        },
    )
    assert created.status_code == 201

    response = await client.get(
        "/appointments/availability",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"date": "2026-09-14"},
    )
    assert response.status_code == 200
    slots = response.json()
    assert "2026-09-14T08:00:00" in slots
    assert "2026-09-14T09:00:00" not in slots
    assert "2026-09-14T10:00:00" not in slots
    assert "2026-09-14T11:00:00" not in slots
    assert "2026-09-14T12:00:00" in slots


async def test_availability_job_without_end_blocks_one_hour(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Open Ended")

    created = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Short job",
            "scheduled_start": "2026-09-14T14:00:00",
        },
    )
    assert created.status_code == 201

    response = await client.get(
        "/appointments/availability",
        headers={"X-Tenant-ID": tenant["id"]},
        params={"date": "2026-09-14"},
    )
    assert response.status_code == 200
    slots = response.json()
    assert "2026-09-14T13:00:00" in slots
    assert "2026-09-14T14:00:00" not in slots
    assert "2026-09-14T15:00:00" in slots
