"""Tests for contact-preference intake mapping and staff reachability flags."""

from typing import Any
from uuid import uuid4

import pytest
from app.models import Contact, Customer, PushToken, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.utils.tenant_code import generate_unique_tenant_code
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    code = await generate_unique_tenant_code(db)
    tenant = Tenant(slug=slug, code=code, name=f"{slug} Electrical")
    db.add(tenant)
    await db.flush()
    return tenant


async def _submit(
    client: AsyncClient, slug: str, structured_data: dict[str, Any], **contact_overrides: Any
) -> dict[str, Any]:
    contact = {"name": "Homeowner", "email": f"homeowner-{uuid4().hex[:8]}@example.com"}
    contact.update(contact_overrides)
    response = await client.post(
        f"/businesses/{slug}/quote-requests",
        json={
            "contact": contact,
            "category": "consumer_unit",
            "title": "Consumer unit upgrade",
            "structured_data": structured_data,
        },
    )
    assert response.status_code == 201, response.text
    ack: dict[str, Any] = response.json()
    return ack


async def _leads(client: AsyncClient, tenant: Tenant) -> list[dict[str, Any]]:
    listing = await client.get("/quote-requests", headers={"X-Tenant-ID": str(tenant.id)})
    assert listing.status_code == 200, listing.text
    rows: list[dict[str, Any]] = listing.json()
    return rows


async def test_intake_preferred_contact_string_shape(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    await _submit(client, slug, {"preferredContact": "phone"})

    (lead,) = await _leads(client, tenant)
    assert lead["customer"]["preferred_contact_method"] == "phone"
    assert lead["contact_preferred_method"] == "phone"


async def test_intake_preferred_contact_dict_shape(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    await _submit(client, slug, {"preferredContact": {"method": "email"}})

    (lead,) = await _leads(client, tenant)
    assert lead["customer"]["preferred_contact_method"] == "email"
    assert lead["contact_preferred_method"] == "email"


async def test_intake_contact_field_wins_over_structured_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    await _submit(
        client,
        slug,
        {"preferredContact": "email"},
        preferred_contact_method="phone",
    )

    (lead,) = await _leads(client, tenant)
    assert lead["customer"]["preferred_contact_method"] == "phone"
    assert lead["contact_preferred_method"] == "phone"


async def test_intake_chat_preference_is_not_a_follow_up_method(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    # The mobile app's default wizard value: not a staff follow-up channel.
    await _submit(client, slug, {"preferredContact": "in_app_chat"})

    (lead,) = await _leads(client, tenant)
    assert lead["customer"]["preferred_contact_method"] is None
    assert lead["contact_preferred_method"] is None


async def test_auto_provisioned_customer_is_not_chat_reachable(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)

    # Guest intake with an email auto-provisions a passwordless customer.
    await _submit(client, slug, {"preferredContact": "email"})

    (lead,) = await _leads(client, tenant)
    assert lead["customer"]["has_account"] is True
    assert lead["customer_reachable"] is False

    detail = await client.get(
        f"/quote-requests/{lead['id']}", headers={"X-Tenant-ID": str(tenant.id)}
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["customer_reachable"] is False
    assert detail.json()["contact_preferred_method"] == "email"


@pytest.mark.parametrize("claim_field", ["password", "push_token"])
async def test_reachable_customer_variants(
    client: AsyncClient, db: AsyncSession, claim_field: str
) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    await set_tenant_in_session(db, tenant.id)

    contact = Contact(tenant_id=tenant.id, name="Reachable", email=f"r-{uuid4().hex[:8]}@ex.com")
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant.id,
        contact_id=contact.id,
        email=contact.email or "",
        full_name="Reachable",
        password_hash="hash" if claim_field == "password" else None,
    )
    db.add(customer)
    await db.flush()
    if claim_field == "push_token":
        db.add(
            PushToken(
                tenant_id=tenant.id,
                owner_type="customer",
                owner_id=customer.id,
                token=f"ExponentPushToken[{uuid4().hex}]",
                platform="ios",
            )
        )
    db.add(QuoteRequest(tenant_id=tenant.id, contact_id=contact.id, source="web_form"))
    await db.commit()

    (lead,) = await _leads(client, tenant)
    assert lead["customer_reachable"] is True


async def test_staff_list_flags_mixed_leads_without_n_plus_one(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    await set_tenant_in_session(db, tenant.id)

    def _contact(name: str, preferred: str | None = None) -> Contact:
        return Contact(
            tenant_id=tenant.id,
            name=name,
            email=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:6]}@ex.com",
            preferred_contact_method=preferred,
        )

    claimed = _contact("Claimed Customer", preferred="phone")
    push_only = _contact("Push Only")
    passwordless = _contact("Passwordless")
    no_account = _contact("No Account")
    db.add_all([claimed, push_only, passwordless, no_account])
    await db.flush()

    claimed_customer = Customer(
        tenant_id=tenant.id,
        contact_id=claimed.id,
        email=claimed.email or "",
        full_name=claimed.name,
        password_hash="hash",
    )
    push_customer = Customer(
        tenant_id=tenant.id,
        contact_id=push_only.id,
        email=push_only.email or "",
        full_name=push_only.name,
        password_hash=None,
    )
    db.add_all(
        [
            claimed_customer,
            push_customer,
            Customer(
                tenant_id=tenant.id,
                contact_id=passwordless.id,
                email=passwordless.email or "",
                full_name=passwordless.name,
                password_hash=None,
            ),
        ]
    )
    await db.flush()
    db.add(
        PushToken(
            tenant_id=tenant.id,
            owner_type="customer",
            owner_id=push_customer.id,
            token=f"ExponentPushToken[{uuid4().hex}]",
            platform="ios",
        )
    )
    db.add_all(
        [
            QuoteRequest(tenant_id=tenant.id, contact_id=claimed.id, source="web_form"),
            QuoteRequest(
                tenant_id=tenant.id,
                contact_id=push_only.id,
                source="web_form",
                structured_data={"preferredContact": {"method": "email"}},
            ),
            QuoteRequest(
                tenant_id=tenant.id,
                contact_id=passwordless.id,
                source="web_form",
                structured_data={"preferredContact": "in_app_chat"},
            ),
            QuoteRequest(tenant_id=tenant.id, contact_id=no_account.id, source="qr"),
        ]
    )
    await db.commit()

    # Count queries per table while listing the leads: the customer and
    # push-token lookups must stay batched (one query each) for the page.
    statements: list[str] = []

    def _record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: Any
    ) -> None:
        statements.append(statement)

    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    sync_engine = getattr(engine, "sync_engine", engine)
    event.listen(sync_engine, "before_cursor_execute", _record)
    try:
        leads = await _leads(client, tenant)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _record)

    assert len(leads) == 4
    customer_queries = [s for s in statements if "FROM customers" in s]
    push_token_queries = [s for s in statements if "FROM push_tokens" in s]
    assert len(customer_queries) <= 1
    assert len(push_token_queries) <= 1

    by_name = {lead["customer"]["name"]: lead for lead in leads}
    assert by_name["Claimed Customer"]["customer_reachable"] is True
    assert by_name["Claimed Customer"]["contact_preferred_method"] == "phone"
    assert by_name["Push Only"]["customer_reachable"] is True
    assert by_name["Push Only"]["contact_preferred_method"] == "email"
    assert by_name["Passwordless"]["customer_reachable"] is False
    assert by_name["Passwordless"]["contact_preferred_method"] is None
    assert by_name["No Account"]["customer_reachable"] is False
    assert by_name["No Account"]["customer"]["has_account"] is False


async def test_preferred_method_falls_back_to_structured_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pref-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    await set_tenant_in_session(db, tenant.id)

    contact = Contact(tenant_id=tenant.id, name="Fallback", preferred_contact_method=None)
    db.add(contact)
    await db.flush()
    db.add(
        QuoteRequest(
            tenant_id=tenant.id,
            contact_id=contact.id,
            source="web_form",
            structured_data={"preferredContact": "email"},
        )
    )
    await db.commit()

    (lead,) = await _leads(client, tenant)
    assert lead["customer"]["preferred_contact_method"] is None
    assert lead["contact_preferred_method"] == "email"
    assert lead["customer_reachable"] is False
