"""Tests for the guest-scoped public chat thread endpoints."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app import config
from app.guest_auth import issue_guest_token
from app.models import Communication, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.utils.tenant_code import generate_unique_tenant_code
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_tenant(db: AsyncSession, slug: str) -> Tenant:
    await bypass_rls_in_session(db)
    code = await generate_unique_tenant_code(db)
    tenant = Tenant(slug=slug, code=code, name=f"{slug} Electrical")
    db.add(tenant)
    await db.flush()
    return tenant


def _fake_llm_response(payload: dict[str, Any]) -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=None),
    )


async def _submit_with_question(
    client: AsyncClient, db: AsyncSession, slug: str, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Submit a quote request whose sync check returns a follow-up question."""
    monkeypatch.setattr(config.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        "app.intake_triage.acompletion",
        AsyncMock(
            return_value=_fake_llm_response(
                {"needs_followup": True, "question": "How old is the current fuse box?"}
            )
        ),
    )
    response = await client.post(
        f"/businesses/{slug}/quote-requests",
        json={
            "contact": {"name": "Thread Guest", "email": "thread@example.com"},
            "category": "consumer_unit",
            "title": "Fuse box replacement",
            "sync_check": True,
        },
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def _followup_payload(confidence: int, complete: bool, message: str) -> dict[str, Any]:
    return {
        "confidence": confidence,
        "complete": complete,
        "message": message,
        "extracted": {"fuse_box_age": "about 20 years"},
        "options": [],
        "suggested_questions": [],
        "usage": None,
        "model": "gpt-4o-mini",
    }


async def test_thread_flow_question_reply_closure(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    ack = await _submit_with_question(client, db, slug, monkeypatch)
    qr_id = ack["id"]
    token = ack["ai_check"]["thread_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Guest reads the thread: the AI question is there.
    listing = await client.get(f"/public/threads/{qr_id}/messages", headers=headers)
    assert listing.status_code == 200, listing.text
    messages = listing.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["sender_role"] == "ai"
    assert messages[0]["body"] == "How old is the current fuse box?"

    # Guest answers; the AI reaches confidence and closes the thread.
    followup = AsyncMock(return_value=_followup_payload(85, True, "Thanks, that's everything."))
    requote = AsyncMock()
    monkeypatch.setattr("app.routers.public_threads.generate_followup", followup)
    monkeypatch.setattr("app.routers.public_threads.requote_after_triage_close", requote)
    reply = await client.post(
        f"/public/threads/{qr_id}/messages",
        headers=headers,
        json={"body": "It's about 20 years old."},
    )
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert data["message"]["sender_role"] == "customer"
    assert data["message"]["body"] == "It's about 20 years old."
    assert data["closed"] is True
    assert data["ai_reply"] is not None
    # Closure schedules the background requote with the tenant + thread ids.
    requote.assert_called_once_with(tenant.id, UUID(qr_id))

    # The thread now holds question + answer + closure, and the closure row
    # carries the complete flag; the extracted fact landed on the request.
    await set_tenant_in_session(db, tenant.id)
    rows = (
        await db.scalars(
            select(Communication)
            .where(Communication.quote_request_id == UUID(qr_id))
            .order_by(Communication.created_at.asc())
        )
    ).all()
    assert [row.sender_role for row in rows] == ["ai", "customer", "ai"]
    customer_row = rows[1]
    assert customer_row.direction == "inbound"
    closure_row = rows[2]
    assert closure_row.ai_metadata["complete"] is True
    quote_request = await db.scalar(select(QuoteRequest).where(QuoteRequest.id == UUID(qr_id)))
    assert quote_request is not None
    assert quote_request.structured_data["ai_extracted"]["fuse_box_age"] == "about 20 years"

    # Posting again on the closed thread returns the closure, no new AI turn.
    again = await client.post(
        f"/public/threads/{qr_id}/messages",
        headers=headers,
        json={"body": "Anything else?"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["closed"] is True


async def test_thread_reply_open_turn_not_closed(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    ack = await _submit_with_question(client, db, slug, monkeypatch)
    qr_id = ack["id"]
    headers = {"Authorization": f"Bearer {ack['ai_check']['thread_token']}"}

    monkeypatch.setattr(
        "app.routers.public_threads.generate_followup",
        AsyncMock(return_value=_followup_payload(40, False, "And where is it located?")),
    )
    reply = await client.post(
        f"/public/threads/{qr_id}/messages",
        headers=headers,
        json={"body": "It's about 20 years old."},
    )
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert data["closed"] is False
    assert data["ai_reply"]["body"] == "And where is it located?"


async def test_thread_ai_failure_returns_message_without_reply(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    ack = await _submit_with_question(client, db, slug, monkeypatch)
    qr_id = ack["id"]
    headers = {"Authorization": f"Bearer {ack['ai_check']['thread_token']}"}

    monkeypatch.setattr(
        "app.routers.public_threads.generate_followup",
        AsyncMock(side_effect=RuntimeError("LLM service unavailable")),
    )
    reply = await client.post(
        f"/public/threads/{qr_id}/messages",
        headers=headers,
        json={"body": "It's about 20 years old."},
    )
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert data["message"]["body"] == "It's about 20 years old."
    assert data["ai_reply"] is None
    assert data["closed"] is False


async def test_guest_followup_slow_llm_within_budget_returns_ai_reply(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow-but-within-budget LLM still returns the ai_reply (Fixes #117)."""
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    ack = await _submit_with_question(client, db, slug, monkeypatch)
    qr_id = ack["id"]
    headers = {"Authorization": f"Bearer {ack['ai_check']['thread_token']}"}

    # Generous budget, LLM that takes a beat: the portal awaits ai_reply.
    monkeypatch.setattr(config.settings, "guest_followup_timeout_seconds", 30.0)

    async def slow_followup(*args: Any, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return _followup_payload(40, False, "And where is it located?")

    monkeypatch.setattr(
        "app.routers.public_threads.generate_followup", AsyncMock(side_effect=slow_followup)
    )
    reply = await client.post(
        f"/public/threads/{qr_id}/messages",
        headers=headers,
        json={"body": "It's about 20 years old."},
    )
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert data["message"]["body"] == "It's about 20 years old."
    assert data["closed"] is False
    assert data["ai_reply"] is not None
    assert data["ai_reply"]["body"] == "And where is it located?"


async def test_guest_followup_beyond_budget_fails_open(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A too-slow LLM stores the message and returns ai_reply=null (Fixes #117)."""
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    ack = await _submit_with_question(client, db, slug, monkeypatch)
    qr_id = ack["id"]
    headers = {"Authorization": f"Bearer {ack['ai_check']['thread_token']}"}

    monkeypatch.setattr(config.settings, "guest_followup_timeout_seconds", 0.05)

    async def too_slow_followup(*args: Any, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(5)
        return _followup_payload(85, True, "too late")

    monkeypatch.setattr(
        "app.routers.public_threads.generate_followup", AsyncMock(side_effect=too_slow_followup)
    )
    reply = await client.post(
        f"/public/threads/{qr_id}/messages",
        headers=headers,
        json={"body": "It's about 20 years old."},
    )
    assert reply.status_code == 200, reply.text
    data = reply.json()
    # Fail-open: the customer's message is stored and returned, no 5xx.
    assert data["message"]["body"] == "It's about 20 years old."
    assert data["ai_reply"] is None
    assert data["closed"] is False


async def test_thread_requires_token(client: AsyncClient, db: AsyncSession) -> None:
    response = await client.get(f"/public/threads/{uuid4()}/messages")
    assert response.status_code == 401


async def test_thread_token_scoped_to_one_quote_request(
    client: AsyncClient, db: AsyncSession
) -> None:
    # A guest token minted for one quote request cannot open another thread.
    token, _ = issue_guest_token(uuid4(), uuid4())
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(f"/public/threads/{uuid4()}/messages", headers=headers)
    assert response.status_code == 401


async def test_thread_token_rejected_for_other_thread(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    ack = await _submit_with_question(client, db, slug, monkeypatch)

    # Token for a DIFFERENT (non-existent) quote request of the same tenant.
    other_token, _ = issue_guest_token(uuid4(), tenant.id)
    response = await client.get(
        f"/public/threads/{ack['id']}/messages",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 401


async def test_thread_get_with_valid_token_unknown_qr_is_404(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    await _submit_with_question(client, db, slug, monkeypatch)

    unknown_qr = uuid4()
    token, _ = issue_guest_token(unknown_qr, tenant.id)
    response = await client.get(
        f"/public/threads/{unknown_qr}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
