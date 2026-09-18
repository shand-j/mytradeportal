"""Tests for quote lifecycle endpoints."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app.models import BillOfQuantities, Contact, Customer, Notification, Quote, QuoteRequest
from app.rls import set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import select
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


async def _create_quote(client: AsyncClient, tenant_id: str, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Initial quote",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def test_contact_notes_flow_to_quote_and_job(client: AsyncClient) -> None:
    """CRM contact notes merge into the quote's notes at creation (without
    overwriting notes typed on the creation screen) and survive the
    quote → job conversion."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    headers = {"X-Tenant-ID": tenant["id"]}
    contact_response = await client.post(
        "/contacts",
        headers=headers,
        json={"name": "Notes Carrier", "notes": "Gate code 4521; dog on site"},
    )
    assert contact_response.status_code == 201
    contact = contact_response.json()

    quote_response = await client.post(
        "/quotes",
        headers=headers,
        json={
            "contact_id": contact["id"],
            "title": "Fuse board upgrade",
            "notes": "Customer wants a Saturday visit",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert quote_response.status_code == 201, quote_response.text
    quote = quote_response.json()
    assert quote["notes"] is not None
    assert "Customer wants a Saturday visit" in quote["notes"]
    assert "Gate code 4521; dog on site" in quote["notes"]

    approve = await client.post(f"/quotes/{quote['id']}/approve", headers=headers, json={})
    assert approve.status_code == 200, approve.text

    convert = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers=headers,
        json={"notes": "Bring the long ladder"},
    )
    assert convert.status_code == 201, convert.text
    job = convert.json()
    assert "Bring the long ladder" in (job["notes"] or "")
    assert "Customer wants a Saturday visit" in (job["notes"] or "")
    assert "Gate code 4521; dog on site" in (job["notes"] or "")


async def test_update_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Updater")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "title": "Updated quote",
            "status": "sent",
            "line_items": [
                {"description": "Parts", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated quote"
    assert data["status"] == "sent"
    assert data["subtotal"] == "100.00"
    assert len(data["line_items"]) == 1
    assert data["line_items"][0]["description"] == "Parts"


async def test_send_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Sender")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/send",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["sent_at"] is not None


async def test_send_quote_links_notification_to_quote(
    client: AsyncClient, db: AsyncSession
) -> None:
    """quote_sent stores /quotes/{id} so the customer bell row deep-links."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    tenant_id = UUID(tenant["id"])
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Quote Recipient", email="qr@example.com")
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant_id,
        contact_id=contact.id,
        email="qr@example.com",
        full_name="Quote Recipient",
    )
    db.add(customer)
    await db.flush()
    quote = Quote(
        tenant_id=tenant_id,
        contact_id=contact.id,
        title="Fuse board upgrade",
        status="draft",
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
    )
    db.add(quote)
    await db.flush()
    lead = QuoteRequest(
        tenant_id=tenant_id,
        contact_id=contact.id,
        customer_id=customer.id,
        quote_id=quote.id,
        source="app",
        raw_text="Fuse board upgrade",
    )
    db.add(lead)
    await db.flush()
    quote.quote_request_id = lead.id
    await db.commit()

    response = await client.post(
        f"/quotes/{quote.id}/send",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200, response.text

    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.type == "quote_sent",
        )
    )
    assert notification is not None
    assert notification.recipient_type == "customer"
    assert notification.recipient_id == customer.id
    assert notification.link == f"/quotes/{quote.id}"


async def test_reject_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Rejecter")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.post(
        f"/quotes/{quote['id']}/reject",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


async def test_refine_quote(client: AsyncClient) -> None:
    """Refining a manual quote appends AI-regenerated lines, keeping manual ones."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Refiner")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    generated = {
        "line_items": [
            {
                "description": "Regenerated labour",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 200.00,
            }
        ],
        "notes": "",
    }
    with (
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=([], "no_index")),
        ),
        patch(
            "app.routers.quotes.generate_quote_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
    ):
        response = await client.post(
            f"/quotes/{quote['id']}/refine",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"instructions": "Regenerate the labour line"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == quote["id"]
    descriptions = [li["description"] for li in body["line_items"]]
    # The original manual line is preserved; the AI line is appended.
    assert "Labour" in descriptions
    assert "Regenerated labour" in descriptions
    ai_line = next(li for li in body["line_items"] if li["description"] == "Regenerated labour")
    assert ai_line["ai_generated"] is True
    assert body["ai_generated"] is True


async def test_delete_quote(client: AsyncClient) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Deleter")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    response = await client.delete(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert response.status_code == 204

    get_response = await client.get(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
    )
    assert get_response.status_code == 404


async def test_list_quotes_handles_malformed_boq_json(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Legacy Data")
    quote_data = await _create_quote(client, tenant["id"], contact["id"])

    quote = (
        await db.execute(
            select(Quote).where(Quote.id == quote_data["id"], Quote.tenant_id == tenant["id"])
        )
    ).scalar_one()
    quote.bill_of_quantities = BillOfQuantities(
        tenant_id=quote.tenant_id,
        quote_id=quote.id,
        status="draft",
        subtotal=Decimal("100.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
        confidence=0.85,
        warnings=[],
        regulatory_citations=[],
        compliance_warnings=[],
        customer_summary_lines=[
            {"description": "Missing total"},
            {"description": "Valid line", "total": "100.00"},
            "bad-entry",
        ],
        margin_indicator={},
        retrieval_evidence={},
        line_items=[],
    )
    await db.commit()

    response = await client.get("/quotes", headers={"X-Tenant-ID": tenant["id"]})
    assert response.status_code == 200

    fetched_quote = response.json()[0]
    assert fetched_quote["id"] == quote_data["id"]
    assert fetched_quote["bill_of_quantities"]["customer_summary_lines"] == [
        {"description": "Valid line", "total": "100.00"}
    ]
    assert fetched_quote["bill_of_quantities"]["margin_indicator"] is None
    assert fetched_quote["bill_of_quantities"]["retrieval_evidence"] is None


async def test_list_quotes_handles_null_valued_boq_json(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """Pre-existing BoQ rows may store partial JSONB with explicit ``null`` values.

    Older code versions persisted ``margin_indicator`` / ``retrieval_evidence``
    payloads where individual keys hold ``null``. Because the nested Read models
    expose non-nullable fields with defaults, an explicit ``null`` (as opposed to
    a missing key) must not break serialization of the quotes list.
    """
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Quote Null Data")
    quote_data = await _create_quote(client, tenant["id"], contact["id"])

    quote = (
        await db.execute(
            select(Quote).where(Quote.id == quote_data["id"], Quote.tenant_id == tenant["id"])
        )
    ).scalar_one()
    quote.bill_of_quantities = BillOfQuantities(
        tenant_id=quote.tenant_id,
        quote_id=quote.id,
        status="draft",
        subtotal=Decimal("100.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
        confidence=0.85,
        warnings=[],
        regulatory_citations=[],
        compliance_warnings=[],
        customer_summary_lines=[],
        # Partial payloads with explicit nulls, as written by older versions.
        margin_indicator={"subtotal": None, "estimated_margin_percent": None},
        retrieval_evidence={
            "knowledge_available": None,
            "top_relevance_score": None,
            "quality_score": None,
            "job_types": None,
            "citations_used": 3,
        },
        line_items=[],
    )
    await db.commit()

    response = await client.get("/quotes", headers={"X-Tenant-ID": tenant["id"]})
    assert response.status_code == 200

    boq = response.json()[0]["bill_of_quantities"]
    # All-null margin payload collapses to absent.
    assert boq["margin_indicator"] is None
    # Null keys fall back to model defaults; non-null keys are preserved.
    assert boq["retrieval_evidence"] is not None
    assert boq["retrieval_evidence"]["knowledge_available"] is True
    assert boq["retrieval_evidence"]["top_relevance_score"] == 0.0
    assert boq["retrieval_evidence"]["job_types"] == []
    assert boq["retrieval_evidence"]["citations_used"] == 3


async def test_refine_drops_duplicated_manual_lines(client: AsyncClient) -> None:
    """If the LLM re-emits a preserved manual line, refine drops the duplicate."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Refine Deduper")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    manual_line = quote["line_items"][0]

    generated = {
        "line_items": [
            {
                # Exact duplicate of the manual line — must be dropped.
                "description": manual_line["description"],
                "kind": "labour",
                "quantity": manual_line["quantity"],
                "unit_price": manual_line["unit_price"],
            },
            {
                "description": "Regenerated labour",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 200.00,
            },
        ],
        "notes": "",
    }
    with (
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=([], "no_index")),
        ),
        patch(
            "app.routers.quotes.generate_quote_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
    ):
        response = await client.post(
            f"/quotes/{quote['id']}/refine",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"instructions": "Regenerate"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    manual_desc = manual_line["description"]
    assert [li["description"] for li in body["line_items"]].count(manual_desc) == 1
    assert any("duplicate" in w.lower() for w in body["ai_warnings"]), body["ai_warnings"]


async def test_update_quote_preserves_ai_generated_flags(client: AsyncClient) -> None:
    """Round-tripping line items through PATCH must keep ai_generated lineage."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Lineage Keeper")
    quote = await _create_quote(client, tenant["id"], contact["id"])
    line = quote["line_items"][0]

    response = await client.patch(
        f"/quotes/{quote['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "line_items": [
                {
                    "description": line["description"],
                    "quantity": line["quantity"],
                    "unit_price": line["unit_price"],
                    "ai_generated": True,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["line_items"][0]["ai_generated"] is True
    assert body["ai_generated"] is True


async def test_convert_approved_quote_to_job(client: AsyncClient, db: AsyncSession) -> None:
    """quote → job: approved quotes convert once, carrying the customer's
    reconfirmed dates into the job notes."""
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Job Convert")
    quote = await _create_quote(client, tenant["id"], contact["id"])

    # Not approved yet → 400.
    early = await client.post(
        f"/quotes/{quote['id']}/convert-to-job", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert early.status_code == 400

    patched = await client.post(
        f"/quotes/{quote['id']}/approve",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert patched.status_code == 200, patched.text
    # Simulate the customer's reconfirmed dates landing on acceptance.
    from app.models import Quote as QuoteModel
    from sqlalchemy import update as sa_update

    await db.execute(
        sa_update(QuoteModel)
        .where(QuoteModel.id == UUID(quote["id"]))
        .values(accepted_dates=["Fri 12 Sep", "Mon 15 Sep"])
    )
    await db.commit()

    response = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": "2026-09-12T09:00:00", "scheduled_end": "2026-09-12T17:00:00"},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["quote_id"] == quote["id"]
    assert job["status"] == "scheduled"
    assert "Fri 12 Sep" in (job["notes"] or "")

    # Second conversion → 409.
    again = await client.post(
        f"/quotes/{quote['id']}/convert-to-job", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert again.status_code == 409


async def test_convert_quote_to_job_carries_quote_request_photos(
    client: AsyncClient, db: AsyncSession
) -> None:
    """quote → job: photos from the quote request land on the job record.

    Covers both storage shapes: ``MediaAsset`` rows (customer-app uploads) and
    the intake form's ``media_urls`` JSONB, which previously never made it onto
    the job. A URL present in both is carried once.
    """
    tenant = await _create_tenant(client, f"quote-{uuid4().hex[:8]}")
    headers = {"X-Tenant-ID": tenant["id"]}
    contact = await _create_contact(client, tenant["id"], "Photo Convert")

    from app.models import Quote as QuoteModel
    from sqlalchemy import update as sa_update

    intake_url = f"/files/download?key=tenants/{tenant['id']}/intake/{uuid4().hex}/site.jpg"
    shared_url = f"https://api.example.com/files/download?key=tenants/{tenant['id']}/shared.jpg"
    app_url = f"https://api.example.com/files/download?key=tenants/{tenant['id']}/app.jpg"

    lead = await client.post(
        "/quote-requests",
        headers=headers,
        json={
            "contact_id": contact["id"],
            "raw_text": "Fuse board upgrade",
            "media_urls": [intake_url, shared_url],
        },
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]

    # Customer-app style upload: one asset duplicating a media_url, one unique.
    for url in (shared_url, app_url):
        attached = await client.post(
            f"/quote-requests/{lead_id}/media",
            headers=headers,
            json={"file_url": url, "source": "customer_app"},
        )
        assert attached.status_code == 201, attached.text

    quote = await _create_quote(client, tenant["id"], contact["id"])
    await db.execute(
        sa_update(QuoteModel)
        .where(QuoteModel.id == UUID(quote["id"]))
        .values(quote_request_id=UUID(lead_id))
    )
    await db.commit()

    approved = await client.post(f"/quotes/{quote['id']}/approve", headers=headers, json={})
    assert approved.status_code == 200, approved.text

    converted = await client.post(f"/quotes/{quote['id']}/convert-to-job", headers=headers)
    assert converted.status_code == 201, converted.text
    job = converted.json()
    assert sorted(job["photos"]) == sorted([intake_url, shared_url, app_url])

    # The photos survive on a fresh read of the job record.
    fetched = await client.get(f"/jobs/{job['id']}", headers=headers)
    assert fetched.status_code == 200
    assert sorted(fetched.json()["photos"]) == sorted([intake_url, shared_url, app_url])
