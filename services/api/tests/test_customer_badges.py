"""CRM trust badges + customer blocking tests (beta backlog N26).

Covers the auto badge rules (Late Payer / Non-payer / Time Waster), manual
override semantics (override wins, clearing returns to auto), and the block
enforcement points (customer login + quote-request creation).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import Customer, Invoice, Quote
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_contact(
    admin_client: AsyncClient, name: str = "Badge Customer"
) -> dict[str, Any]:
    response = await admin_client.post("/contacts", json={"name": name})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _invoice(
    tenant_id: UUID,
    contact_id: UUID,
    *,
    status: str = "sent",
    due_date: datetime | None = None,
    paid_at: datetime | None = None,
) -> Invoice:
    return Invoice(
        tenant_id=tenant_id,
        contact_id=contact_id,
        invoice_number=f"INV-{uuid4().hex[:8]}",
        status=status,
        due_date=due_date,
        paid_at=paid_at,
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
    )


def _quote(tenant_id: UUID, contact_id: UUID, *, status: str = "sent") -> Quote:
    return Quote(
        tenant_id=tenant_id,
        contact_id=contact_id,
        title=f"Quote {uuid4().hex[:6]}",
        status=status,
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("20.00"),
        total=Decimal("120.00"),
    )


async def _get_contact(admin_client: AsyncClient, contact_id: str) -> dict[str, Any]:
    response = await admin_client.get(f"/contacts/{contact_id}")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# ---------------------------------------------------------------------------
# Auto badge rules
# ---------------------------------------------------------------------------


async def test_no_history_no_badges(admin_client: AsyncClient) -> None:
    contact = await _create_contact(admin_client)
    body = await _get_contact(admin_client, contact["id"])
    assert body["badges"] == []
    assert body["auto_badges"] == []
    assert body["badge_overrides"] == {}
    assert body["is_blocked"] is False


async def test_late_payer_badge_after_two_late_payments(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await _create_contact(admin_client)
    tenant_id = UUID(contact["tenant_id"])
    contact_id = UUID(contact["id"])
    await set_tenant_in_session(db, tenant_id)

    due = datetime.utcnow() - timedelta(days=20)
    # Two invoices paid after the due date -> Late Payer.
    db.add(
        _invoice(
            tenant_id, contact_id, status="paid", due_date=due, paid_at=due + timedelta(days=5)
        )
    )
    db.add(
        _invoice(
            tenant_id, contact_id, status="paid", due_date=due, paid_at=due + timedelta(days=9)
        )
    )
    # One paid on time must not dilute the rule.
    db.add(_invoice(tenant_id, contact_id, status="paid", due_date=due, paid_at=due))
    await db.flush()

    body = await _get_contact(admin_client, contact["id"])
    assert "late_payer" in body["auto_badges"]
    assert "late_payer" in body["badges"]


async def test_single_late_payment_does_not_badge(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await _create_contact(admin_client)
    tenant_id = UUID(contact["tenant_id"])
    contact_id = UUID(contact["id"])
    await set_tenant_in_session(db, tenant_id)

    due = datetime.utcnow() - timedelta(days=20)
    db.add(
        _invoice(
            tenant_id, contact_id, status="paid", due_date=due, paid_at=due + timedelta(days=5)
        )
    )
    await db.flush()

    body = await _get_contact(admin_client, contact["id"])
    assert body["auto_badges"] == []


async def test_non_payer_badge_for_invoice_unpaid_well_past_due(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await _create_contact(admin_client)
    tenant_id = UUID(contact["tenant_id"])
    contact_id = UUID(contact["id"])
    await set_tenant_in_session(db, tenant_id)

    # Issued 40 days ago, due 40 days ago, still "sent" (unpaid).
    db.add(
        _invoice(
            tenant_id,
            contact_id,
            status="sent",
            due_date=datetime.utcnow() - timedelta(days=40),
        )
    )
    # Recently-due unpaid invoice is inside the grace window -> no badge alone.
    db.add(
        _invoice(
            tenant_id,
            contact_id,
            status="sent",
            due_date=datetime.utcnow() - timedelta(days=5),
        )
    )
    await db.flush()

    body = await _get_contact(admin_client, contact["id"])
    assert "non_payer" in body["auto_badges"]
    assert "non_payer" in body["badges"]


async def test_recent_unpaid_invoice_does_not_badge(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await _create_contact(admin_client)
    tenant_id = UUID(contact["tenant_id"])
    contact_id = UUID(contact["id"])
    await set_tenant_in_session(db, tenant_id)

    db.add(
        _invoice(
            tenant_id,
            contact_id,
            status="sent",
            due_date=datetime.utcnow() - timedelta(days=10),
        )
    )
    await db.flush()

    body = await _get_contact(admin_client, contact["id"])
    assert body["auto_badges"] == []


async def test_time_waster_badge_after_three_unanswered_quotes(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await _create_contact(admin_client)
    tenant_id = UUID(contact["tenant_id"])
    contact_id = UUID(contact["id"])
    await set_tenant_in_session(db, tenant_id)

    db.add(_quote(tenant_id, contact_id, status="sent"))
    db.add(_quote(tenant_id, contact_id, status="sent"))
    db.add(_quote(tenant_id, contact_id, status="expired"))
    await db.flush()

    body = await _get_contact(admin_client, contact["id"])
    assert "time_waster" in body["auto_badges"]
    assert "time_waster" in body["badges"]


async def test_time_waster_not_set_with_engagement_or_few_quotes(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    engaged = await _create_contact(admin_client, name="Engaged Customer")
    tenant_id = UUID(engaged["tenant_id"])
    await set_tenant_in_session(db, tenant_id)
    engaged_id = UUID(engaged["id"])
    db.add(_quote(tenant_id, engaged_id, status="sent"))
    db.add(_quote(tenant_id, engaged_id, status="expired"))
    # A rejection still counts as engagement — the customer replied.
    db.add(_quote(tenant_id, engaged_id, status="rejected"))
    await db.flush()
    body = await _get_contact(admin_client, engaged["id"])
    assert "time_waster" not in body["auto_badges"]

    few = await _create_contact(admin_client, name="Two Quote Customer")
    few_id = UUID(few["id"])
    db.add(_quote(tenant_id, few_id, status="sent"))
    db.add(_quote(tenant_id, few_id, status="expired"))
    await db.flush()
    body = await _get_contact(admin_client, few["id"])
    assert "time_waster" not in body["auto_badges"]


# ---------------------------------------------------------------------------
# Manual overrides
# ---------------------------------------------------------------------------


async def test_manual_override_wins_and_clear_returns_to_auto(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact = await _create_contact(admin_client)
    tenant_id = UUID(contact["tenant_id"])
    contact_id = UUID(contact["id"])
    await set_tenant_in_session(db, tenant_id)

    due = datetime.utcnow() - timedelta(days=20)
    db.add(
        _invoice(
            tenant_id, contact_id, status="paid", due_date=due, paid_at=due + timedelta(days=5)
        )
    )
    db.add(
        _invoice(
            tenant_id, contact_id, status="paid", due_date=due, paid_at=due + timedelta(days=9)
        )
    )
    await db.flush()

    # Force the auto badge off — manual override wins.
    off = await admin_client.patch(
        f"/contacts/{contact['id']}", json={"badge_overrides": {"late_payer": False}}
    )
    assert off.status_code == 200, off.text
    assert off.json()["badge_overrides"] == {"late_payer": False}
    assert "late_payer" in off.json()["auto_badges"]
    assert "late_payer" not in off.json()["badges"]

    # Force a badge on with no underlying data.
    on = await admin_client.patch(
        f"/contacts/{contact['id']}", json={"badge_overrides": {"time_waster": True}}
    )
    assert on.status_code == 200, on.text
    assert on.json()["badge_overrides"] == {"late_payer": False, "time_waster": True}
    assert "time_waster" in on.json()["badges"]
    assert "time_waster" not in on.json()["auto_badges"]

    # Clearing the override returns the badge to the auto decision.
    cleared = await admin_client.patch(
        f"/contacts/{contact['id']}", json={"badge_overrides": {"late_payer": None}}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["badge_overrides"] == {"time_waster": True}
    assert "late_payer" in cleared.json()["badges"]


async def test_unknown_badge_override_rejected(admin_client: AsyncClient) -> None:
    contact = await _create_contact(admin_client)
    response = await admin_client.patch(
        f"/contacts/{contact['id']}", json={"badge_overrides": {"late_payr": True}}
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("unknown_badge:")


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------


async def _register_customer(
    admin_client: AsyncClient, db: AsyncSession
) -> tuple[dict[str, Any], Customer]:
    """Create a customer account (with password) linked to a CRM contact."""
    contact = await _create_contact(admin_client, name="Portal Customer")
    tenant_id = UUID(contact["tenant_id"])
    contact_id = UUID(contact["id"])
    await set_tenant_in_session(db, tenant_id)
    customer = Customer(
        tenant_id=tenant_id,
        contact_id=contact_id,
        email=f"blocked-{uuid4().hex[:6]}@example.com",
        full_name="Portal Customer",
        password_hash=get_password_hash("customer-pass-123"),
        is_active=True,
    )
    db.add(customer)
    await db.flush()
    return contact, customer


async def test_block_and_unblock_round_trip(admin_client: AsyncClient) -> None:
    contact = await _create_contact(admin_client)

    blocked = await admin_client.post(
        f"/contacts/{contact['id']}/block", json={"reason": "Abusive on the phone"}
    )
    assert blocked.status_code == 200, blocked.text
    body = blocked.json()
    assert body["is_blocked"] is True
    assert body["blocked_at"] is not None
    assert body["blocked_reason"] == "Abusive on the phone"

    fetched = await _get_contact(admin_client, contact["id"])
    assert fetched["is_blocked"] is True

    # The list endpoint surfaces the block state for CRM visibility.
    listed = await admin_client.get("/contacts")
    assert listed.status_code == 200
    row = next(c for c in listed.json() if c["id"] == contact["id"])
    assert row["is_blocked"] is True

    unblocked = await admin_client.post(f"/contacts/{contact['id']}/unblock")
    assert unblocked.status_code == 200, unblocked.text
    body = unblocked.json()
    assert body["is_blocked"] is False
    assert body["blocked_at"] is None
    assert body["blocked_reason"] is None


async def test_blocked_customer_cannot_log_in(
    client: AsyncClient, admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact, customer = await _register_customer(admin_client, db)
    login_payload = {"email": customer.email, "password": "customer-pass-123"}

    ok = await client.post("/customer/login", json=login_payload)
    assert ok.status_code == 200, ok.text

    blocked = await admin_client.post(f"/contacts/{contact['id']}/block", json={})
    assert blocked.status_code == 200, blocked.text

    refused = await client.post("/customer/login", json=login_payload)
    assert refused.status_code == 403
    assert refused.json()["detail"].startswith("customer_blocked:")

    # Wrong-password attempts still get the generic 401 (no enumeration).
    bad = await client.post(
        "/customer/login", json={"email": customer.email, "password": "wrong-password"}
    )
    assert bad.status_code == 401

    await admin_client.post(f"/contacts/{contact['id']}/unblock")
    again = await client.post("/customer/login", json=login_payload)
    assert again.status_code == 200, again.text


async def test_blocked_customer_cannot_create_quote_request(
    client: AsyncClient, admin_client: AsyncClient, db: AsyncSession
) -> None:
    contact, customer = await _register_customer(admin_client, db)

    payload = {"customer_id": str(customer.id), "raw_text": "New consumer unit"}
    ok = await admin_client.post("/quote-requests", json=payload)
    assert ok.status_code == 201, ok.text

    await admin_client.post(f"/contacts/{contact['id']}/block", json={})
    refused = await admin_client.post("/quote-requests", json=payload)
    assert refused.status_code == 403
    assert refused.json()["detail"].startswith("customer_blocked:")

    await admin_client.post(f"/contacts/{contact['id']}/unblock")
    again = await admin_client.post("/quote-requests", json=payload)
    assert again.status_code == 201, again.text
