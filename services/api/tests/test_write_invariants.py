"""Regression tests for strict write invariants on numeric/schedule inputs."""

from collections.abc import Callable
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _set_vat_registered(client: AsyncClient, registered: bool) -> None:
    response = await client.patch(
        "/onboarding/step/tax",
        json={"step": "tax", "value": {"vat_registered": registered}},
    )
    assert response.status_code == 200, response.text


async def _create_contact(client: AsyncClient, name: str = "Invariant Contact") -> str:
    response = await client.post(
        "/contacts",
        json={"name": name, "email": f"invariants-{uuid4().hex[:8]}@example.com"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _document_payload(endpoint: str, contact_id: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "contact_id": contact_id,
        "line_items": [{"description": "Labour", "quantity": "1", "unit_price": "100.00"}],
    }
    if endpoint == "/quotes":
        payload["title"] = "Invariant quote"
    return payload


@pytest.mark.parametrize("endpoint", ["/quotes", "/invoices"])
async def test_tenant_vat_rate_percent_keeps_fraction_ceiling(
    admin_client: AsyncClient, endpoint: str
) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)

    update = await admin_client.patch("/tenants/me", json={"vatRate": 20})
    assert update.status_code == 200, update.text
    assert update.json()["vatRate"] == pytest.approx(20.0)

    created = await admin_client.post(
        endpoint,
        json={**_document_payload(endpoint, contact_id), "vat_rate": "0.21"},
    )
    assert created.status_code == 400
    assert "registered VAT rate" in created.json()["detail"]

    ok = await admin_client.post(endpoint, json=_document_payload(endpoint, contact_id))
    assert ok.status_code == 201, ok.text
    patched = await admin_client.patch(f"{endpoint}/{ok.json()['id']}", json={"vat_rate": "0.21"})
    assert patched.status_code == 400
    assert "registered VAT rate" in patched.json()["detail"]


@pytest.mark.parametrize("endpoint", ["/quotes", "/invoices"])
@pytest.mark.parametrize(
    "override",
    [
        {"vat_rate": "-0.01"},
        {"vat_rate": "NaN"},
        {"line_items": [{"description": "Labour", "quantity": "-1", "unit_price": "100.00"}]},
        {"line_items": [{"description": "Labour", "quantity": "0", "unit_price": "100.00"}]},
        {"line_items": [{"description": "Labour", "quantity": "1", "unit_price": "-100.00"}]},
        {"line_items": [{"description": "Labour", "quantity": "1", "unit_price": "0"}]},
        {"line_items": [{"description": "   ", "quantity": "1", "unit_price": "100.00"}]},
        {"line_items": [{"description": "Labour", "quantity": "1.001", "unit_price": "100.00"}]},
        {"line_items": [{"description": "Labour", "quantity": "1", "unit_price": "1e100"}]},
    ],
)
async def test_invalid_document_create_is_rejected_without_persisting_row(
    admin_client: AsyncClient,
    endpoint: str,
    override: dict[str, object],
) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)

    before = await admin_client.get(endpoint)
    assert before.status_code == 200
    response = await admin_client.post(
        endpoint,
        json={**_document_payload(endpoint, contact_id), **deepcopy(override)},
    )
    assert response.status_code in {400, 422}, response.text
    assert "traceback" not in response.text.lower()
    after = await admin_client.get(endpoint)
    assert after.status_code == 200
    assert len(after.json()) == len(before.json())


@pytest.mark.parametrize("endpoint", ["/quotes", "/invoices"])
async def test_document_create_accepts_db_precision_boundary_values(
    admin_client: AsyncClient, endpoint: str
) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    payload = _document_payload(endpoint, contact_id)
    payload["vat_rate"] = "0.20"
    payload["line_items"] = [
        {
            "description": "Boundary labour",
            "quantity": "99999999.99",
            "unit_price": "0.0001",
        }
    ]
    response = await admin_client.post(endpoint, json=payload)
    assert response.status_code == 201, response.text


async def test_quote_update_rejects_invalid_numeric_values_and_keeps_state(
    admin_client: AsyncClient,
) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/quotes", json=_document_payload("/quotes", contact_id))
    assert created.status_code == 201, created.text
    quote_id = str(created.json()["id"])
    before = await admin_client.get(f"/quotes/{quote_id}")
    assert before.status_code == 200

    for patch in (
        {"vat_rate": "-0.01"},
        {"vat_rate": "NaN"},
        {"estimated_hours": "-1"},
        {"estimated_hours": "10000.00"},
        {"line_items": [{"description": "Labour", "quantity": "-1", "unit_price": "100.00"}]},
        {"line_items": [{"description": "   ", "quantity": "1", "unit_price": "100.00"}]},
    ):
        rejected = await admin_client.patch(f"/quotes/{quote_id}", json=patch)
        assert rejected.status_code in {400, 422}, rejected.text

    zero_hours = await admin_client.patch(f"/quotes/{quote_id}", json={"estimated_hours": "0"})
    assert zero_hours.status_code == 200, zero_hours.text
    assert Decimal(str(zero_hours.json()["estimated_hours"])) == Decimal("0.00")

    max_hours = await admin_client.patch(f"/quotes/{quote_id}", json={"estimated_hours": "9999.99"})
    assert max_hours.status_code == 200, max_hours.text
    assert Decimal(str(max_hours.json()["estimated_hours"])) == Decimal("9999.99")

    after = await admin_client.get(f"/quotes/{quote_id}")
    assert after.status_code == 200
    assert after.json()["line_items"][0]["description"] == before.json()["line_items"][0]["description"]


async def test_invoice_update_rejects_invalid_numeric_values_and_keeps_state(
    admin_client: AsyncClient,
) -> None:
    await _set_vat_registered(admin_client, True)
    contact_id = await _create_contact(admin_client)
    created = await admin_client.post("/invoices", json=_document_payload("/invoices", contact_id))
    assert created.status_code == 201, created.text
    invoice_id = str(created.json()["id"])
    before = await admin_client.get(f"/invoices/{invoice_id}")
    assert before.status_code == 200

    for patch in (
        {"vat_rate": "-0.01"},
        {"vat_rate": "NaN"},
        {"line_items": [{"description": "Labour", "quantity": "-1", "unit_price": "100.00"}]},
        {"line_items": [{"description": "Labour", "quantity": "1", "unit_price": "1e100"}]},
        {"line_items": [{"description": "   ", "quantity": "1", "unit_price": "100.00"}]},
    ):
        rejected = await admin_client.patch(f"/invoices/{invoice_id}", json=patch)
        assert rejected.status_code in {400, 422}, rejected.text

    after = await admin_client.get(f"/invoices/{invoice_id}")
    assert after.status_code == 200
    assert after.json()["line_items"][0]["description"] == before.json()["line_items"][0]["description"]


async def test_whitespace_only_contact_name_rejected(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/contacts",
        json={"name": "   ", "email": f"bad-name-{uuid4().hex[:8]}@example.com"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "create_endpoint,payload_builder",
    [
        (
            "/jobs",
            lambda contact_id: {
                "contact_id": contact_id,
                "title": "Invalid window job",
                "scheduled_start": "2026-02-01T10:00:00",
                "scheduled_end": "2026-02-01T09:00:00",
            },
        ),
        (
            "/jobs",
            lambda contact_id: {
                "contact_id": contact_id,
                "title": "Zero window job",
                "scheduled_start": "2026-02-01T10:00:00",
                "scheduled_end": "2026-02-01T10:00:00",
            },
        ),
        (
            "/appointments",
            lambda contact_id: {
                "contact_id": contact_id,
                "title": "Invalid window appointment",
                "start_at": "2026-02-01T10:00:00",
                "end_at": "2026-02-01T09:00:00",
            },
        ),
        (
            "/appointments",
            lambda contact_id: {
                "contact_id": contact_id,
                "title": "Zero window appointment",
                "start_at": "2026-02-01T10:00:00",
                "end_at": "2026-02-01T10:00:00",
            },
        ),
    ],
)
async def test_reversed_or_zero_schedule_windows_rejected_on_create(
    admin_client: AsyncClient,
    create_endpoint: str,
    payload_builder: Callable[[str], dict[str, object]],
) -> None:
    contact_id = await _create_contact(admin_client)
    response = await admin_client.post(create_endpoint, json=payload_builder(contact_id))
    assert response.status_code == 422


async def test_reversed_or_zero_schedule_windows_rejected_on_update(
    admin_client: AsyncClient,
) -> None:
    contact_id = await _create_contact(admin_client)

    created_job = await admin_client.post(
        "/jobs",
        json={
            "contact_id": contact_id,
            "title": "Valid job",
            "scheduled_start": "2026-02-01T09:00:00",
            "scheduled_end": "2026-02-01T10:00:00",
        },
    )
    assert created_job.status_code == 201, created_job.text
    job_id = created_job.json()["id"]
    for patch in (
        {"scheduled_start": "2026-02-01T10:00:00", "scheduled_end": "2026-02-01T09:00:00"},
        {"scheduled_start": "2026-02-01T10:00:00", "scheduled_end": "2026-02-01T10:00:00"},
    ):
        response = await admin_client.patch(f"/jobs/{job_id}", json=patch)
        assert response.status_code == 422

    created_appt = await admin_client.post(
        "/appointments",
        json={
            "contact_id": contact_id,
            "title": "Valid appointment",
            "start_at": "2026-02-01T12:00:00",
            "end_at": "2026-02-01T13:00:00",
        },
    )
    assert created_appt.status_code == 201, created_appt.text
    appointment_id = created_appt.json()["id"]
    for patch in (
        {"start_at": "2026-02-01T14:00:00", "end_at": "2026-02-01T13:00:00"},
        {"start_at": "2026-02-01T14:00:00", "end_at": "2026-02-01T14:00:00"},
    ):
        response = await admin_client.patch(f"/appointments/{appointment_id}", json=patch)
        assert response.status_code == 422


async def test_back_to_back_and_dst_normalized_windows_still_work(admin_client: AsyncClient) -> None:
    contact_id = await _create_contact(admin_client)

    first = await admin_client.post(
        "/appointments",
        json={
            "contact_id": contact_id,
            "title": "Back-to-back first",
            "start_at": "2026-02-02T09:00:00",
            "end_at": "2026-02-02T10:00:00",
        },
    )
    assert first.status_code == 201, first.text
    second = await admin_client.post(
        "/appointments",
        json={
            "contact_id": contact_id,
            "title": "Back-to-back second",
            "start_at": "2026-02-02T10:00:00",
            "end_at": "2026-02-02T11:00:00",
        },
    )
    assert second.status_code == 201, second.text

    dst = await admin_client.post(
        "/appointments",
        json={
            "contact_id": contact_id,
            "title": "DST normalized window",
            "start_at": "2026-03-29T00:30:00+00:00",
            "end_at": "2026-03-29T02:30:00+01:00",
        },
    )
    assert dst.status_code == 201, dst.text
    body = dst.json()
    assert body["start_at"] == "2026-03-29T00:30:00"
    assert body["end_at"] == "2026-03-29T01:30:00"
