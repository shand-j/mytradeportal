"""Tests for the customer email sequence with per-tenant magic links.

Sequence under test: quote ready (magic link) → acceptance confirmation →
booking confirmed on scheduling → invoice sent (magic link) → payment
received + review prompt. All sends are mocked — send_customer_email/send_email
calls are captured, never delivered.

The magic-link helper (``app.email.resolve_customer_magic_link``) wraps
``app.portal_links.magic_link_url``; tests stub that issuer so the helper's
Customer-row lookup runs for real without minting portal tokens.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app import email as email_module
from app.database import engine
from app.email_templates import (
    booking_confirmed as booking_confirmed_template,
)
from app.email_templates import (
    chat_message as chat_message_template,
)
from app.email_templates import (
    invoice_sent as invoice_sent_template,
)
from app.email_templates import (
    payment_received as payment_received_template,
)
from app.email_templates import (
    quote_accepted as quote_accepted_template,
)
from app.email_templates import (
    quote_ready as quote_ready_template,
)
from app.models import Contact, Customer, Invoice, PushToken, Quote, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.scheduler import run_reminder_tick
from app.security import get_password_hash
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_stripe_webhooks import (
    _patch_construct,
    _post_event,
    payment_intent_succeeded_event,
)

pytestmark = pytest.mark.asyncio

MAGIC_URL = "https://acme.mytradeportal.co.uk/auth/magic?token=tok-abc123&next=/quotes/x"
DOC_URL_MARKER = "/quote/"  # PUBLIC_DOCS_BASE_URL + kind + raw token


class _EmailRecorder:
    """Stand-in for send_customer_email that records calls (db arg dropped)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, db: Any = None, **kwargs: Any) -> bool:
        self.calls.append(kwargs)
        return True


def _stub_portal_links(monkeypatch: MonkeyPatch, url: str = MAGIC_URL) -> AsyncMock:
    """Stub ``app.email.magic_link_url`` (the portal_links token issuer)."""
    magic_link_url = AsyncMock(return_value=url)
    monkeypatch.setattr(email_module, "magic_link_url", magic_link_url)
    return magic_link_url


async def _create_tenant(
    db: AsyncSession, slug: str, settings: dict[str, Any] | None = None
) -> Tenant:
    await bypass_rls_in_session(db)
    tenant = Tenant(slug=slug, name=f"{slug} Electrical", settings=settings or {})
    db.add(tenant)
    await db.flush()
    return tenant


async def _create_contact(
    db: AsyncSession, tenant: Tenant, email: str | None = "homeowner@example.com"
) -> Contact:
    await set_tenant_in_session(db, tenant.id)
    contact = Contact(tenant_id=tenant.id, name="Amy Homeowner", email=email)
    db.add(contact)
    await db.flush()
    return contact


async def _create_customer(db: AsyncSession, tenant: Tenant, contact: Contact) -> Customer:
    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=contact.email or "homeowner@example.com",
        full_name="Amy Homeowner",
        is_active=True,
    )
    db.add(customer)
    await db.flush()
    return customer


async def _create_quote_via_api(
    client: AsyncClient, tenant_id: str, contact_id: str
) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "contact_id": contact_id,
            "title": "Fuse board replacement",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


# ---------------------------------------------------------------------------
# Templates: quote_ready / invoice_sent magic-link primary, doc link secondary
# ---------------------------------------------------------------------------


async def test_quote_ready_magic_link_primary_doc_secondary() -> None:
    _, html, text = quote_ready_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        quote_title="Fuse board",
        quote_total="£120.00",
        view_url="https://mytradeportal.co.uk/quote/doctoken",
        portal_url=MAGIC_URL,
    )
    assert MAGIC_URL in html
    assert MAGIC_URL in text
    assert "https://mytradeportal.co.uk/quote/doctoken" in html
    # Magic link is the primary CTA; the doc link is the secondary fallback.
    assert html.index(MAGIC_URL) < html.index("https://mytradeportal.co.uk/quote/doctoken")
    assert "read-only copy" in html


async def test_quote_ready_without_magic_link_keeps_doc_cta() -> None:
    _, html, text = quote_ready_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        quote_title="Fuse board",
        quote_total="£120.00",
        view_url="https://mytradeportal.co.uk/quote/doctoken",
    )
    assert "https://mytradeportal.co.uk/quote/doctoken" in html
    assert "https://mytradeportal.co.uk/quote/doctoken" in text
    assert "read-only copy" not in html


async def test_invoice_sent_magic_link_primary_doc_secondary() -> None:
    _, html, text = invoice_sent_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        invoice_number="INV-001",
        invoice_total="£600.00",
        view_url="https://mytradeportal.co.uk/invoice/doctoken",
        portal_url=MAGIC_URL,
    )
    assert MAGIC_URL in html
    assert MAGIC_URL in text
    assert "https://mytradeportal.co.uk/invoice/doctoken" in html
    assert html.index(MAGIC_URL) < html.index("https://mytradeportal.co.uk/invoice/doctoken")
    assert "read-only copy" in html


async def test_invoice_sent_without_magic_link_unchanged() -> None:
    _, html, text = invoice_sent_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        invoice_number="INV-001",
        invoice_total="£600.00",
        view_url="https://mytradeportal.co.uk/invoice/doctoken",
    )
    assert "https://mytradeportal.co.uk/invoice/doctoken" in html
    assert "https://mytradeportal.co.uk/invoice/doctoken" in text
    assert "read-only copy" not in html


async def test_quote_accepted_pending_booking_copy_and_magic_link() -> None:
    _, html, text = quote_accepted_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        quote_title="Fuse board",
        quote_total="£120.00",
        portal_url=MAGIC_URL,
    )
    assert "pending" in html
    assert "pending" in text
    assert "as soon as" in text
    assert MAGIC_URL in html
    # Backward compatible without the magic link: copy still stands.
    _, html_plain, text_plain = quote_accepted_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        quote_title="Fuse board",
        quote_total="£120.00",
    )
    assert "pending" in html_plain
    assert "pending" in text_plain


async def test_booking_confirmed_renders_visit_details() -> None:
    _, html, text = booking_confirmed_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        job_title="Fuse board replacement",
        visit_date="Monday 21 September 2026",
        time_window="09:00 - 11:00",
        address="1 Millbank, SW1P 3AA",
        tradie_name="Acme Electrical",
        tradie_phone="07700 900123",
    )
    for fragment in (
        "Monday 21 September 2026",
        "09:00 - 11:00",
        "1 Millbank, SW1P 3AA",
        "Acme Electrical",
        "07700 900123",
        "reply to this email",
    ):
        assert fragment in html
        assert fragment in text


async def test_payment_received_with_review_prompt() -> None:
    _, html, text = payment_received_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        invoice_number="INV-001",
        amount_paid="£600.00",
        paid_date="14 Sep 2026",
        review_url="https://g.page/r/acme-review",
    )
    assert "£600.00" in html
    assert "INV-001" in html
    assert "14 Sep 2026" in html
    assert "How did we do?" in html
    assert "https://g.page/r/acme-review" in html
    assert "Leave Acme Electrical a review" in text
    # Ours is the confirmation; Stripe's own receipt is acknowledged.
    assert "Stripe" in text


async def test_payment_received_without_review_url_has_no_review_block() -> None:
    _, html, text = payment_received_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        invoice_number="INV-001",
        amount_paid="£600.00",
        paid_date="14 Sep 2026",
    )
    assert "How did we do?" not in html
    assert "review" not in text.lower().replace("for your records", "")
    assert "£600.00" in html


# ---------------------------------------------------------------------------
# Quote send: magic link when a Customer row exists, doc token otherwise
# ---------------------------------------------------------------------------


async def test_quote_send_email_contains_magic_link_when_customer_exists(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant = await _create_tenant(db, f"qmail-{uuid4().hex[:8]}")
    contact = await _create_contact(db, tenant)
    await _create_customer(db, tenant, contact)
    quote = await _create_quote_via_api(client, str(tenant.id), str(contact.id))

    magic_link_url = _stub_portal_links(monkeypatch)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.quotes.send_customer_email", recorder)

    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": str(tenant.id)}
    )

    assert response.status_code == 200, response.text
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["template"] == "quote_ready"
    assert MAGIC_URL in call["html_body"]
    # The doc token is still minted and offered as the view-only fallback.
    assert DOC_URL_MARKER in call["html_body"]
    assert "read-only copy" in call["html_body"]
    magic_link_url.assert_awaited_once()
    assert magic_link_url.await_args is not None
    assert magic_link_url.await_args.args[3] == f"/quotes/{quote['id']}"


async def test_quote_send_email_falls_back_to_doc_link_without_customer(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant = await _create_tenant(db, f"qmail-{uuid4().hex[:8]}")
    contact = await _create_contact(db, tenant)
    quote = await _create_quote_via_api(client, str(tenant.id), str(contact.id))

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.quotes.send_customer_email", recorder)

    response = await client.post(
        f"/quotes/{quote['id']}/send", headers={"X-Tenant-ID": str(tenant.id)}
    )

    assert response.status_code == 200, response.text
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert DOC_URL_MARKER in call["html_body"]
    assert "auth/magic" not in call["html_body"]
    assert "read-only copy" not in call["html_body"]


async def test_invoice_send_email_contains_magic_link_when_customer_exists(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant = await _create_tenant(db, f"imail-{uuid4().hex[:8]}")
    contact = await _create_contact(db, tenant)
    await _create_customer(db, tenant, contact)
    create = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": str(tenant.id)},
        json={
            "contact_id": str(contact.id),
            "line_items": [
                {"description": "Labour", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert create.status_code == 201, create.text
    invoice = create.json()

    magic_link_url = _stub_portal_links(monkeypatch)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.invoices.send_customer_email", recorder)

    response = await client.post(
        f"/invoices/{invoice['id']}/send", headers={"X-Tenant-ID": str(tenant.id)}
    )

    assert response.status_code == 200, response.text
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert MAGIC_URL in call["html_body"]
    assert "/invoice/" in call["html_body"]
    assert "read-only copy" in call["html_body"]
    magic_link_url.assert_awaited_once()
    assert magic_link_url.await_args is not None
    assert magic_link_url.await_args.args[3] == f"/invoices/{invoice['id']}"


async def test_invoice_send_email_falls_back_to_doc_link_without_customer(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant = await _create_tenant(db, f"imail-{uuid4().hex[:8]}")
    contact = await _create_contact(db, tenant)
    create = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": str(tenant.id)},
        json={
            "contact_id": str(contact.id),
            "line_items": [
                {"description": "Labour", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert create.status_code == 201, create.text
    invoice = create.json()

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.invoices.send_customer_email", recorder)

    response = await client.post(
        f"/invoices/{invoice['id']}/send", headers={"X-Tenant-ID": str(tenant.id)}
    )

    assert response.status_code == 200, response.text
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert "/invoice/" in call["html_body"]
    assert "auth/magic" not in call["html_body"]
    assert "read-only copy" not in call["html_body"]


# ---------------------------------------------------------------------------
# Booking confirmed: fires on schedule PATCH, not on unrelated PATCHes
# ---------------------------------------------------------------------------


async def _create_tenant_via_api(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def test_booking_confirmed_email_fires_on_schedule_patch(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant = await _create_tenant_via_api(client, f"book-{uuid4().hex[:8]}")
    await set_tenant_in_session(db, UUID(tenant["id"]))
    tenant_row = await db.get(Tenant, UUID(tenant["id"]))
    assert tenant_row is not None
    tenant_row.settings = {"email": "sparks@example.com", "phone": "07700 900123"}
    await db.flush()

    contact_response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "name": "Amy Homeowner",
            "email": "amy@example.com",
            "address": "1 Millbank",
            "postcode": "SW1P 3AA",
        },
    )
    assert contact_response.status_code == 201, contact_response.text
    contact = contact_response.json()

    job_response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    assert job_response.status_code == 201, job_response.text
    job = job_response.json()

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.jobs.send_customer_email", recorder)

    start = datetime(2026, 9, 21, 9, 0)
    end = datetime(2026, 9, 21, 11, 0)
    patch = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "scheduled_start": start.isoformat(),
            "scheduled_end": end.isoformat(),
        },
    )

    assert patch.status_code == 200, patch.text
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["event"] == "booking_confirmed"
    assert call["template"] == "booking_confirmed"
    assert call["to_email"] == "amy@example.com"
    # Tenant-branded: display name + Reply-To so "reply to change" reaches the tradie.
    assert call["from_name"] == tenant["name"]
    assert call["reply_to"] == "sparks@example.com"
    html = call["html_body"]
    assert start.strftime("%A %d %B %Y") in html
    assert "09:00 - 11:00" in html
    assert "1 Millbank, SW1P 3AA" in html
    assert "07700 900123" in html
    assert "reply to this email" in html


async def test_booking_confirmed_email_not_fired_on_unrelated_patch(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant = await _create_tenant_via_api(client, f"book-{uuid4().hex[:8]}")
    contact_response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"name": "Amy Homeowner", "email": "amy@example.com"},
    )
    assert contact_response.status_code == 201, contact_response.text
    contact = contact_response.json()
    job_response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    assert job_response.status_code == 201, job_response.text
    job = job_response.json()

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.jobs.send_customer_email", recorder)

    patch = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"notes": "Customer has a dog"},
    )

    assert patch.status_code == 200, patch.text
    assert recorder.calls == []

    # Rescheduling fires a fresh confirmation (one per scheduling change).
    start = datetime(2026, 9, 22, 13, 0)
    first = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": start.isoformat()},
    )
    assert first.status_code == 200, first.text
    assert len(recorder.calls) == 1
    assert "from 13:00" in recorder.calls[0]["html_body"]


async def _booking_tenant_with_contact(
    client: AsyncClient, db: AsyncSession
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Tenant (branded settings) + contact, shared by the create/convert tests."""
    tenant = await _create_tenant_via_api(client, f"book-{uuid4().hex[:8]}")
    await set_tenant_in_session(db, UUID(tenant["id"]))
    tenant_row = await db.get(Tenant, UUID(tenant["id"]))
    assert tenant_row is not None
    tenant_row.settings = {"email": "sparks@example.com", "phone": "07700 900123"}
    await db.flush()
    contact_response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "name": "Amy Homeowner",
            "email": "amy@example.com",
            "address": "1 Millbank",
            "postcode": "SW1P 3AA",
        },
    )
    assert contact_response.status_code == 201, contact_response.text
    return tenant, contact_response.json()


async def test_booking_confirmed_email_fires_once_on_create_with_schedule(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Direct job creation on a real slot emails the confirmation (Fixes #116)."""
    tenant, contact = await _booking_tenant_with_contact(client, db)

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.jobs.send_customer_email", recorder)

    start = datetime(2026, 9, 21, 9, 0)
    job_response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board swap",
            "scheduled_start": start.isoformat(),
            "scheduled_end": (start + timedelta(hours=2)).isoformat(),
        },
    )
    assert job_response.status_code == 201, job_response.text
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["event"] == "booking_confirmed"
    assert call["template"] == "booking_confirmed"
    assert call["to_email"] == "amy@example.com"
    assert call["from_name"] == tenant["name"]
    assert call["reply_to"] == "sparks@example.com"
    assert start.strftime("%A %d %B %Y") in call["html_body"]
    assert "09:00 - 11:00" in call["html_body"]


async def test_booking_confirmed_email_not_sent_on_create_without_schedule(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """An unscheduled job create sends nothing (Fixes #116)."""
    tenant, contact = await _booking_tenant_with_contact(client, db)

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.jobs.send_customer_email", recorder)

    job_response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    assert job_response.status_code == 201, job_response.text
    assert recorder.calls == []


async def test_booking_confirmed_email_fires_once_on_convert_to_job_with_schedule(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Quote → job conversion on a real slot emails the confirmation (Fixes #116)."""
    tenant, contact = await _booking_tenant_with_contact(client, db)
    quote_response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board swap",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert quote_response.status_code == 201, quote_response.text
    quote = quote_response.json()
    approve = await client.post(
        f"/quotes/{quote['id']}/approve",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert approve.status_code == 200, approve.text

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.jobs.send_customer_email", recorder)

    start = datetime(2026, 9, 22, 9, 0)
    convert = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "scheduled_start": start.isoformat(),
            "scheduled_end": (start + timedelta(hours=2)).isoformat(),
        },
    )
    assert convert.status_code == 201, convert.text
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["event"] == "booking_confirmed"
    assert call["to_email"] == "amy@example.com"
    assert call["from_name"] == tenant["name"]
    assert start.strftime("%A %d %B %Y") in call["html_body"]


async def test_booking_confirmed_email_not_sent_on_convert_without_schedule(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Conversion without accepted dates or an explicit start sends nothing."""
    tenant, contact = await _booking_tenant_with_contact(client, db)
    quote_response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Fuse board swap",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "100.00"},
            ],
        },
    )
    assert quote_response.status_code == 201, quote_response.text
    quote = quote_response.json()
    approve = await client.post(
        f"/quotes/{quote['id']}/approve",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert approve.status_code == 200, approve.text

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.jobs.send_customer_email", recorder)

    convert = await client.post(
        f"/quotes/{quote['id']}/convert-to-job",
        headers={"X-Tenant-ID": tenant["id"]},
        json={},
    )
    assert convert.status_code == 201, convert.text
    assert convert.json()["scheduled_start"] is None
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# Payment received: customer email from the Stripe succeeded webhook
# ---------------------------------------------------------------------------


async def _seed_stripe_invoice(
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Seed tenant → contact → sent invoice, committed for the handler session."""
    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        tenant = Tenant(
            slug=f"pay-{uuid4().hex[:8]}",
            name="Payday Electrical",
            settings=settings or {},
        )
        session.add(tenant)
        await session.flush()
        await set_tenant_in_session(session, tenant.id)
        contact = Contact(tenant_id=tenant.id, name="Amy Homeowner", email="amy@example.com")
        session.add(contact)
        await session.flush()
        invoice = Invoice(
            tenant_id=tenant.id,
            contact_id=contact.id,
            invoice_number=f"INV-{uuid4().hex[:6]}",
            status="sent",
            subtotal=Decimal("600.00"),
            total=Decimal("600.00"),
        )
        session.add(invoice)
        await session.flush()
        ids = {
            "tenant_id": tenant.id,
            "contact_id": contact.id,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
        }
        await session.commit()
        return ids


async def _cleanup_stripe_seed(ids: dict[str, Any], event_ids: list[str]) -> None:
    from app.models import ProcessedWebhook
    from sqlalchemy import delete

    async with AsyncSession(engine) as session:
        await bypass_rls_in_session(session)
        for event_id in event_ids:
            await session.execute(
                delete(ProcessedWebhook).where(ProcessedWebhook.event_id == event_id)
            )
        await session.execute(delete(Tenant).where(Tenant.id == ids["tenant_id"]))
        await session.commit()


async def test_payment_received_email_with_review_cta(
    monkeypatch: MonkeyPatch,
) -> None:
    ids = await _seed_stripe_invoice(
        settings={
            "email": "sparks@example.com",
            "review_url": "https://g.page/r/payday-review",
        }
    )
    event_id = f"evt_pay_{uuid4().hex[:12]}"
    event = payment_intent_succeeded_event(
        event_id, invoice_id=ids["invoice_id"], tenant_id=ids["tenant_id"]
    )
    _patch_construct(monkeypatch, event)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.payment_notifications.send_customer_email", recorder)
    try:
        response = await _post_event(event)

        assert response.status_code == 200, response.text
        assert len(recorder.calls) == 1
        call = recorder.calls[0]
        assert call["event"] == "payment_received"
        assert call["template"] == "payment_received"
        assert call["to_email"] == "amy@example.com"
        assert call["from_name"] == "Payday Electrical"
        assert call["reply_to"] == "sparks@example.com"
        html = call["html_body"]
        assert ids["invoice_number"] in html
        assert "£600.00" in html
        assert "How did we do?" in html
        assert "https://g.page/r/payday-review" in html
    finally:
        await _cleanup_stripe_seed(ids, [event_id])


async def test_payment_received_email_without_review_url_has_no_review_block(
    monkeypatch: MonkeyPatch,
) -> None:
    ids = await _seed_stripe_invoice(settings={"email": "sparks@example.com"})
    event_id = f"evt_pay_{uuid4().hex[:12]}"
    event = payment_intent_succeeded_event(
        event_id, invoice_id=ids["invoice_id"], tenant_id=ids["tenant_id"]
    )
    _patch_construct(monkeypatch, event)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.payment_notifications.send_customer_email", recorder)
    try:
        response = await _post_event(event)

        assert response.status_code == 200, response.text
        assert len(recorder.calls) == 1
        html = recorder.calls[0]["html_body"]
        assert ids["invoice_number"] in html
        assert "How did we do?" not in html
    finally:
        await _cleanup_stripe_seed(ids, [event_id])


async def test_webhook_still_200_when_customer_email_send_raises(
    monkeypatch: MonkeyPatch,
) -> None:
    ids = await _seed_stripe_invoice(settings={"email": "sparks@example.com"})
    event_id = f"evt_pay_{uuid4().hex[:12]}"
    event = payment_intent_succeeded_event(
        event_id, invoice_id=ids["invoice_id"], tenant_id=ids["tenant_id"]
    )
    _patch_construct(monkeypatch, event)
    monkeypatch.setattr(
        "app.payment_notifications.send_customer_email",
        AsyncMock(side_effect=RuntimeError("resend down")),
    )
    try:
        response = await _post_event(event)

        assert response.status_code == 200, response.text
        async with AsyncSession(engine) as session:
            await bypass_rls_in_session(session)
            invoice = await session.get(Invoice, ids["invoice_id"])
            assert invoice is not None
            assert invoice.status == "paid"
            assert invoice.paid_via == "stripe"
    finally:
        await _cleanup_stripe_seed(ids, [event_id])


# ---------------------------------------------------------------------------
# Manual mark-paid: same payment_received confirmation, non-card copy variant
# ---------------------------------------------------------------------------


async def _create_invoice_for_tenant(
    client: AsyncClient, tenant: Tenant, contact: Contact
) -> dict[str, Any]:
    create = await client.post(
        "/invoices",
        headers={"X-Tenant-ID": str(tenant.id)},
        json={
            "contact_id": str(contact.id),
            "line_items": [
                {"description": "Labour", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert create.status_code == 201, create.text
    data: dict[str, Any] = create.json()
    return data


async def test_mark_paid_sends_payment_received_email_with_review_cta(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    """Manual mark-paid now confirms to the customer, review CTA included (#114)."""
    tenant = await _create_tenant(
        db,
        f"mpaid-{uuid4().hex[:8]}",
        settings={"email": "sparks@example.com", "review_url": "https://g.page/r/acme-review"},
    )
    contact = await _create_contact(db, tenant)
    invoice = await _create_invoice_for_tenant(client, tenant, contact)

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.payment_notifications.send_customer_email", recorder)

    response = await client.post(
        f"/invoices/{invoice['id']}/mark-paid", headers={"X-Tenant-ID": str(tenant.id)}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paid"
    assert response.json()["paid_via"] == "manual"

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["event"] == "payment_received"
    assert call["template"] == "payment_received"
    assert call["to_email"] == "homeowner@example.com"
    assert call["from_name"] == tenant.name
    assert invoice["invoice_number"] in call["html_body"]
    assert "£100.00" in call["html_body"]
    # Manual path: the copy must NOT claim a card payment / Stripe receipt.
    assert "Stripe will also email you a card receipt" not in call["html_body"]
    assert "Stripe will also email you a card receipt" not in call["text_body"]
    # Review prompt present because the tenant configured review_url.
    assert "How did we do?" in call["html_body"]
    assert "https://g.page/r/acme-review" in call["html_body"]


async def test_mark_paid_email_omits_review_cta_without_review_url(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant = await _create_tenant(db, f"mpaid-{uuid4().hex[:8]}")
    contact = await _create_contact(db, tenant)
    invoice = await _create_invoice_for_tenant(client, tenant, contact)

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.payment_notifications.send_customer_email", recorder)

    response = await client.post(
        f"/invoices/{invoice['id']}/mark-paid", headers={"X-Tenant-ID": str(tenant.id)}
    )
    assert response.status_code == 200, response.text
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["event"] == "payment_received"
    assert "How did we do?" not in recorder.calls[0]["html_body"]
    assert "Stripe will also email you a card receipt" not in recorder.calls[0]["html_body"]


# ---------------------------------------------------------------------------
# Reminders: magic link when a Customer exists (no fresh doc token), else doc
# ---------------------------------------------------------------------------


async def _make_due_quote(db: AsyncSession, tenant_id: UUID, contact_id: UUID) -> Quote:
    quote = Quote(
        tenant_id=tenant_id,
        contact_id=contact_id,
        title="Consumer unit replacement",
        status="sent",
        sent_at=datetime.utcnow() - timedelta(days=4),
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )
    db.add(quote)
    await db.flush()
    return quote


async def _make_due_invoice(db: AsyncSession, tenant_id: UUID, contact_id: UUID) -> Invoice:
    invoice = Invoice(
        tenant_id=tenant_id,
        contact_id=contact_id,
        invoice_number=f"INV-{uuid4().hex[:6]}",
        status="sent",
        issue_date=datetime.utcnow() - timedelta(days=22),
        due_date=datetime.utcnow() - timedelta(days=8),
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )
    db.add(invoice)
    await db.flush()
    return invoice


async def test_quote_reminder_sends_magic_link_and_skips_doc_token(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email="amy@example.com")
    db.add(contact)
    await db.flush()
    await _make_due_quote(db, tenant_id, contact.id)
    await db.commit()

    monkeypatch.setattr(
        "app.scheduler.resolve_customer_magic_link", AsyncMock(return_value=MAGIC_URL)
    )
    doc_view_url = AsyncMock(return_value="https://mytradeportal.co.uk/quote/should-not-be-used")
    monkeypatch.setattr("app.scheduler._document_view_url", doc_view_url)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.scheduler.send_customer_email", recorder)

    summary = await run_reminder_tick(db)

    assert summary["quote_reminders"] == 1
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["template"] == "quote_reminder"
    assert MAGIC_URL in call["html_body"]
    doc_view_url.assert_not_awaited()


async def test_quote_reminder_sends_doc_token_when_no_customer(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email="amy@example.com")
    db.add(contact)
    await db.flush()
    await _make_due_quote(db, tenant_id, contact.id)
    await db.commit()

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.scheduler.send_customer_email", recorder)

    summary = await run_reminder_tick(db)

    assert summary["quote_reminders"] == 1
    assert len(recorder.calls) == 1
    html = recorder.calls[0]["html_body"]
    assert DOC_URL_MARKER in html
    assert "auth/magic" not in html


async def test_invoice_reminder_sends_magic_link_and_skips_doc_token(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email="amy@example.com")
    db.add(contact)
    await db.flush()
    await _make_due_invoice(db, tenant_id, contact.id)
    await db.commit()

    monkeypatch.setattr(
        "app.scheduler.resolve_customer_magic_link", AsyncMock(return_value=MAGIC_URL)
    )
    doc_view_url = AsyncMock(return_value="https://mytradeportal.co.uk/invoice/unused")
    monkeypatch.setattr("app.scheduler._document_view_url", doc_view_url)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.scheduler.send_customer_email", recorder)

    summary = await run_reminder_tick(db)

    assert summary["invoice_reminders"] == 1
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["template"] == "invoice_reminder"
    assert MAGIC_URL in call["html_body"]
    doc_view_url.assert_not_awaited()


async def test_invoice_reminder_sends_doc_token_when_no_customer(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email="amy@example.com")
    db.add(contact)
    await db.flush()
    await _make_due_invoice(db, tenant_id, contact.id)
    await db.commit()

    recorder = _EmailRecorder()
    monkeypatch.setattr("app.scheduler.send_customer_email", recorder)

    summary = await run_reminder_tick(db)

    assert summary["invoice_reminders"] == 1
    assert len(recorder.calls) == 1
    html = recorder.calls[0]["html_body"]
    assert "/invoice/" in html
    assert "auth/magic" not in html


# ---------------------------------------------------------------------------
# chat_message template: staff chat email (push + email for app/email prefs)
# ---------------------------------------------------------------------------


async def test_chat_message_template_renders_preview_and_portal_cta() -> None:
    subject, html, text = chat_message_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        message_preview="We can move the visit to Tuesday if that helps.",
        reply_url=MAGIC_URL,
    )
    assert "Acme Electrical" in subject
    assert "We can move the visit to Tuesday if that helps." in html
    assert "Reply in the portal" in html
    assert MAGIC_URL in html
    assert MAGIC_URL in text


async def _seed_chat_thread(
    db: AsyncSession, tenant_id: UUID, preferred: str | None
) -> dict[str, UUID]:
    """Seed contact → customer (passwordless) → quote request thread + push token."""
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(
        tenant_id=tenant_id,
        name="Amy Homeowner",
        email="amy@example.com",
        preferred_contact_method=preferred,
    )
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant_id,
        contact_id=contact.id,
        email=contact.email or "amy@example.com",
        full_name="Amy Homeowner",
    )
    db.add(customer)
    await db.flush()
    quote_request = QuoteRequest(
        tenant_id=tenant_id,
        contact_id=contact.id,
        customer_id=customer.id,
        source="web_form",
    )
    db.add(quote_request)
    db.add(
        PushToken(
            tenant_id=tenant_id,
            owner_type="customer",
            owner_id=customer.id,
            token=f"ExponentPushToken[{uuid4().hex}]",
            platform="ios",
        )
    )
    await db.commit()
    return {
        "contact_id": contact.id,
        "customer_id": customer.id,
        "quote_request_id": quote_request.id,
    }


async def _staff_chat_message(client: AsyncClient, tenant_id: UUID, quote_request_id: UUID) -> None:
    response = await client.post(
        "/communications",
        headers={"X-Tenant-ID": str(tenant_id)},
        json={
            "quote_request_id": str(quote_request_id),
            "channel": "in_app_chat",
            "body": "We can move the visit to Tuesday if that helps.",
        },
    )
    assert response.status_code == 201, response.text


async def test_staff_chat_message_to_app_preference_sends_push_and_email(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    ids = await _seed_chat_thread(db, tenant_id, preferred="app")

    push = AsyncMock()
    monkeypatch.setattr("app.push.send_expo_push", push)
    magic_link_url = AsyncMock(return_value=MAGIC_URL)
    monkeypatch.setattr("app.routers.communications.magic_link_url", magic_link_url)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.communications.send_customer_email", recorder)

    await _staff_chat_message(admin_client, tenant_id, ids["quote_request_id"])

    # Push still goes out to the registered customer device…
    push.assert_awaited_once()
    assert push.await_args is not None
    assert push.await_args.args[0] != []
    # …and the customer also gets the chat_message email with a magic link.
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["event"] == "chat_message"
    assert call["template"] == "chat_message"
    assert call["to_email"] == "amy@example.com"
    assert "Tuesday" in call["html_body"]
    assert MAGIC_URL in call["html_body"]
    assert "Reply in the portal" in call["html_body"]
    magic_link_url.assert_awaited_once()
    assert magic_link_url.await_args is not None
    # No quote linked to the thread: the magic link lands on the quotes list.
    assert magic_link_url.await_args.args[3] == "/quotes"


async def test_staff_chat_message_email_links_quote_when_thread_has_one(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    ids = await _seed_chat_thread(db, tenant_id, preferred="email")
    await set_tenant_in_session(db, tenant_id)
    quote_request = await db.get(QuoteRequest, ids["quote_request_id"])
    assert quote_request is not None
    quote = Quote(
        tenant_id=tenant_id,
        contact_id=ids["contact_id"],
        title="Fuse board upgrade",
        status="sent",
        subtotal=Decimal("400.00"),
        vat_amount=Decimal("80.00"),
        total=Decimal("480.00"),
    )
    db.add(quote)
    await db.flush()
    quote_request.quote_id = quote.id
    await db.commit()

    monkeypatch.setattr("app.push.send_expo_push", AsyncMock())
    magic_link_url = AsyncMock(return_value=MAGIC_URL)
    monkeypatch.setattr("app.routers.communications.magic_link_url", magic_link_url)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.communications.send_customer_email", recorder)

    await _staff_chat_message(admin_client, tenant_id, ids["quote_request_id"])

    assert len(recorder.calls) == 1
    magic_link_url.assert_awaited_once()
    assert magic_link_url.await_args is not None
    assert magic_link_url.await_args.args[3] == f"/quotes/{quote.id}"


async def test_staff_chat_message_to_phone_preference_sends_push_but_no_email(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    ids = await _seed_chat_thread(db, tenant_id, preferred="phone")

    push = AsyncMock()
    monkeypatch.setattr("app.push.send_expo_push", push)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.communications.send_customer_email", recorder)

    await _staff_chat_message(admin_client, tenant_id, ids["quote_request_id"])

    push.assert_awaited_once()
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# booking_confirmed claim_url: account-claim CTA for passwordless customers
# ---------------------------------------------------------------------------


CLAIM_URL = "https://acme.mytradeportal.co.uk/auth/magic?token=tok-claim&next=/claim"


async def test_booking_confirmed_template_with_claim_block() -> None:
    _, html, text = booking_confirmed_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        job_title="Fuse board replacement",
        visit_date="Monday 21 September 2026",
        time_window="09:00 - 11:00",
        claim_url=CLAIM_URL,
    )
    assert "Create your account" in html
    assert "Manage your quote, booking and invoices in one place" in html
    assert CLAIM_URL in html
    assert CLAIM_URL in text


async def test_booking_confirmed_template_without_claim_url_has_no_claim_block() -> None:
    _, html, text = booking_confirmed_template(
        customer_name="Amy",
        business_name="Acme Electrical",
        job_title="Fuse board replacement",
        visit_date="Monday 21 September 2026",
        time_window="09:00 - 11:00",
    )
    assert "Create your account" not in html
    assert "Manage your quote, booking and invoices" not in text


async def _schedule_job_and_capture_email(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: MonkeyPatch,
    *,
    with_password: bool,
) -> dict[str, Any]:
    tenant = await _create_tenant_via_api(client, f"book-{uuid4().hex[:8]}")
    tenant_id = UUID(tenant["id"])
    await set_tenant_in_session(db, tenant_id)

    contact_response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"name": "Amy Homeowner", "email": "amy@example.com"},
    )
    assert contact_response.status_code == 201, contact_response.text
    contact = contact_response.json()

    customer = Customer(
        tenant_id=tenant_id,
        contact_id=UUID(contact["id"]),
        email="amy@example.com",
        full_name="Amy Homeowner",
        password_hash=get_password_hash("chosen-password-123") if with_password else None,
    )
    db.add(customer)
    await db.commit()

    job_response = await client.post(
        "/jobs",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": contact["id"], "title": "Fuse board swap"},
    )
    assert job_response.status_code == 201, job_response.text
    job = job_response.json()

    magic_link_url = AsyncMock(return_value=CLAIM_URL)
    monkeypatch.setattr("app.routers.jobs.magic_link_url", magic_link_url)
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.routers.jobs.send_customer_email", recorder)

    patch = await client.patch(
        f"/jobs/{job['id']}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"scheduled_start": datetime(2026, 9, 21, 9, 0).isoformat()},
    )
    assert patch.status_code == 200, patch.text
    assert len(recorder.calls) == 1
    return {"call": recorder.calls[0], "magic_link_url": magic_link_url}


async def test_booking_confirmed_email_carries_claim_url_for_passwordless_customer(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    result = await _schedule_job_and_capture_email(client, db, monkeypatch, with_password=False)
    call = result["call"]
    assert call["event"] == "booking_confirmed"
    assert CLAIM_URL in call["html_body"]
    assert "Create your account" in call["html_body"]
    magic_link_url = result["magic_link_url"]
    magic_link_url.assert_awaited_once()
    assert magic_link_url.await_args is not None
    assert magic_link_url.await_args.args[3] == "/claim"


async def test_booking_confirmed_email_has_no_claim_cta_for_passworded_customer(
    client: AsyncClient, db: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    result = await _schedule_job_and_capture_email(client, db, monkeypatch, with_password=True)
    call = result["call"]
    assert call["event"] == "booking_confirmed"
    assert "Create your account" not in call["html_body"]
    assert CLAIM_URL not in call["html_body"]
    result["magic_link_url"].assert_not_awaited()
