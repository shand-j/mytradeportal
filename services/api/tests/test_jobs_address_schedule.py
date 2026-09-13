"""G2/G3 job tests: contact-address denormalisation, accepted_dates schedule
prefill on quote → job conversion, and one-way job → appointment schedule sync.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import Quote as QuoteModel
from app.rls import set_tenant_in_session
from app.routers.quotes import _parse_accepted_date
from httpx import AsyncClient
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_contact(
    client: AsyncClient,
    tenant_id: str,
    name: str,
    address: str | None = None,
    postcode: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "email": f"{name.lower().replace(' ', '.')}@example.com",
    }
    if address is not None:
        payload["address"] = address
    if postcode is not None:
        payload["postcode"] = postcode
    response = await client.post("/contacts", headers={"X-Tenant-ID": tenant_id}, json=payload)
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_quote(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Consumer unit replacement",
            "line_items": [
                {"description": "Labour", "quantity": "3", "unit": "hrs", "unit_price": "45.00"},
                {"description": "10-way board", "quantity": "1", "unit_price": "120.00"},
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


async def _set_accepted_dates(
    db: AsyncSession, tenant_id: str, quote_id: str, dates: list[str]
) -> None:
    await set_tenant_in_session(db, UUID(tenant_id))
    await db.execute(
        sa_update(QuoteModel).where(QuoteModel.id == UUID(quote_id)).values(accepted_dates=dates)
    )
    await db.commit()


async def test_create_job_denormalises_contact_address(client: AsyncClient) -> None:
    """G2: POST /jobs copies the contact's address/postcode onto the job."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(
        client, tenant["id"], "Denorm Create", address="1 Millbank", postcode="SW1P 3AA"
    )

    response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["address"] == "1 Millbank"
    assert job["postcode"] == "SW1P 3AA"

    # A later contact edit must not rewrite the job's history.
    patched = await client.patch(
        f"/contacts/{contact['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"address": "9 Moved Away", "postcode": "N1 9GU"},
    )
    assert patched.status_code == 200

    fetched = await client.get(f"/jobs/{job['id']}", headers={"X-Tenant-ID": tenant["id"]})
    assert fetched.status_code == 200
    assert fetched.json()["address"] == "1 Millbank"
    assert fetched.json()["postcode"] == "SW1P 3AA"


async def test_convert_to_job_denormalises_contact_address(
    client: AsyncClient, db: AsyncSession
) -> None:
    """G2: convert-to-job copies the contact's address/postcode onto the job."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(
        client, tenant["id"], "Denorm Convert", address="22 Baker Street", postcode="NW1 6XE"
    )
    quote = await _create_quote(client, tenant["id"], contact["id"])
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["address"] == "22 Baker Street"
    assert job["postcode"] == "NW1 6XE"


async def test_convert_to_job_prefills_earliest_accepted_date(
    client: AsyncClient, db: AsyncSession
) -> None:
    """G3: no explicit schedule → earliest accepted date at 09:00, end = start
    + quoted labour hours (3 hrs of labour lines here)."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Prefill Dates")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    later = date.today() + timedelta(days=5)
    earlier = date.today() + timedelta(days=2)
    await _set_accepted_dates(
        db, tenant["id"], quote["id"], [later.isoformat(), earlier.isoformat()]
    )
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["scheduled_start"] == f"{earlier.isoformat()}T09:00:00"
    assert job["scheduled_end"] == f"{earlier.isoformat()}T12:00:00"
    # The labels still ride along in the notes for context.
    assert later.isoformat() in (job["notes"] or "")


async def test_convert_to_job_explicit_schedule_wins(client: AsyncClient, db: AsyncSession) -> None:
    """G3: an explicitly provided scheduled_start/end beats the prefill."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Explicit Wins")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    await _set_accepted_dates(
        db, tenant["id"], quote["id"], [(date.today() + timedelta(days=2)).isoformat()]
    )
    await _approve_quote(client, tenant["id"], quote["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": "2026-10-01T13:30:00", "scheduled_end": "2026-10-01T15:30:00"},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["scheduled_start"] == "2026-10-01T13:30:00"
    assert job["scheduled_end"] == "2026-10-01T15:30:00"


async def test_update_job_schedule_syncs_linked_appointment(client: AsyncClient) -> None:
    """G3: setting/changing a job's schedule moves the linked appointment."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Sync Target")

    created = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "EICR"},
    )
    assert created.status_code == 201
    job = created.json()

    appt = await client.post(
        "/appointments",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "job_id": job["id"],
            "title": "EICR visit",
            "start_at": "2026-09-20T09:00:00",
            "end_at": "2026-09-20T11:00:00",
        },
    )
    assert appt.status_code == 201, appt.text
    appointment_id = appt.json()["id"]

    # Scheduling the job moves the appointment to the same slot.
    scheduled = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": "2026-09-22T14:00:00", "scheduled_end": "2026-09-22T16:00:00"},
    )
    assert scheduled.status_code == 200, scheduled.text

    fetched = await client.get(
        f"/appointments/{appointment_id}", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert fetched.status_code == 200
    assert fetched.json()["start_at"] == "2026-09-22T14:00:00"
    assert fetched.json()["end_at"] == "2026-09-22T16:00:00"

    # An end-less reschedule keeps the appointment's previous duration (2h).
    moved = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": "2026-09-23T10:00:00", "scheduled_end": None},
    )
    assert moved.status_code == 200, moved.text

    refetched = await client.get(
        f"/appointments/{appointment_id}", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert refetched.status_code == 200
    assert refetched.json()["start_at"] == "2026-09-23T10:00:00"
    assert refetched.json()["end_at"] == "2026-09-23T12:00:00"


async def test_update_job_schedule_without_appointment_noops(client: AsyncClient) -> None:
    """G3: scheduling a job with no linked appointment succeeds untouched."""
    tenant = await _create_tenant(client, f"job-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "No Appt")

    created = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "PAT testing"},
    )
    assert created.status_code == 201
    job = created.json()

    response = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": "2026-09-25T09:00:00", "scheduled_end": "2026-09-25T10:00:00"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["scheduled_start"] == "2026-09-25T09:00:00"

    # No appointments were created as a side effect.
    listed = await client.get("/appointments", headers={"X-Tenant-ID": tenant["id"]})
    assert listed.status_code == 200
    assert listed.json() == []


async def test_parse_accepted_date_formats() -> None:
    """The accepted-date parser handles ISO dates and en-GB short labels."""
    today = date(2026, 9, 13)
    assert _parse_accepted_date("2026-09-20", today) == date(2026, 9, 20)
    assert _parse_accepted_date("Mon 14 Sep", today) == date(2026, 9, 14)
    # Labels without a year roll to next year once the day has passed.
    assert _parse_accepted_date("Fri 11 Sep", today) == date(2027, 9, 11)
    assert _parse_accepted_date("not a date", today) is None
    assert _parse_accepted_date("", today) is None
    assert _parse_accepted_date(None, today) is None
