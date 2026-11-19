"""Tenant brand colour in quote/invoice reminder emails (extends #167).

The send-quote / send-invoice emails already tint their CTAs from the
tenant's ``primary_color`` (#167); the reminder chase emails must match so a
customer sees the same brand across the whole payment conversation. The
template-level fallback keeps the platform colours (indigo magic-link button,
dark/gold invoice button) when no brand colour is threaded through.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from app.email_templates import invoice_reminder as invoice_reminder_template
from app.email_templates import quote_reminder as quote_reminder_template
from app.models import Contact, Invoice, Quote, Tenant
from app.scheduler import run_reminder_tick
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

BRAND = "#123ABC"
PLATFORM_INDIGO = "#4F46E5"
PLATFORM_INVOICE_BG = "#0F1E26"
PLATFORM_INVOICE_FG = "#FFC107"
PORTAL_URL = "https://acme.mytradeportal.co.uk/auth/magic?token=tok&next=/quotes/x"
VIEW_URL = "https://www.mytradeportal.co.uk/quote/test-token"

# ---------------------------------------------------------------------------
# Template unit tests
# ---------------------------------------------------------------------------


def test_quote_reminder_magic_link_uses_brand_color() -> None:
    _, html, _ = quote_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        quote_title="Consumer unit replacement",
        quote_total="£600.00",
        portal_url=PORTAL_URL,
        brand_color=BRAND,
    )
    assert f"background:{BRAND}" in html
    assert f"background:{PLATFORM_INDIGO}" not in html


def test_quote_reminder_magic_link_falls_back_to_platform_indigo() -> None:
    _, html, _ = quote_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        quote_title="Consumer unit replacement",
        quote_total="£600.00",
        portal_url=PORTAL_URL,
    )
    assert f"background:{PLATFORM_INDIGO}" in html


def test_quote_reminder_view_link_uses_brand_color() -> None:
    _, html, _ = quote_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        quote_title="Consumer unit replacement",
        quote_total="£600.00",
        view_url=VIEW_URL,
        brand_color=BRAND,
    )
    assert f"background:{BRAND}" in html
    assert f"background:{PLATFORM_INDIGO}" not in html


def test_quote_reminder_view_link_falls_back_to_platform_indigo() -> None:
    _, html, _ = quote_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        quote_title="Consumer unit replacement",
        quote_total="£600.00",
        view_url=VIEW_URL,
    )
    assert f"background:{PLATFORM_INDIGO}" in html


def test_invoice_reminder_magic_link_uses_brand_color() -> None:
    _, html, _ = invoice_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        invoice_number="INV-001",
        invoice_total="£600.00",
        portal_url=PORTAL_URL,
        brand_color=BRAND,
    )
    assert f"background:{BRAND}" in html
    assert f"background:{PLATFORM_INDIGO}" not in html


def test_invoice_reminder_magic_link_falls_back_to_platform_indigo() -> None:
    _, html, _ = invoice_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        invoice_number="INV-001",
        invoice_total="£600.00",
        portal_url=PORTAL_URL,
    )
    assert f"background:{PLATFORM_INDIGO}" in html


def test_invoice_reminder_view_link_uses_brand_color() -> None:
    _, html, _ = invoice_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        invoice_number="INV-001",
        invoice_total="£600.00",
        view_url=VIEW_URL,
        brand_color=BRAND,
    )
    assert f"background:{BRAND}" in html
    assert f"background:{PLATFORM_INVOICE_BG}" not in html
    # Branded buttons use white text, like invoice_sent.
    assert "color:#fff" in html


def test_invoice_reminder_view_link_falls_back_to_platform_dark_gold() -> None:
    _, html, _ = invoice_reminder_template(
        customer_name="Amy",
        business_name="Sparky Ltd",
        invoice_number="INV-001",
        invoice_total="£600.00",
        view_url=VIEW_URL,
    )
    assert f"background:{PLATFORM_INVOICE_BG}" in html
    assert f"color:{PLATFORM_INVOICE_FG}" in html


# ---------------------------------------------------------------------------
# Integration: tenant settings primary_color → reminder scheduler emails
# ---------------------------------------------------------------------------


class _EmailRecorder:
    """Stand-in for app.scheduler.send_customer_email that records calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, db: Any = None, **kwargs: Any) -> bool:
        self.calls.append(kwargs)
        return True


@pytest_asyncio.fixture
async def email_recorder(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[_EmailRecorder, None]:
    recorder = _EmailRecorder()
    monkeypatch.setattr("app.scheduler.send_customer_email", recorder)
    yield recorder


def _tenant_id(admin_client: AsyncClient) -> UUID:
    return UUID(admin_client.headers["X-Tenant-ID"])


async def _branded_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    tenant.settings = {**tenant.settings, "primary_color": BRAND}


@pytest.mark.asyncio
async def test_quote_reminder_email_uses_tenant_brand_color(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    await _branded_tenant(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email="amy@example.com")
    db.add(contact)
    await db.flush()
    db.add(
        Quote(
            tenant_id=tenant_id,
            contact_id=contact.id,
            title="Consumer unit replacement",
            status="sent",
            sent_at=datetime.utcnow() - timedelta(days=4),
            subtotal=Decimal("500.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("100.00"),
            total=Decimal("600.00"),
        )
    )
    await db.commit()

    summary = await run_reminder_tick(db)

    assert summary["quote_reminders"] == 1
    assert len(email_recorder.calls) == 1
    html = email_recorder.calls[0]["html_body"]
    assert f"background:{BRAND}" in html
    assert f"background:{PLATFORM_INDIGO}" not in html


@pytest.mark.asyncio
async def test_invoice_reminder_email_uses_tenant_brand_color(
    admin_client: AsyncClient,
    db: AsyncSession,
    email_recorder: _EmailRecorder,
) -> None:
    tenant_id = _tenant_id(admin_client)
    await _branded_tenant(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Amy Homeowner", email="amy@example.com")
    db.add(contact)
    await db.flush()
    db.add(
        Invoice(
            tenant_id=tenant_id,
            contact_id=contact.id,
            invoice_number=f"INV-{uuid4().hex[:6]}",
            status="sent",
            issue_date=datetime.utcnow() - timedelta(days=22),
            due_date=datetime.utcnow() - timedelta(days=8),
            subtotal=Decimal("500.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("100.00"),
            total=Decimal("600.00"),
        )
    )
    await db.commit()

    summary = await run_reminder_tick(db)

    assert summary["invoice_reminders"] == 1
    assert len(email_recorder.calls) == 1
    html = email_recorder.calls[0]["html_body"]
    assert f"background:{BRAND}" in html
    assert f"background:{PLATFORM_INVOICE_BG}" not in html
