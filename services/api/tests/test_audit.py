"""End-to-end tests for the audit-log writer wired into mutation endpoints.

These tests exercise the FULL request path (authenticated client → router →
``write_audit_log`` → ``audit_logs`` table) so a future refactor that
accidentally drops an audit call is caught.
"""

from __future__ import annotations

import pytest
from app.models import AuditLog
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _audit_actions_for_entity(
    db: AsyncSession, *, entity_type: str, entity_id: str
) -> list[str]:
    """Return the recorded ``action`` strings for one entity, oldest first."""
    result = await db.execute(
        select(AuditLog.action)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.asc())
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_contact_lifecycle_writes_audit_log(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    create = await admin_client.post(
        "/contacts", json={"name": "Audit Customer", "email": "audit@test.local"}
    )
    assert create.status_code == 201, create.text
    contact_id = create.json()["id"]

    update = await admin_client.patch(
        f"/contacts/{contact_id}", json={"phone": "07123456789"}
    )
    assert update.status_code == 200, update.text

    delete = await admin_client.delete(f"/contacts/{contact_id}")
    assert delete.status_code == 204, delete.text

    actions = await _audit_actions_for_entity(db, entity_type="contact", entity_id=contact_id)
    assert actions == ["contact.created", "contact.updated", "contact.deleted"]


@pytest.mark.asyncio
async def test_audit_log_records_actor_and_payload(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    response = await admin_client.post(
        "/contacts", json={"name": "Payload Customer", "email": "payload@test.local"}
    )
    assert response.status_code == 201, response.text
    contact_id = response.json()["id"]

    entry_result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "contact",
            AuditLog.entity_id == contact_id,
            AuditLog.action == "contact.created",
        )
    )
    entry = entry_result.scalar_one()
    assert entry.actor_id is not None, "actor_id should be the authenticated admin"
    assert entry.payload["name"] == "Payload Customer"
    assert entry.payload["email"] == "payload@test.local"
    # tenant_id is set automatically — must equal the request's tenant.
    assert str(entry.tenant_id) == admin_client.headers["X-Tenant-ID"]


@pytest.mark.asyncio
async def test_quote_lifecycle_writes_audit_log(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await admin_client.post(
        "/contacts", json={"name": "Quote Customer", "email": "quote@test.local"}
    )
    assert contact.status_code == 201
    contact_id = contact.json()["id"]

    create = await admin_client.post(
        "/quotes",
        json={
            "contact_id": contact_id,
            "title": "Test Quote",
            "line_items": [
                {
                    "description": "Test item",
                    "quantity": 1,
                    "unit_price": 100.0,
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    quote_id = create.json()["id"]

    send = await admin_client.post(f"/quotes/{quote_id}/send")
    assert send.status_code == 200, send.text

    approve = await admin_client.post(
        f"/quotes/{quote_id}/approve", json={"approved": True}
    )
    assert approve.status_code == 200, approve.text

    delete = await admin_client.delete(f"/quotes/{quote_id}")
    assert delete.status_code == 204, delete.text

    actions = await _audit_actions_for_entity(db, entity_type="quote", entity_id=quote_id)
    assert actions == [
        "quote.created",
        "quote.sent",
        "quote.approved",
        "quote.deleted",
    ]


@pytest.mark.asyncio
async def test_invoice_paid_writes_audit_log_with_total(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await admin_client.post(
        "/contacts", json={"name": "Invoice Customer", "email": "inv@test.local"}
    )
    assert contact.status_code == 201
    contact_id = contact.json()["id"]

    create = await admin_client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "line_items": [
                {"description": "Callout", "quantity": 1, "unit_price": 75.0}
            ],
        },
    )
    assert create.status_code == 201, create.text
    invoice_id = create.json()["id"]

    paid = await admin_client.post(f"/invoices/{invoice_id}/mark-paid")
    assert paid.status_code == 200, paid.text

    entry_result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "invoice",
            AuditLog.entity_id == invoice_id,
            AuditLog.action == "invoice.paid",
        )
    )
    entry = entry_result.scalar_one()
    assert entry.payload.get("total") is not None
    # Sanity: created and paid actions both present.
    actions = await _audit_actions_for_entity(db, entity_type="invoice", entity_id=invoice_id)
    assert "invoice.created" in actions
    assert "invoice.paid" in actions


@pytest.mark.asyncio
async def test_audit_logs_are_tenant_scoped(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Audit rows from tenant A must not be visible to tenant B via the API."""
    contact = await admin_client.post(
        "/contacts", json={"name": "Scoped Customer", "email": "scoped@test.local"}
    )
    assert contact.status_code == 201

    # Verify the audit row exists in tenant A's scope (RLS test on raw SQL).
    from uuid import UUID

    from app.rls import set_tenant_in_session

    tenant_a = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_a)
    rows_a = (
        await db.execute(select(AuditLog).where(AuditLog.action == "contact.created"))
    ).all()
    assert len(rows_a) >= 1

    # Switch session to a different tenant — must see zero audit rows for
    # this action because the policy filters by tenant_id.
    from uuid import uuid4

    other_tenant = uuid4()  # unrelated id — RLS just compares text equality
    await set_tenant_in_session(db, other_tenant)
    rows_b = (
        await db.execute(select(AuditLog).where(AuditLog.action == "contact.created"))
    ).all()
    assert rows_b == [], "RLS leaked audit rows from another tenant"
