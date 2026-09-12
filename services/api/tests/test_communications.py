"""Tests for communication log endpoints."""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app.models import Communication, Contact, QuoteRequest, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy import func, select
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


async def _log_in(client: AsyncClient, db: AsyncSession, tenant: dict[str, Any]) -> None:
    """Create a staff user for the tenant and log the test client in.

    Communication endpoints authenticate the actor (staff or customer), so
    tests must carry a real session rather than just the tenant header.
    """
    await set_tenant_in_session(db, UUID(tenant["id"]))
    password = "test-password-123"
    db.add(
        User(
            tenant_id=UUID(tenant["id"]),
            email="owner@test.local",
            full_name="Tenant Owner",
            role="admin",
            password_hash=get_password_hash(password),
            is_active=True,
        )
    )
    await db.commit()
    response = await client.post(
        "/auth/login",
        headers={"host": f"{tenant['slug']}.localhost"},
        json={"email": "owner@test.local", "password": password},
    )
    assert response.status_code == 200, response.text


async def test_create_and_list_communications(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _create_tenant(client, f"comm-{uuid4().hex[:8]}")
    await _log_in(client, db, tenant)
    contact = await _create_contact(client, tenant["id"], "Comm Customer")

    response = await client.post(
        "/communications",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "channel": "email",
            "subject": "Quote follow-up",
            "body": "Here is your quote.",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["channel"] == "email"
    assert data["tenant_id"] == tenant["id"]

    list_response = await client.get("/communications", headers={"X-Tenant-ID": tenant["id"]})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_communication_requires_valid_contact(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _create_tenant(client, f"comm-{uuid4().hex[:8]}")
    await _log_in(client, db, tenant)
    response = await client.post(
        "/communications",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"contact_id": str(uuid4()), "channel": "sms", "body": "Hello"},
    )
    assert response.status_code == 400


async def _create_lead(db: AsyncSession, tenant_id: UUID) -> QuoteRequest:
    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Lead Owner", email="lead.owner@example.com")
    db.add(contact)
    await db.flush()
    quote_request = QuoteRequest(
        tenant_id=tenant_id,
        contact_id=contact.id,
        source="web_form",
        raw_text="Need my fuse board replaced",
        structured_data={"category": "consumer_unit", "title": "Fuse board replacement"},
    )
    db.add(quote_request)
    await db.flush()
    return quote_request


async def test_ai_followup_merges_extracted_facts(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Facts the customer stated are merged into structured_data["ai_extracted"]."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)

    result_payload = {
        "confidence": 40,
        "complete": False,
        "message": "Where is the consumer unit located?",
        "extracted": {"property_type": "semi-detached", "parking": "driveway"},
    }
    with patch(
        "app.routers.communications.generate_followup",
        new=AsyncMock(return_value=result_payload),
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sender_role"] == "ai"
    assert body["ai_metadata"]["confidence"] == 40

    await db.refresh(quote_request)
    assert quote_request.structured_data["ai_extracted"] == {
        "property_type": "semi-detached",
        "parking": "driveway",
    }


async def test_ai_followup_forwards_full_thread_to_llm(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """The router forwards the whole thread; the LLM code owns any tail cap."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)
    for index in range(15):
        db.add(
            Communication(
                tenant_id=tenant_id,
                contact_id=quote_request.contact_id,
                quote_request_id=quote_request.id,
                channel="in_app_chat",
                direction="inbound",
                sender_role="customer",
                body=f"message {index}",
            )
        )
    await db.flush()

    captured: dict[str, Any] = {}

    async def _fake_followup(
        job_description: str, prior_messages: list[dict[str, str]], **kwargs: Any
    ) -> dict[str, Any]:
        captured["prior_messages"] = prior_messages
        return {"confidence": 30, "complete": False, "message": "More info?", "extracted": {}}

    with patch(
        "app.routers.communications.generate_followup",
        new=AsyncMock(side_effect=_fake_followup),
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert response.status_code == 200, response.text
    assert len(captured["prior_messages"]) == 15
    assert captured["prior_messages"][-1]["text"] == "message 14"


async def _seed_thread_at_turn_cap(
    db: AsyncSession, tenant_id: UUID, quote_request: QuoteRequest
) -> None:
    """Seed 3 AI questions (the max follow-up turns) plus a customer reply."""
    base = datetime.utcnow() - timedelta(minutes=10)
    for index in range(3):
        db.add(
            Communication(
                tenant_id=tenant_id,
                contact_id=quote_request.contact_id,
                quote_request_id=quote_request.id,
                channel="in_app_chat",
                direction="outbound",
                sender_role="ai",
                body=f"Question {index}",
                ai_metadata={"complete": False, "confidence": 30},
                created_at=base + timedelta(minutes=index * 2),
            )
        )
    db.add(
        Communication(
            tenant_id=tenant_id,
            contact_id=quote_request.contact_id,
            quote_request_id=quote_request.id,
            channel="in_app_chat",
            direction="inbound",
            sender_role="customer",
            body="Here are my answers",
            created_at=base + timedelta(minutes=7),
        )
    )
    await db.flush()


async def test_ai_followup_dedupes_unanswered_question(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A second ai-followup call before the customer answers returns the same
    message instead of generating another near-identical question."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)

    followup = AsyncMock(
        return_value={
            "confidence": 40,
            "complete": False,
            "message": "Where is the consumer unit located?",
            "extracted": {},
        }
    )
    with patch("app.routers.communications.generate_followup", new=followup):
        first = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")
        second = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["body"] == "Where is the consumer unit located?"
    # The LLM was only called once — the second call hit the dedupe guard.
    assert followup.await_count == 1


async def test_ai_followup_asks_again_after_customer_reply(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """The dedupe guard only applies while the latest message is from the AI."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)

    followup = AsyncMock(
        return_value={
            "confidence": 40,
            "complete": False,
            "message": "And how old is the property?",
            "extracted": {},
        }
    )
    with patch("app.routers.communications.generate_followup", new=followup):
        first = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")
    assert first.status_code == 200

    # The customer replies; the next ai-followup must call the LLM again.
    reply = await admin_client.post(
        "/communications",
        headers={"X-Tenant-ID": str(tenant_id)},
        json={
            "quote_request_id": str(quote_request.id),
            "channel": "in_app_chat",
            "direction": "inbound",
            "body": "It's under the stairs",
        },
    )
    assert reply.status_code == 201, reply.text

    with patch("app.routers.communications.generate_followup", new=followup):
        second = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")
    assert second.status_code == 200, second.text
    assert second.json()["id"] != first.json()["id"]
    assert followup.await_count == 2


async def test_ai_followup_turn_cap_closure_requires_callback(
    admin_client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing via the turn cap without confidence flags the lead for a call."""
    from app.routers import communications as comms_router

    monkeypatch.setattr(comms_router.settings, "max_followup_turns", 3)
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)
    await _seed_thread_at_turn_cap(db, tenant_id, quote_request)

    result_payload = {
        "confidence": 45,
        "complete": False,
        "message": "Anything else we should know?",
        "extracted": {},
        "suggested_questions": ["How old is the existing wiring?"],
    }
    with (
        patch(
            "app.routers.communications.generate_followup",
            new=AsyncMock(return_value=result_payload),
        ),
        patch("app.routers.communications.requote_after_triage_close", new=AsyncMock()) as requote,
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "give you a call" in body["body"]
    assert body["ai_metadata"]["complete"] is True
    assert body["ai_metadata"]["confidence"] == 45
    assert body["ai_metadata"]["requires_callback"] is True
    assert body["ai_metadata"]["suggested_questions"] == ["How old is the existing wiring?"]

    await db.refresh(quote_request)
    assert quote_request.requires_callback is True
    # Closure schedules the background re-quote of the linked draft.
    requote.assert_awaited_once()


async def test_ai_followup_confident_closure_keeps_callback_false(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Closing with confidence keeps the thank-you body and no callback flag."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)

    result_payload = {
        "confidence": 92,
        "complete": True,
        "message": "Thanks, that's everything we need.",
        "extracted": {},
    }
    with (
        patch(
            "app.routers.communications.generate_followup",
            new=AsyncMock(return_value=result_payload),
        ),
        patch("app.routers.communications.requote_after_triage_close", new=AsyncMock()),
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "review your request" in body["body"]
    assert body["ai_metadata"]["complete"] is True
    assert body["ai_metadata"]["confidence"] == 92
    assert body["ai_metadata"]["requires_callback"] is False
    assert "suggested_questions" not in body["ai_metadata"]

    await db.refresh(quote_request)
    assert quote_request.requires_callback is False


async def test_ai_followup_persists_options_in_metadata(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Quick-reply options from the LLM are persisted in ai_metadata."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)

    result_payload = {
        "confidence": 40,
        "complete": False,
        "message": "Where is the fuse box?",
        "extracted": {},
        "options": ["Fuse box under the stairs", "In the garage", "Not sure"],
    }
    with patch(
        "app.routers.communications.generate_followup",
        new=AsyncMock(return_value=result_payload),
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_metadata"]["complete"] is False
    assert body["ai_metadata"]["options"] == [
        "Fuse box under the stairs",
        "In the garage",
        "Not sure",
    ]


async def _make_customer(db: AsyncSession, tenant_id: UUID) -> Any:
    """Create a contact + linked customer account in the given tenant."""
    from app.models import Customer

    await set_tenant_in_session(db, tenant_id)
    contact = Contact(tenant_id=tenant_id, name="Chatty Homeowner", email="chatty@example.com")
    db.add(contact)
    await db.flush()
    customer = Customer(
        tenant_id=tenant_id,
        contact_id=contact.id,
        email="chatty@example.com",
        full_name="Chatty Homeowner",
        password_hash=get_password_hash("homeowner-pass-123"),
        is_active=True,
    )
    db.add(customer)
    await db.flush()
    return customer


def _customer_headers(tenant_id: UUID, customer: Any) -> dict[str, str]:
    from app.security import create_access_token

    token = create_access_token(
        user_id=customer.id,
        tenant_id=tenant_id,
        role="customer",
        email=customer.email,
        subject_type="customer",
    )
    return {"X-Tenant-ID": str(tenant_id), "Authorization": f"Bearer {token}"}


async def test_customer_message_direction_inbound_from_tenant_view(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A customer-authored chat message is inbound, whatever the payload says."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    customer = await _make_customer(db, tenant_id)
    quote_request = await _create_lead(db, tenant_id)
    quote_request.customer_id = customer.id
    await db.flush()

    response = await admin_client.post(
        "/communications",
        headers=_customer_headers(tenant_id, customer),
        json={
            "quote_request_id": str(quote_request.id),
            "channel": "in_app_chat",
            "body": "The breaker trips straight away",
            "direction": "outbound",
            "sender_role": "ai",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["direction"] == "inbound"
    assert body["sender_role"] == "customer"


async def test_staff_message_direction_outbound_even_if_payload_says_inbound(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Staff-authored messages stay outbound regardless of client payload."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)

    response = await admin_client.post(
        "/communications",
        json={
            "quote_request_id": str(quote_request.id),
            "channel": "in_app_chat",
            "body": "We'll take a look",
            "direction": "inbound",
            "sender_role": "customer",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["direction"] == "outbound"
    assert body["sender_role"] == "business"


async def test_ai_followup_notifies_linked_customer(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """A new AI chat message raises a persistent customer notification."""
    from app.models import Notification

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    customer = await _make_customer(db, tenant_id)
    quote_request = await _create_lead(db, tenant_id)
    quote_request.customer_id = customer.id
    await db.flush()

    result_payload = {
        "confidence": 40,
        "complete": False,
        "message": "Where is the consumer unit located?",
        "extracted": {},
    }
    with patch(
        "app.routers.communications.generate_followup",
        new=AsyncMock(return_value=result_payload),
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert response.status_code == 200, response.text

    notification = await db.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.recipient_type == "customer",
            Notification.recipient_id == customer.id,
            Notification.type == "chat_message",
        )
    )
    assert notification is not None
    assert notification.link == f"/customer/chat/{quote_request.id}"


async def test_ai_followup_skips_notification_without_account(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """Leads without a customer account get no in-app notification (email-only)."""
    from app.models import Notification

    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)  # customer_id is None

    result_payload = {
        "confidence": 40,
        "complete": False,
        "message": "Where is the consumer unit located?",
        "extracted": {},
    }
    with patch(
        "app.routers.communications.generate_followup",
        new=AsyncMock(return_value=result_payload),
    ):
        response = await admin_client.post(f"/communications/{quote_request.id}/ai-followup")

    assert response.status_code == 200, response.text
    count = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.tenant_id == tenant_id,
            Notification.recipient_type == "customer",
        )
    )
    assert count == 0


async def test_legacy_customer_message_reads_back_inbound(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """C2: direction is tenant-relative. Rows written before the write-time
    fix stored "outbound" for everything, so customer-authored rows are
    normalised to inbound at read time; staff-logged inbound channels
    (calls/emails) are left untouched."""
    tenant_id = UUID(admin_client.headers["X-Tenant-ID"])
    quote_request = await _create_lead(db, tenant_id)
    legacy_customer_row = Communication(
        tenant_id=tenant_id,
        contact_id=quote_request.contact_id,
        quote_request_id=quote_request.id,
        channel="in_app_chat",
        direction="outbound",  # legacy mis-stored value
        sender_role="customer",
        body="The breaker trips straight away",
    )
    staff_call_log = Communication(
        tenant_id=tenant_id,
        contact_id=quote_request.contact_id,
        quote_request_id=quote_request.id,
        channel="phone_call",
        direction="inbound",  # legitimately inbound, business-authored log
        sender_role="business",
        body="Customer called about the quote",
    )
    db.add_all([legacy_customer_row, staff_call_log])
    await db.commit()

    response = await admin_client.get(f"/communications?quote_request_id={quote_request.id}")
    assert response.status_code == 200, response.text
    by_body = {row["body"]: row for row in response.json()}
    assert by_body["The breaker trips straight away"]["direction"] == "inbound"
    assert by_body["Customer called about the quote"]["direction"] == "inbound"

    # New writes keep deriving direction from the actor (already covered by
    # the create tests) — the AI's own messages stay outbound.
    ai_row = Communication(
        tenant_id=tenant_id,
        quote_request_id=quote_request.id,
        channel="in_app_chat",
        direction="outbound",
        sender_role="ai",
        body="Where is the fuse board?",
    )
    db.add(ai_row)
    await db.commit()
    response = await admin_client.get(f"/communications?quote_request_id={quote_request.id}")
    by_body = {row["body"]: row for row in response.json()}
    assert by_body["Where is the fuse board?"]["direction"] == "outbound"
