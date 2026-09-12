"""Tests for the AI telemetry foundation (ai_call_events writer + wiring).

Covers the W1-A acceptance criteria: schema round-trip, fail-open proof
(forced DB error → request still succeeds), writer latency budget, cost
stamping, trace/parent linkage across generate→refine→send→accept, and the
anonymous demo path (tenant_id NULL + real model label).
"""

import json
import time
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.ai_telemetry import (
    AiCallContext,
    AiCallTracker,
    get_or_create_trace_id,
    record_ai_event,
)
from app.config import settings
from app.models import AiCallEvent, Quote
from app.rag.generation import QUOTE_DRAFT_PROMPT_VERSION
from app.rls import TENANT_SCOPED_TABLES
from httpx import AsyncClient
from sqlalchemy import Table, select, text
from sqlalchemy.ext.asyncio import AsyncSession

_RETRIEVED = [
    {
        "code": "ELEC-SOCKET-ADD",
        "description": "Install one additional double socket",
        "unit": "each",
        "unit_price": "85.00",
        "category": "Sockets",
    }
]

_LLM_CONTENT = json.dumps(
    {
        "line_items": [
            {
                "code": "ELEC-SOCKET-ADD",
                "quantity": 2,
                "reason": "two new sockets",
                "catalogue_ref": 1,
            }
        ],
        "assumptions": [],
        "notes": "",
    }
)


def _fake_llm_response(prompt_tokens: int = 1200, completion_tokens: int = 300) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=_LLM_CONTENT),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens_details=None,
        ),
    )


def _mock_pipeline() -> Any:
    """Patch retrieval + the LiteLLM call so the REAL generation code runs."""
    return (
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=(_RETRIEVED, "grounded")),
        ),
        patch("app.rag.generation.acompletion", new=AsyncMock(return_value=_fake_llm_response())),
        patch(
            "app.rag.retrieval.search_knowledge_chunks",
            new=AsyncMock(return_value=[]),
        ),
    )


async def _create_tenant(client: AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.post("/tenants", json={"slug": slug, "name": f"{slug} Ltd"})
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


async def _create_contact(client: AsyncClient, tenant_id: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


async def _events_for_trace(db: AsyncSession, trace_id: str) -> list[AiCallEvent]:
    rows = await db.execute(
        select(AiCallEvent)
        .where(AiCallEvent.trace_id == trace_id)
        .order_by(AiCallEvent.created_at.asc())
    )
    return list(rows.scalars().all())


def test_tables_are_not_tenant_scoped() -> None:
    """ai_call_events / fx_rates must stay OUT of RLS (cross-tenant BI reads)."""
    assert "ai_call_events" not in TENANT_SCOPED_TABLES
    assert "fx_rates" not in TENANT_SCOPED_TABLES
    table = AiCallEvent.__table__
    assert isinstance(table, Table)
    index_names = {idx.name for idx in table.indexes}
    assert "ix_ai_call_events_tenant_feature_created" in index_names


@pytest.mark.asyncio
async def test_record_ai_event_schema_round_trip(db: AsyncSession) -> None:
    """A written event round-trips with derived cost/fx fields stamped."""
    tenant_id = uuid4()
    event_id = await record_ai_event(
        db,
        feature="quote_draft",
        tenant_id=tenant_id,
        user_id=uuid4(),
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=200,
        latency_seconds=1.25,
        trace_id="trace-rt",
        prompt_version=QUOTE_DRAFT_PROMPT_VERSION,
        quote_id=uuid4(),
        raw_payload={"k": "v"},
    )
    assert event_id is not None

    event = await db.get(AiCallEvent, event_id)
    assert event is not None
    assert event.tenant_id == tenant_id
    assert event.feature == "quote_draft"
    assert event.status == "success"
    assert event.attempt_no == 1  # column default
    assert event.gen_ai_provider_name == "openai"
    assert event.gen_ai_request_model == "gpt-4o-mini"
    assert event.gen_ai_usage_input_tokens == 1000
    assert event.gen_ai_usage_output_tokens == 500
    assert event.gen_ai_usage_cached_input_tokens == 200
    # (1000*0.00015 + 500*0.0006 + 200*0.000075) / 1000 = 0.000465
    assert event.est_cost_usd == Decimal("0.000465")
    assert event.fx_rate is not None
    assert event.fx_rate_date is not None
    assert event.cost_gbp == (event.est_cost_usd * event.fx_rate).quantize(Decimal("0.0001"))
    assert event.latency_seconds == 1.25
    assert event.raw_payload == {"k": "v"}
    # Prompt text must never reach Postgres.
    assert "prompt" not in {k.lower() for k in event.raw_payload}


@pytest.mark.asyncio
async def test_record_ai_event_fail_open_keeps_session_usable(db: AsyncSession) -> None:
    """A forced DB failure (unserialisable JSONB) returns None and the
    savepoint rollback leaves the caller's transaction fully usable."""
    result = await record_ai_event(
        db,
        feature="quote_draft",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=5,
        raw_payload={"bad": object()},  # asyncpg cannot encode this
    )
    assert result is None
    # The business transaction still works afterwards.
    assert (await db.execute(text("SELECT 1"))).scalar() == 1
    ok = await record_ai_event(db, feature="outcome", raw_payload={"outcome": "quote_sent"})
    assert ok is not None


@pytest.mark.asyncio
async def test_record_ai_event_fail_open_without_session() -> None:
    """The own-session path also swallows failures (patched session factory)."""
    with patch("app.database.get_db_session", side_effect=RuntimeError("forced session failure")):
        result = await record_ai_event(
            None, feature="embedding", model="text-embedding-3-large", input_tokens=10
        )
    assert result is None


@pytest.mark.asyncio
async def test_generate_endpoint_survives_telemetry_db_error(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-open proof: with the event constructor exploding, POST
    /quotes/generate still succeeds end-to-end."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    tenant = await _create_tenant(client, f"failopen-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Fail Open")
    retrieval_patch, llm_patch, knowledge_patch = _mock_pipeline()
    with (
        retrieval_patch,
        llm_patch,
        knowledge_patch,
        patch(
            "app.ai_telemetry.AiCallEvent",
            side_effect=RuntimeError("forced db error"),
        ),
    ):
        response = await client.post(
            "/quotes/generate",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"contact_id": contact["id"], "description": "Add two sockets please"},
        )
    assert response.status_code == 201, response.text
    assert response.json()["line_items"]


@pytest.mark.asyncio
async def test_writer_latency_p95_under_50ms(db: AsyncSession) -> None:
    """100 sequential writes; p95 must stay under the 50ms budget."""
    durations: list[float] = []
    for _ in range(100):
        started = time.perf_counter()
        await record_ai_event(
            db,
            feature="embedding",
            model="text-embedding-3-large",
            input_tokens=42,
            output_tokens=0,
            trace_id="latency-bench",
        )
        durations.append(time.perf_counter() - started)
    durations.sort()
    p95 = durations[94]
    assert p95 < 0.050, f"writer p95 {p95 * 1000:.1f}ms exceeds 50ms budget"


@pytest.mark.asyncio
async def test_trace_parent_linkage_generate_refine_send_accept(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate→refine→send→accept share one trace; refine links its parent."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    tenant = await _create_tenant(client, f"trace-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Trace Customer")
    retrieval_patch, llm_patch, knowledge_patch = _mock_pipeline()

    with retrieval_patch, llm_patch, knowledge_patch:
        gen_response = await client.post(
            "/quotes/generate",
            headers={"X-Tenant-ID": tenant["id"]},
            json={
                "contact_id": contact["id"],
                "description": "I need two extra double sockets installed",
            },
        )
        assert gen_response.status_code == 201, gen_response.text
        quote_id = gen_response.json()["id"]

        refine_response = await client.post(
            f"/quotes/{quote_id}/refine",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"instructions": "Use cheaper materials"},
        )
        assert refine_response.status_code == 200, refine_response.text

    quote = await db.get(Quote, quote_id)
    assert quote is not None
    trace_id = (quote.ai_metadata or {}).get("trace_id")
    assert trace_id

    send_response = await client.post(
        f"/quotes/{quote_id}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert send_response.status_code == 200, send_response.text
    approve_response = await client.post(
        f"/quotes/{quote_id}/approve",
        headers={"X-Tenant-ID": tenant["id"]},
        json={"approved": True},
    )
    assert approve_response.status_code == 200, approve_response.text

    events = await _events_for_trace(db, str(trace_id))
    by_feature: dict[str, list[AiCallEvent]] = {}
    for event in events:
        by_feature.setdefault(event.feature, []).append(event)

    draft = by_feature["quote_draft"][0]
    refine = by_feature["quote_refine"][0]
    outcomes = {e.raw_payload.get("outcome"): e for e in by_feature.get("outcome", [])}

    # Draft event: real model label, prompt version, tokens + derived cost.
    assert draft.gen_ai_request_model == settings.llm_model
    assert draft.prompt_version == QUOTE_DRAFT_PROMPT_VERSION
    assert draft.attempt_no == 1
    assert draft.gen_ai_usage_input_tokens == 1200
    assert draft.gen_ai_usage_output_tokens == 300
    assert draft.est_cost_usd is not None
    assert draft.cost_gbp is not None
    assert draft.fx_rate is not None
    assert draft.latency_seconds is not None and draft.latency_seconds >= 0
    assert draft.status == "success"
    assert str(draft.quote_id) == quote_id
    assert str(draft.tenant_id) == tenant["id"]

    # Refine links to the draft via parent_event_id on the same trace.
    assert refine.parent_event_id == draft.id
    assert refine.attempt_no == 2
    assert refine.gen_ai_request_model == settings.llm_model
    assert refine.prompt_version == QUOTE_DRAFT_PROMPT_VERSION

    # Outcomes carry the trace (and no model/cost) so cost↔outcome joins work.
    assert set(outcomes) == {"quote_sent", "quote_accepted"}
    for outcome in outcomes.values():
        assert outcome.gen_ai_request_model is None
        assert outcome.est_cost_usd is None
        assert outcome.status == "success"


async def _clean_demo_used_flags() -> None:
    """Delete the demo one-shot Redis flags (bare-IP backstop included) so the
    gate does not leak between demo tests. Mirrors test_demo_quotes.py."""
    from app.redis_client import get_redis
    from app.routers.demo import _DEMO_USED_IP_KEY_PREFIX, _DEMO_USED_KEY_PREFIX

    redis = get_redis()
    for prefix in (_DEMO_USED_KEY_PREFIX, _DEMO_USED_IP_KEY_PREFIX):
        keys = [key async for key in redis.scan_iter(match=f"{prefix}*")]
        if keys:
            await redis.delete(*keys)


@pytest.mark.asyncio
async def test_demo_event_has_null_tenant_and_real_model_label(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The anonymous demo records tenant_id=NULL and the ACTUAL override
    model (gpt-4o-mini), not the configured production model."""
    await _clean_demo_used_flags()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai")
    monkeypatch.setattr(settings, "demo_llm_model", "gpt-4o-mini")
    monkeypatch.setattr(settings, "llm_model", "openai/kimi-k2.6")
    unique_ua = f"pytest-ai-telemetry/{uuid4().hex}"
    with (
        patch(
            "app.routers.demo.search_cost_items_with_status",
            new=AsyncMock(return_value=(_RETRIEVED, "grounded")),
        ),
        patch("app.rag.generation.acompletion", new=AsyncMock(return_value=_fake_llm_response())),
        patch("app.rag.retrieval.search_knowledge_chunks", new=AsyncMock(return_value=[])),
    ):
        response = await client.post(
            "/demo/quotes/generate",
            json={"description": "Install two extra double sockets in the kitchen"},
            headers={"user-agent": unique_ua},
        )
    assert response.status_code == 200, response.text

    rows = await db.execute(select(AiCallEvent).where(AiCallEvent.feature == "demo_quote"))
    events = list(rows.scalars().all())
    assert len(events) == 1
    event = events[0]
    assert event.tenant_id is None
    assert event.user_id is None
    # The actual model used (demo override), NOT settings.llm_model.
    assert event.gen_ai_request_model == "gpt-4o-mini"
    assert event.gen_ai_request_model != settings.llm_model
    # gpt-4o-mini pricing, not kimi pricing: (1200*0.00015 + 300*0.0006)/1000
    assert event.est_cost_usd == Decimal("0.000360")
    assert event.cost_gbp is not None
    assert event.prompt_version == QUOTE_DRAFT_PROMPT_VERSION
    assert event.raw_payload.get("ip_hash")
    assert event.raw_payload.get("kind") == "generate"
    assert event.trace_id
    await _clean_demo_used_flags()


@pytest.mark.asyncio
async def test_tracker_records_error_status_and_reraises(db: AsyncSession) -> None:
    """An exception inside the tracked block is recorded (status=error) and
    still propagates to the caller."""
    ctx = AiCallContext(feature="quote_draft", db=db, trace_id="tracker-error")
    with pytest.raises(RuntimeError, match="boom"):
        async with AiCallTracker(ctx, model="gpt-4o-mini"):
            raise RuntimeError("boom")
    assert ctx.event_id is not None
    event = await db.get(AiCallEvent, ctx.event_id)
    assert event is not None
    assert event.status == "error"
    assert event.latency_seconds is not None


@pytest.mark.asyncio
async def test_get_or_create_trace_id_is_stable(db: AsyncSession) -> None:
    tenant_id = uuid4()
    contact_id = uuid4()
    quote = Quote(tenant_id=tenant_id, contact_id=contact_id, title="t")
    first = get_or_create_trace_id(quote)
    second = get_or_create_trace_id(quote)
    assert first == second
    assert quote.ai_metadata["trace_id"] == first
