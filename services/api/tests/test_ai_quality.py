"""Tests for AI draft feedback capture + keep-rate computation (W1-B).

Covers: the pure matching/metric math on fixture draft/final pairs (unchanged,
price-edited, description-rewritten, line-added, line-removed, mixed, and a
fuzzy pair below the 0.85 threshold), worker idempotence, feedback-row
capture at generation with correct generation_event_id linkage, open-row
reuse on refine, and the send hook (final_snapshot + background compute).

The compute worker opens its own session via ``app.ai_quality.get_db_session``;
integration tests patch it to the per-test session so the worker sees rows
still inside the test transaction (same pattern as test_quote_automation.py).
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app.ai_quality import (
    capture_draft_feedback,
    compute_draft_quality,
    compute_quality_metrics,
    finalize_draft_feedback,
)
from app.config import settings
from app.models import AiDraftFeedback, Quote
from app.rls import TENANT_SCOPED_TABLES, set_tenant_in_session
from httpx import AsyncClient
from sqlalchemy import func, select
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


def _fake_llm_response() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=_LLM_CONTENT),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=50,
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
        patch("app.rag.retrieval.search_knowledge_chunks", new=AsyncMock(return_value=[])),
    )


def _worker_session(db: AsyncSession) -> Any:
    """Patch the compute worker's session factory to the test session."""

    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    return patch("app.ai_quality.get_db_session", _session)


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


async def _generate_quote(client: AsyncClient, tenant: dict[str, Any], contact_id: str) -> str:
    retrieval_patch, llm_patch, knowledge_patch = _mock_pipeline()
    with retrieval_patch, llm_patch, knowledge_patch:
        response = await client.post(
            "/quotes/generate",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"contact_id": contact_id, "description": "Add two double sockets"},
        )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


async def _feedback_rows(db: AsyncSession, quote_id: str) -> list[AiDraftFeedback]:
    rows = await db.execute(
        select(AiDraftFeedback)
        .where(AiDraftFeedback.quote_id == UUID(quote_id))
        .order_by(AiDraftFeedback.created_at.asc())
    )
    return list(rows.scalars().all())


def _snap(lines: list[tuple[str, str, str]]) -> dict[str, Any]:
    """Build a snapshot dict from (description, quantity, unit_price) triples."""
    total = sum(Decimal(qty) * Decimal(price) for _desc, qty, price in lines)
    return {
        "line_items": [
            {"description": desc, "quantity": qty, "unit_price": price}
            for desc, qty, price in lines
        ],
        "total": str(total),
    }


# --- schema -----------------------------------------------------------------


def test_ai_draft_feedback_is_tenant_scoped() -> None:
    """The feedback table is registered for RLS (per-tenant quality reads)."""
    assert "ai_draft_feedback" in TENANT_SCOPED_TABLES


# --- pure metric math --------------------------------------------------------


def test_metrics_unchanged_draft() -> None:
    draft = _snap([("Install one additional double socket", "2", "85.00")])
    metrics = compute_quality_metrics(
        draft, _snap([("Install one additional double socket", "2", "85.00")])
    )
    assert metrics == {
        "keep_rate": Decimal("1.000"),
        "price_drift_pct": Decimal("0.00"),
        "lines_added": 0,
        "lines_removed": 0,
        "description_rewrites": 0,
    }


def test_metrics_price_edited() -> None:
    """Same description, price moved: not 'unchanged', drift reflects the edit."""
    draft = _snap([("Install one additional double socket", "1", "100.00")])
    final = _snap([("Install one additional double socket", "1", "120.00")])
    metrics = compute_quality_metrics(draft, final)
    assert metrics["keep_rate"] == Decimal("0.000")
    assert metrics["price_drift_pct"] == Decimal("20.00")
    assert metrics["lines_added"] == 0
    assert metrics["lines_removed"] == 0
    assert metrics["description_rewrites"] == 0


def test_metrics_description_rewritten() -> None:
    """A fuzzy match (ratio ≥ 0.85) counts as a rewrite, matched for drift."""
    draft = _snap([("Supply and install double socket", "1", "85.00")])
    final = _snap([("Supply and install double socket outlet", "1", "85.00")])
    metrics = compute_quality_metrics(draft, final)
    assert metrics["keep_rate"] == Decimal("0.000")
    assert metrics["description_rewrites"] == 1
    assert metrics["lines_added"] == 0
    assert metrics["lines_removed"] == 0
    assert metrics["price_drift_pct"] == Decimal("0.00")


def test_metrics_line_added() -> None:
    """An added final line never distorts keep_rate or drift."""
    draft = _snap([("Consumer unit replacement labour", "1", "520.00")])
    final = _snap(
        [
            ("Consumer unit replacement labour", "1", "520.00"),
            ("Call-out fee", "1", "45.00"),
        ]
    )
    metrics = compute_quality_metrics(draft, final)
    assert metrics["keep_rate"] == Decimal("1.000")
    assert metrics["lines_added"] == 1
    assert metrics["lines_removed"] == 0
    assert metrics["price_drift_pct"] == Decimal("0.00")


def test_metrics_line_removed() -> None:
    """A removed draft line drops keep_rate to unchanged/total-draft."""
    draft = _snap(
        [
            ("Consumer unit replacement labour", "1", "520.00"),
            ("Call-out fee", "1", "45.00"),
        ]
    )
    final = _snap([("Consumer unit replacement labour", "1", "520.00")])
    metrics = compute_quality_metrics(draft, final)
    assert metrics["keep_rate"] == Decimal("0.500")
    assert metrics["lines_added"] == 0
    assert metrics["lines_removed"] == 1
    # Only matched pairs count, so the removed line does not move the drift.
    assert metrics["price_drift_pct"] == Decimal("0.00")


def test_metrics_mixed() -> None:
    """One unchanged, one price-edited, one rewritten, one added."""
    draft = _snap(
        [
            ("Labour — first fix", "1", "300.00"),
            ("Consumer unit", "1", "480.00"),
            ("Install downlights (per room)", "2", "150.00"),
        ]
    )
    final = _snap(
        [
            ("Labour — first fix", "1", "300.00"),
            ("Consumer unit", "1", "520.00"),
            ("Install LED downlights per room", "2", "150.00"),
            ("Call-out fee", "1", "45.00"),
        ]
    )
    metrics = compute_quality_metrics(draft, final)
    assert metrics["keep_rate"] == Decimal("0.333")  # 1 of 3 unchanged
    assert metrics["description_rewrites"] == 1
    assert metrics["lines_added"] == 1
    assert metrics["lines_removed"] == 0
    # Matched pairs: 300 + 480 + 300 = 1080 → 300 + 520 + 300 = 1120.
    assert metrics["price_drift_pct"] == Decimal("3.70")


def test_metrics_below_fuzzy_threshold_is_add_plus_remove() -> None:
    """A completely re-described line is a removal + addition, not a rewrite,
    and with no matched pairs the drift is undefined (None)."""
    draft = _snap([("Full house rewire", "1", "3500.00")])
    final = _snap([("Garden office lighting circuit", "1", "900.00")])
    metrics = compute_quality_metrics(draft, final)
    assert metrics["keep_rate"] == Decimal("0.000")
    assert metrics["description_rewrites"] == 0
    assert metrics["lines_added"] == 1
    assert metrics["lines_removed"] == 1
    assert metrics["price_drift_pct"] is None


def test_metrics_normalisation_collapses_case_and_whitespace() -> None:
    draft = _snap([("  Install   Double SOCKET ", "1", "85.00")])
    final = _snap([("install double socket", "1", "85.00")])
    metrics = compute_quality_metrics(draft, final)
    assert metrics["keep_rate"] == Decimal("1.000")
    assert metrics["description_rewrites"] == 0


# --- capture at generation ---------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_row_created_at_generation(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generation writes one feedback row linked to the generation event."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    tenant = await _create_tenant(client, f"fbgen-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Feedback Gen")

    quote_id = await _generate_quote(client, tenant, contact["id"])

    await set_tenant_in_session(db, UUID(tenant["id"]))
    rows = await _feedback_rows(db, quote_id)
    assert len(rows) == 1
    row = rows[0]

    quote = await db.get(Quote, UUID(quote_id))
    assert quote is not None
    metadata = quote.ai_metadata or {}

    # Linkage: generation event + trace, straight from ai_metadata.
    assert row.generation_event_id is not None
    assert str(row.generation_event_id) == metadata["last_event_id"]
    assert row.trace_id == metadata["trace_id"]
    assert str(row.tenant_id) == tenant["id"]

    # The draft snapshot mirrors extra_data["ai_draft"]; nothing final yet.
    assert row.draft_snapshot == (quote.extra_data or {}).get("ai_draft")
    assert row.draft_snapshot["line_items"][0]["description"] == (
        "Install one additional double socket"
    )
    assert row.final_snapshot is None
    assert row.keep_rate is None
    assert row.computed_at is None


@pytest.mark.asyncio
async def test_refine_updates_open_row_in_place(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refine reuses the quote's open feedback row (no duplicate) and
    re-links it to the refine's generation event."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    tenant = await _create_tenant(client, f"fbref-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Feedback Refine")
    quote_id = await _generate_quote(client, tenant, contact["id"])

    await set_tenant_in_session(db, UUID(tenant["id"]))
    before = await _feedback_rows(db, quote_id)
    assert len(before) == 1
    first_event_id = before[0].generation_event_id

    retrieval_patch, llm_patch, knowledge_patch = _mock_pipeline()
    with retrieval_patch, llm_patch, knowledge_patch:
        response = await client.post(
            f"/quotes/{quote_id}/refine",
            headers={"X-Tenant-ID": tenant["id"]},
            json={"instructions": "Use cheaper materials"},
        )
    assert response.status_code == 200, response.text

    after = await _feedback_rows(db, quote_id)
    assert len(after) == 1  # same open row, updated — never duplicated
    assert after[0].id == before[0].id
    assert after[0].generation_event_id != first_event_id

    quote = await db.get(Quote, UUID(quote_id))
    assert quote is not None
    assert str(after[0].generation_event_id) == (quote.ai_metadata or {})["last_event_id"]


# --- send hook + worker -------------------------------------------------------


@pytest.mark.asyncio
async def test_send_finalizes_and_computes(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Send writes final_snapshot and the background worker fills metrics."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-llm")
    tenant = await _create_tenant(client, f"fbsend-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Feedback Send")
    quote_id = await _generate_quote(client, tenant, contact["id"])

    # The electrician edits the price before sending: 2 x £85 -> 2 x £100.
    patch_response = await client.patch(
        f"/quotes/{quote_id}",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "line_items": [
                {
                    "description": "Install one additional double socket",
                    "quantity": 2,
                    "unit_price": "100.00",
                }
            ]
        },
    )
    assert patch_response.status_code == 200, patch_response.text

    with _worker_session(db):
        send_response = await client.post(
            f"/quotes/{quote_id}/send", headers={"X-Tenant-ID": tenant["id"]}
        )
    assert send_response.status_code == 200, send_response.text

    await set_tenant_in_session(db, UUID(tenant["id"]))
    rows = await _feedback_rows(db, quote_id)
    assert len(rows) == 1
    row = rows[0]

    # final_snapshot captured the as-sent line items.
    assert row.final_snapshot is not None
    final_lines = row.final_snapshot["line_items"]
    assert len(final_lines) == 1
    assert final_lines[0]["description"] == "Install one additional double socket"
    # String form of the Decimal depends on whether the value round-tripped
    # through the DB (Numeric scale 4), so compare numerically.
    assert Decimal(final_lines[0]["quantity"]) == Decimal("2")
    assert Decimal(final_lines[0]["unit_price"]) == Decimal("100")

    # The background compute ran during the send request (ASGI transport
    # waits for BackgroundTasks): price-edited single line.
    assert row.computed_at is not None
    assert row.keep_rate == Decimal("0.000")
    assert row.lines_added == 0
    assert row.lines_removed == 0
    assert row.description_rewrites == 0
    # 2x85 = 170 -> 2x100 = 200: +30/170 = 17.65%.
    assert row.price_drift_pct == Decimal("17.65")


@pytest.mark.asyncio
async def test_send_without_ai_draft_schedules_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A manually-built quote has no feedback row; send still succeeds."""
    tenant = await _create_tenant(client, f"fbman-{uuid4().hex[:8]}")
    contact = await _create_contact(client, tenant["id"], "Feedback Manual")
    create_response = await client.post(
        "/quotes",
        headers={"X-Tenant-ID": tenant["id"]},
        json={
            "contact_id": contact["id"],
            "title": "Manual quote",
            "line_items": [{"description": "Manual labour", "quantity": 1, "unit_price": "200.00"}],
        },
    )
    assert create_response.status_code == 201, create_response.text
    quote_id = create_response.json()["id"]

    send_response = await client.post(
        f"/quotes/{quote_id}/send", headers={"X-Tenant-ID": tenant["id"]}
    )
    assert send_response.status_code == 200, send_response.text

    await set_tenant_in_session(db, UUID(tenant["id"]))
    assert await _feedback_rows(db, quote_id) == []


# --- worker idempotence + fail-open -------------------------------------------


async def _make_tenant_row(db: AsyncSession) -> UUID:
    """Insert a bare tenant row (feedback rows FK-reference tenants)."""
    from app.models import Tenant

    tenant = Tenant(slug=f"fbw-{uuid4().hex[:8]}", name="Feedback Worker Ltd")
    db.add(tenant)
    await db.flush()
    await set_tenant_in_session(db, tenant.id)
    return tenant.id


async def _make_finalised_row(db: AsyncSession, tenant_id: UUID) -> AiDraftFeedback:
    row = AiDraftFeedback(
        tenant_id=tenant_id,
        quote_id=uuid4(),
        trace_id="trace-idem",
        draft_snapshot=_snap([("Install one additional double socket", "2", "85.00")]),
        final_snapshot=_snap([("Install one additional double socket", "2", "100.00")]),
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_worker_is_idempotent(db: AsyncSession) -> None:
    """Recomputing overwrites metrics in place — same values, no extra rows."""
    tenant_id = await _make_tenant_row(db)
    row = await _make_finalised_row(db, tenant_id)

    with _worker_session(db):
        await compute_draft_quality(row.id, tenant_id)
        first_computed_at = row.computed_at
        await compute_draft_quality(row.id, tenant_id)

    assert row.keep_rate == Decimal("0.000")
    assert row.price_drift_pct == Decimal("17.65")
    assert row.lines_added == 0
    assert row.lines_removed == 0
    assert row.description_rewrites == 0
    assert first_computed_at is not None
    count = await db.scalar(
        select(func.count()).select_from(AiDraftFeedback).where(AiDraftFeedback.id == row.id)
    )
    assert count == 1


@pytest.mark.asyncio
async def test_worker_skips_incomplete_and_missing_rows(db: AsyncSession) -> None:
    """No final_snapshot yet → metrics untouched; unknown id → logged no-op."""
    tenant_id = await _make_tenant_row(db)
    row = AiDraftFeedback(
        tenant_id=tenant_id,
        quote_id=uuid4(),
        draft_snapshot=_snap([("Install one additional double socket", "1", "85.00")]),
    )
    db.add(row)
    await db.flush()

    with _worker_session(db):
        await compute_draft_quality(row.id, tenant_id)
        await compute_draft_quality(uuid4(), tenant_id)  # missing row: no-op

    assert row.keep_rate is None
    assert row.computed_at is None


@pytest.mark.asyncio
async def test_capture_without_draft_snapshot_is_noop(db: AsyncSession) -> None:
    """capture_draft_feedback on a quote with no ai_draft writes nothing."""
    tenant_id = await _make_tenant_row(db)
    quote = Quote(tenant_id=tenant_id, contact_id=uuid4(), title="manual")
    assert await capture_draft_feedback(db, quote) is None
    assert await finalize_draft_feedback(db, quote) is None
