"""Tests for guest tokens, the sync intake AI check and public photo upload."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app import config
from app.guest_auth import issue_guest_token, verify_guest_token
from app.models import AiCallEvent, Customer, QuoteRequest, Tenant
from app.rls import bypass_rls_in_session, set_tenant_in_session
from app.security import create_access_token
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
    """Build a LiteLLM-shaped response carrying ``payload`` as JSON content."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload)),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=20,
            prompt_tokens_details=None,
        ),
    )


def _intake_payload(email: str | None = "guest@example.com") -> dict[str, Any]:
    return {
        "contact": {
            "name": "Guest Homeowner",
            "email": email,
            "phone": "07700 900111",
            "postcode": "SK8 3NJ",
        },
        "category": "consumer_unit",
        "title": "Consumer unit upgrade",
        "raw_text": "Fuse box keeps tripping, want it replaced.",
        "sync_check": True,
        "entry_channel": "widget",
    }


# --- Guest tokens ------------------------------------------------------------


def test_guest_token_roundtrip() -> None:
    qr_id, tenant_id = uuid4(), uuid4()
    token, expires_at = issue_guest_token(qr_id, tenant_id)
    claims = verify_guest_token(token, qr_id)
    assert claims is not None
    assert claims["subject_type"] == "guest"
    assert claims["qr_id"] == str(qr_id)
    assert claims["tenant_id"] == str(tenant_id)
    assert expires_at is not None


def test_guest_token_wrong_quote_request_rejected() -> None:
    token, _ = issue_guest_token(uuid4(), uuid4())
    assert verify_guest_token(token, uuid4()) is None


def test_guest_token_tampered_rejected() -> None:
    qr_id = uuid4()
    token, _ = issue_guest_token(qr_id, uuid4())
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert verify_guest_token(tampered, qr_id) is None


def test_guest_token_customer_token_rejected() -> None:
    qr_id, tenant_id = uuid4(), uuid4()
    customer_token = create_access_token(
        user_id=uuid4(),
        tenant_id=tenant_id,
        role="customer",
        email="c@example.com",
        subject_type="customer",
    )
    assert verify_guest_token(customer_token, qr_id) is None


def test_guest_token_expired_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GUEST_THREAD_TTL_MINUTES", -1)
    qr_id = uuid4()
    token, _ = issue_guest_token(qr_id, uuid4())
    assert verify_guest_token(token, qr_id) is None


# --- Sync intake check on the public endpoint --------------------------------


async def test_sync_check_questions_returns_thread_token(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    monkeypatch.setattr(config.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        "app.intake_triage.acompletion",
        AsyncMock(
            return_value=_fake_llm_response(
                {"needs_followup": True, "question": "How many bedrooms does the property have?"}
            )
        ),
    )

    response = await client.post(f"/businesses/{slug}/quote-requests", json=_intake_payload())
    assert response.status_code == 201, response.text
    ack = response.json()
    ai_check = ack["ai_check"]
    assert ai_check["status"] == "questions"
    assert ai_check["question"] == "How many bedrooms does the property have?"
    assert ai_check["thread_token"]
    assert ai_check["thread_expires_at"]

    # The AI question was persisted on the thread.
    await set_tenant_in_session(db, tenant.id)
    quote_request = await db.get(QuoteRequest, UUID(ack["id"]))
    assert quote_request is not None
    from app.models import Communication

    ai_message = await db.scalar(
        select(Communication).where(
            Communication.quote_request_id == quote_request.id,
            Communication.sender_role == "ai",
        )
    )
    assert ai_message is not None
    assert ai_message.body == "How many bedrooms does the property have?"


async def test_sync_check_ok(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    monkeypatch.setattr(config.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        "app.intake_triage.acompletion",
        AsyncMock(return_value=_fake_llm_response({"needs_followup": False, "question": None})),
    )

    response = await client.post(f"/businesses/{slug}/quote-requests", json=_intake_payload())
    assert response.status_code == 201, response.text
    ai_check = response.json()["ai_check"]
    assert ai_check["status"] == "ok"
    assert ai_check["question"] is None
    assert ai_check["thread_token"] is None


async def test_sync_check_llm_error_is_unavailable(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    monkeypatch.setattr(config.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        "app.intake_triage.acompletion",
        AsyncMock(side_effect=RuntimeError("provider down")),
    )

    response = await client.post(f"/businesses/{slug}/quote-requests", json=_intake_payload())
    assert response.status_code == 201, response.text
    assert response.json()["ai_check"]["status"] == "unavailable"


async def test_sync_check_timeout_is_unavailable(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    monkeypatch.setattr(config.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(config, "INTAKE_TRIAGE_TIMEOUT_SECONDS", 0.05)

    async def _slow_completion(**kwargs: Any) -> Any:
        await asyncio.sleep(5)
        return _fake_llm_response({"needs_followup": False, "question": None})

    monkeypatch.setattr("app.intake_triage.acompletion", _slow_completion)

    response = await client.post(f"/businesses/{slug}/quote-requests", json=_intake_payload())
    assert response.status_code == 201, response.text
    assert response.json()["ai_check"]["status"] == "unavailable"


async def test_sync_check_telemetry_recorded(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    monkeypatch.setattr(config.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        "app.intake_triage.acompletion",
        AsyncMock(return_value=_fake_llm_response({"needs_followup": False, "question": None})),
    )

    response = await client.post(f"/businesses/{slug}/quote-requests", json=_intake_payload())
    assert response.status_code == 201, response.text

    event = await db.scalar(select(AiCallEvent).where(AiCallEvent.feature == "intake_triage"))
    assert event is not None
    assert event.actor_type == "customer"
    assert event.entry_channel == "widget"
    assert event.status == "success"
    assert event.gen_ai_request_model == config.INTAKE_TRIAGE_MODEL
    assert event.gen_ai_usage_input_tokens == 120
    assert event.gen_ai_usage_output_tokens == 20


async def test_entry_channel_validation(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    payload = _intake_payload()
    payload["entry_channel"] = "carrier_pigeon"
    response = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    assert response.status_code == 422


async def test_submission_without_sync_check_has_no_ai_check(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    payload = _intake_payload()
    del payload["sync_check"]
    del payload["entry_channel"]
    response = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["ai_check"] is None


# --- Customer auto-provisioning ----------------------------------------------


async def test_submission_with_email_provisions_customer(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    payload = _intake_payload(email="new-homeowner@example.com")
    del payload["sync_check"]

    response = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    assert response.status_code == 201, response.text

    await set_tenant_in_session(db, tenant.id)
    customer = await db.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
            Customer.email == "new-homeowner@example.com",
        )
    )
    assert customer is not None
    assert customer.password_hash is None
    assert customer.is_active is True
    assert customer.contact_id is not None

    quote_request = await db.scalar(select(QuoteRequest).where(QuoteRequest.tenant_id == tenant.id))
    assert quote_request is not None
    assert quote_request.customer_id == customer.id


async def test_submission_reuses_existing_customer(client: AsyncClient, db: AsyncSession) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    payload = _intake_payload(email="repeat@example.com")
    del payload["sync_check"]

    first = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    second = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201

    await set_tenant_in_session(db, tenant.id)
    customers = (
        await db.scalars(
            select(Customer).where(
                Customer.tenant_id == tenant.id,
                Customer.email == "repeat@example.com",
            )
        )
    ).all()
    assert len(customers) == 1


async def test_submission_without_email_provisions_no_customer(
    client: AsyncClient, db: AsyncSession
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    payload = _intake_payload(email=None)
    del payload["sync_check"]

    response = await client.post(f"/businesses/{slug}/quote-requests", json=payload)
    assert response.status_code == 201, response.text

    await set_tenant_in_session(db, tenant.id)
    count = await db.scalar(select(Customer).where(Customer.tenant_id == tenant.id))
    assert count is None


# --- Public intake photo upload ----------------------------------------------


def _mock_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_store(tenant_id: Any, file: Any, content: bytes) -> dict[str, str]:
        key = f"tenants/{tenant_id}/intake/{uuid4()}/{file.filename}"
        return {"key": key, "url": f"/files/download?key={key}"}

    monkeypatch.setattr("app.routers.businesses._store_intake_upload", _fake_store)


async def test_intake_upload_happy_path(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    tenant = await _create_tenant(db, slug)
    _mock_storage(monkeypatch)

    response = await client.post(
        f"/businesses/{slug}/quote-requests/uploads",
        files=[
            ("files", ("a.jpg", b"\xff\xd8\xff" + b"0" * 100, "image/jpeg")),
            ("files", ("b.png", b"\x89PNG" + b"0" * 100, "image/png")),
        ],
    )
    assert response.status_code == 201, response.text
    urls = response.json()["urls"]
    assert len(urls) == 2
    assert all(f"tenants/{tenant.id}/intake/" in url for url in urls)


async def test_intake_upload_rejects_bad_content_type(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    _mock_storage(monkeypatch)

    response = await client.post(
        f"/businesses/{slug}/quote-requests/uploads",
        files=[("files", ("evil.exe", b"MZ" + b"0" * 100, "application/x-msdownload"))],
    )
    assert response.status_code == 415


async def test_intake_upload_rejects_oversize(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    _mock_storage(monkeypatch)

    big = b"0" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        f"/businesses/{slug}/quote-requests/uploads",
        files=[("files", ("big.jpg", big, "image/jpeg"))],
    )
    assert response.status_code == 413


async def test_intake_upload_rejects_too_many_files(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"pub-{uuid4().hex[:8]}"
    await _create_tenant(db, slug)
    _mock_storage(monkeypatch)

    response = await client.post(
        f"/businesses/{slug}/quote-requests/uploads",
        files=[
            ("files", (f"p{i}.jpg", b"\xff\xd8\xff" + b"0" * 10, "image/jpeg")) for i in range(6)
        ],
    )
    assert response.status_code == 422
