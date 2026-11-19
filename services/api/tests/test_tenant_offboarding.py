"""Tests for tenant offboarding (GDPR deletion, POST /tenants/me/offboard)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.models import (
    Communication,
    Contact,
    Customer,
    CustomerPortalToken,
    DocumentAccessToken,
    Invoice,
    InvoiceLineItem,
    PasswordResetToken,
    Quote,
    QuoteLineItem,
    StripeAccount,
    Subscription,
    Tenant,
    User,
)
from app.rls import set_tenant_in_session
from app.security import create_access_token, get_password_hash
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

OFFBOARD_URL = "/tenants/me/offboard"


def _tenant_id(admin_client: AsyncClient) -> UUID:
    return UUID(admin_client.headers["X-Tenant-ID"])


async def _seed_offboard_records(db: AsyncSession, tenant: Tenant) -> dict[str, UUID]:
    """Seed one of each PII-bearing / financial record for the tenant."""
    await set_tenant_in_session(db, tenant.id)
    tenant.settings = {
        "email": "boss@test-electrical.example",
        "phone": "07111222333",
        "address": "1 Trade Way",
        "primary_color": "#123456",
    }

    contact = Contact(
        tenant_id=tenant.id,
        name="Amy Homeowner",
        email="amy@example.com",
        phone="07123456789",
        postcode="SW1A 1AA",
        notes="Prefers afternoon visits",
    )
    db.add(contact)
    await db.flush()

    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email="amy@example.com",
        full_name="Amy Homeowner",
        phone="07123456789",
        password_hash=get_password_hash("customer-password-123"),
        magic_link_token="raw-magic-token",
        magic_link_expires_at=datetime.utcnow() + timedelta(days=1),
    )
    db.add(customer)
    await db.flush()

    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title="Consumer unit replacement",
        status="accepted",
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )
    db.add(quote)
    await db.flush()
    db.add(
        QuoteLineItem(
            tenant_id=tenant.id,
            quote_id=quote.id,
            description="Supply and fit consumer unit",
            quantity=Decimal("1.00"),
            unit="ea",
            unit_price=Decimal("500.00"),
            total=Decimal("500.00"),
        )
    )

    invoice = Invoice(
        tenant_id=tenant.id,
        contact_id=contact.id,
        quote_id=quote.id,
        invoice_number=f"INV-{uuid4().hex[:6]}",
        status="sent",
        issue_date=datetime.utcnow(),
        due_date=datetime.utcnow() + timedelta(days=14),
        subtotal=Decimal("500.00"),
        vat_rate=Decimal("0.20"),
        vat_amount=Decimal("100.00"),
        total=Decimal("600.00"),
    )
    db.add(invoice)
    await db.flush()
    db.add(
        InvoiceLineItem(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            description="Consumer unit works as quoted",
            quantity=Decimal("1.00"),
            unit_price=Decimal("500.00"),
            total=Decimal("500.00"),
        )
    )

    db.add(
        Communication(
            tenant_id=tenant.id,
            contact_id=contact.id,
            channel="email",
            direction="outbound",
            sender_role="business",
            subject="Your quote",
            body="Please find your quote attached.",
        )
    )

    # Non-RLS token/provider tables: no tenant GUC needed for these inserts.
    db.add(
        CustomerPortalToken(
            customer_id=customer.id,
            tenant_id=tenant.id,
            token_hash=uuid4().hex * 2,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    db.add(
        DocumentAccessToken(
            tenant_id=tenant.id,
            kind="quote",
            document_id=quote.id,
            token_hash=uuid4().hex * 2,
            contact_email="amy@example.com",
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
    )
    db.add(
        PasswordResetToken(
            tenant_id=tenant.id,
            owner_type="customer",
            owner_id=customer.id,
            token_hash=uuid4().hex * 2,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
    )
    db.add(
        Subscription(
            tenant_id=tenant.id,
            plan_key="sole_trader",
            status="trialing",
            trial_ends_at=datetime.utcnow() + timedelta(days=14),
        )
    )
    db.add(
        StripeAccount(
            tenant_id=tenant.id,
            stripe_account_id=f"acct_test_{uuid4().hex[:16]}",
        )
    )

    await db.commit()
    return {
        "contact_id": contact.id,
        "customer_id": customer.id,
        "quote_id": quote.id,
        "invoice_id": invoice.id,
    }


async def test_offboard_requires_auth(client: AsyncClient) -> None:
    response = await client.post(OFFBOARD_URL, json={"confirm_slug": "whatever"})
    assert response.status_code == 401


async def test_offboard_requires_admin_role(client: AsyncClient, db: AsyncSession) -> None:
    tenant = Tenant(slug=f"eng-{uuid4().hex[:8]}", name="Engineer Co")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    engineer = User(
        tenant_id=tenant.id,
        email="engineer@test.local",
        full_name="Test Engineer",
        role="engineer",
        password_hash=get_password_hash("engineer-password-123"),
        is_active=True,
    )
    db.add(engineer)
    await db.commit()

    response = await client.post(
        "/auth/login",
        headers={"host": f"{tenant.slug}.localhost"},
        json={"email": engineer.email, "password": "engineer-password-123"},
    )
    assert response.status_code == 200
    client.headers["X-Tenant-ID"] = str(tenant.id)

    response = await client.post(OFFBOARD_URL, json={"confirm_slug": tenant.slug})
    assert response.status_code == 403


async def test_offboard_rejects_wrong_confirm_slug(admin_client: AsyncClient) -> None:
    response = await admin_client.post(OFFBOARD_URL, json={"confirm_slug": "not-the-slug"})
    assert response.status_code == 400


async def test_offboard_deactivates_and_anonymises(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    ids = await _seed_offboard_records(db, tenant)

    response = await admin_client.post(OFFBOARD_URL, json={"confirm_slug": tenant.slug})
    assert response.status_code == 200
    summary = response.json()
    assert summary["tenant_id"] == str(tenant_id)
    assert summary["status"] == "offboarded"
    assert summary["users_deactivated"] == 1
    assert summary["customers_deactivated"] == 1
    assert summary["contacts_anonymised"] == 1
    assert summary["tokens_revoked"] == 3  # portal + document + password-reset
    assert summary["paddle_subscription_cancelled"] is True  # local trial, nothing remote
    # Stripe is not configured in tests, so the API delete fails (best-effort)
    # but the local row must still be detached.
    assert summary["stripe_account_detached"] is False

    await db.refresh(tenant)
    assert tenant.is_active is False
    assert tenant.status == "offboarded"
    # Tenant contact details scrubbed; branding kept for retained records.
    assert "email" not in tenant.settings
    assert "phone" not in tenant.settings
    assert "address" not in tenant.settings
    assert tenant.settings["primary_color"] == "#123456"

    user = await db.scalar(select(User).where(User.tenant_id == tenant_id))
    assert user is not None
    assert user.is_active is False
    assert user.email.endswith("@offboarded.invalid")
    assert user.full_name == "Offboarded user"
    assert user.password_hash is None

    contact = await db.get(Contact, ids["contact_id"])
    assert contact is not None
    assert contact.name == "Former customer"
    assert contact.email is None
    assert contact.phone is None
    assert contact.postcode is None
    assert contact.notes is None

    customer = await db.get(Customer, ids["customer_id"])
    assert customer is not None
    assert customer.is_active is False
    assert customer.email.endswith("@offboarded.invalid")
    assert customer.full_name == "Former customer"
    assert customer.password_hash is None
    assert customer.magic_link_token is None
    assert customer.magic_link_expires_at is None

    portal_token = await db.scalar(
        select(CustomerPortalToken).where(CustomerPortalToken.tenant_id == tenant_id)
    )
    assert portal_token is not None
    assert portal_token.revoked_at is not None

    document_token = await db.scalar(
        select(DocumentAccessToken).where(DocumentAccessToken.tenant_id == tenant_id)
    )
    assert document_token is not None
    assert document_token.revoked_at is not None
    assert document_token.contact_email is None

    reset_token = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.tenant_id == tenant_id)
    )
    assert reset_token is not None
    assert reset_token.used_at is not None

    subscription = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    assert subscription is not None
    assert subscription.status == "canceled"

    stripe_row = await db.scalar(select(StripeAccount).where(StripeAccount.tenant_id == tenant_id))
    assert stripe_row is None


async def test_offboard_preserves_financial_records(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    ids = await _seed_offboard_records(db, tenant)

    response = await admin_client.post(OFFBOARD_URL, json={"confirm_slug": tenant.slug})
    assert response.status_code == 200

    quote = await db.get(Quote, ids["quote_id"])
    assert quote is not None
    assert quote.total == Decimal("600.00")
    assert quote.vat_amount == Decimal("100.00")
    quote_lines = await db.scalar(
        select(func.count(QuoteLineItem.id)).where(QuoteLineItem.quote_id == quote.id)
    )
    assert quote_lines == 1

    invoice = await db.get(Invoice, ids["invoice_id"])
    assert invoice is not None
    assert invoice.total == Decimal("600.00")
    assert invoice.vat_amount == Decimal("100.00")
    assert invoice.invoice_number.startswith("INV-")
    invoice_lines = await db.scalar(
        select(func.count(InvoiceLineItem.id)).where(InvoiceLineItem.invoice_id == invoice.id)
    )
    assert invoice_lines == 1

    # The communication row survives for the audit trail but its PII is gone.
    comm = await db.scalar(select(Communication).where(Communication.tenant_id == tenant_id))
    assert comm is not None
    assert comm.subject is None
    assert comm.body is None


async def test_offboarded_tenant_cannot_authenticate(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    tenant_id = _tenant_id(admin_client)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    slug = tenant.slug
    ids = await _seed_offboard_records(db, tenant)

    # A customer token minted before offboarding works right up to the offboard.
    customer_token = create_access_token(
        ids["customer_id"],
        tenant_id,
        role="customer",
        email="amy@example.com",
        subject_type="customer",
    )
    me = await admin_client.get(
        "/customer/me", headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert me.status_code == 200

    response = await admin_client.post(OFFBOARD_URL, json={"confirm_slug": slug})
    assert response.status_code == 200

    # The caller's own staff session is revoked (user deactivated).
    assert (await admin_client.get("/auth/me")).status_code == 401
    # The pre-offboard customer token is revoked (customer deactivated).
    assert (
        await admin_client.get(
            "/customer/me", headers={"Authorization": f"Bearer {customer_token}"}
        )
    ).status_code == 401
    # Tenant-scoped endpoints reject the offboarded tenant. The exact status
    # depends on middleware ordering: tenant resolution 401s the inactive
    # tenant, but the paywall middleware may intercept first with a 402 for
    # the canceled subscription. Either way, access is gone.
    assert (await admin_client.get("/export/my-data")).status_code in (401, 402)
    # Fresh staff login is refused for an offboarded tenant — both via the
    # Host subdomain and via an explicit tenant_slug in the body.
    login = await admin_client.post(
        "/auth/login",
        headers={"host": f"{slug}.localhost"},
        json={"email": "admin@test.local", "password": "admin-password-123"},
    )
    assert login.status_code == 401
    login = await admin_client.post(
        "/auth/login",
        json={
            "email": "admin@test.local",
            "password": "admin-password-123",
            "tenant_slug": slug,
        },
    )
    assert login.status_code == 401
