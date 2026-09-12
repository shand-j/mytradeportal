"""CRM tests: customer/contact editable fields, parking/access contract, dedupe guard.

Covers beta backlog N25 (editable customer detail + parking/access persistence),
C5 (full address persisted, not just postcode) and C15 (duplicate guard).
"""

import pytest
from app.models import Contact
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _count_contacts(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(Contact))
    return int(result.scalar_one())


async def test_contact_create_round_trips_crm_fields(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/contacts",
        json={
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "07700 900123",
            "address": "12 Example Road, Springfield, SP1 2AB",
            "postcode": "SP1 2AB",
            "preferred_contact_method": "email",
            "property_type": "semi",
            "bedrooms": 3,
            "parking_notes": "Driveway for one van; permit zone after 6pm",
            "access_notes": "Key-safe code 1234; dog in the garden",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["address"] == "12 Example Road, Springfield, SP1 2AB"
    assert body["parking_notes"] == "Driveway for one van; permit zone after 6pm"
    assert body["access_notes"] == "Key-safe code 1234; dog in the garden"
    assert body["preferred_contact_method"] == "email"
    assert body["property_type"] == "semi"
    assert body["bedrooms"] == 3


async def test_contact_update_persists_address_and_site_notes(admin_client: AsyncClient) -> None:
    created = await admin_client.post("/contacts", json={"name": "John Doe"})
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]

    updated = await admin_client.patch(
        f"/contacts/{contact_id}",
        json={
            "address": "Flat 4, 99 High Street, Leeds",
            "postcode": "LS1 4AA",
            "parking_notes": "No on-site parking; use NCP on Park Row",
            "access_notes": "Communal entry, buzzer 4",
            "preferred_contact_method": "phone",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["address"] == "Flat 4, 99 High Street, Leeds"
    assert body["postcode"] == "LS1 4AA"
    assert body["parking_notes"] == "No on-site parking; use NCP on Park Row"
    assert body["access_notes"] == "Communal entry, buzzer 4"

    fetched = await admin_client.get(f"/contacts/{contact_id}")
    assert fetched.status_code == 200
    assert fetched.json()["parking_notes"] == "No on-site parking; use NCP on Park Row"


async def test_contact_read_payload_exposes_site_logistics_for_prefill(
    admin_client: AsyncClient,
) -> None:
    """The contract the quote/job agents pre-fill from (N25 chain)."""
    created = await admin_client.post(
        "/contacts",
        json={
            "name": "Contract Customer",
            "parking_notes": "Driveway",
            "access_notes": "Side gate unlocked",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    for key in (
        "address",
        "postcode",
        "parking_notes",
        "access_notes",
        "property_type",
        "bedrooms",
        "preferred_contact_method",
    ):
        assert key in body
    assert body["parking_notes"] == "Driveway"
    assert body["access_notes"] == "Side gate unlocked"


async def test_contact_create_duplicate_email_rejected(admin_client: AsyncClient) -> None:
    first = await admin_client.post(
        "/contacts", json={"name": "Person One", "email": "dup@example.com"}
    )
    assert first.status_code == 201, first.text

    second = await admin_client.post(
        "/contacts", json={"name": "Person One Again", "email": "DUP@example.com"}
    )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail.startswith("duplicate_contact:email:")
    assert first.json()["id"] in detail


async def test_contact_create_duplicate_name_and_phone_rejected(
    admin_client: AsyncClient,
) -> None:
    first = await admin_client.post(
        "/contacts", json={"name": "Sam  Jones", "phone": "07700 900 555"}
    )
    assert first.status_code == 201, first.text

    # Same person re-entered: normalised name matches and digits-only phone matches.
    second = await admin_client.post(
        "/contacts", json={"name": "sam jones", "phone": "07700900555"}
    )
    assert second.status_code == 409
    assert second.json()["detail"].startswith("duplicate_contact:name_phone:")


async def test_contact_create_distinct_person_allowed(admin_client: AsyncClient) -> None:
    first = await admin_client.post(
        "/contacts", json={"name": "Alice A", "email": "alice@example.com"}
    )
    second = await admin_client.post(
        "/contacts", json={"name": "Bob B", "email": "bob@example.com"}
    )
    assert first.status_code == 201
    assert second.status_code == 201


async def test_customer_create_persists_full_address_and_site_notes(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """C5: full address (not just postcode) persists on customer + contact."""
    response = await admin_client.post(
        "/customers",
        json={
            "full_name": "Home Owner",
            "email": "owner@example.com",
            "phone": "07700 111222",
            "address": "5 Mill Lane, Oxford, OX1 1AA",
            "postcode": "OX1 1AA",
            "preferred_contact_method": "in_app_chat",
            "parking_notes": "Permit holder bay outside",
            "access_notes": "Top-floor flat, no lift",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["address"] == "5 Mill Lane, Oxford, OX1 1AA"
    assert body["postcode"] == "OX1 1AA"
    assert body["parking_notes"] == "Permit holder bay outside"
    assert body["access_notes"] == "Top-floor flat, no lift"

    contact = await db.get(Contact, body["contact_id"])
    assert contact is not None
    assert contact.address == "5 Mill Lane, Oxford, OX1 1AA"
    assert contact.parking_notes == "Permit holder bay outside"
    assert contact.access_notes == "Top-floor flat, no lift"


async def test_customer_create_duplicate_email_rejected(admin_client: AsyncClient) -> None:
    first = await admin_client.post(
        "/customers", json={"full_name": "Dup Person", "email": "dup@example.com"}
    )
    assert first.status_code == 201, first.text

    second = await admin_client.post(
        "/customers", json={"full_name": "Dup Person", "email": "Dup@Example.com"}
    )
    assert second.status_code == 409
    assert second.json()["detail"].startswith("duplicate_customer:email:")


async def test_customer_create_merges_existing_contact(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """An existing CRM contact is linked/back-filled, not duplicated."""
    contact_resp = await admin_client.post(
        "/contacts", json={"name": "Existing Person", "email": "existing@example.com"}
    )
    assert contact_resp.status_code == 201, contact_resp.text
    contact_id = contact_resp.json()["id"]
    before = await _count_contacts(db)

    response = await admin_client.post(
        "/customers",
        json={
            "full_name": "Existing Person",
            "email": "existing@example.com",
            "parking_notes": "Shared driveway",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["contact_id"] == contact_id
    assert await _count_contacts(db) == before

    contact = await db.get(Contact, contact_id)
    assert contact is not None
    assert contact.parking_notes == "Shared driveway"


async def test_customer_update_mirrors_site_notes_to_contact(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    created = await admin_client.post(
        "/customers", json={"full_name": "Edit Me", "email": "editme@example.com"}
    )
    assert created.status_code == 201, created.text
    customer = created.json()

    updated = await admin_client.patch(
        f"/customers/{customer['id']}",
        json={
            "address": "21 New Street, Bristol",
            "postcode": "BS1 2AA",
            "parking_notes": "Underground car park, level -1",
            "access_notes": "Concierge has keys",
            "preferred_contact_method": "email",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["address"] == "21 New Street, Bristol"
    assert body["parking_notes"] == "Underground car park, level -1"

    contact = await db.get(Contact, customer["contact_id"])
    assert contact is not None
    assert contact.address == "21 New Street, Bristol"
    assert contact.parking_notes == "Underground car park, level -1"
    assert contact.access_notes == "Concierge has keys"
    assert contact.preferred_contact_method == "email"


async def test_customer_update_not_found(admin_client: AsyncClient) -> None:
    response = await admin_client.patch(
        "/customers/00000000-0000-0000-0000-000000000000",
        json={"parking_notes": "x"},
    )
    assert response.status_code == 404
