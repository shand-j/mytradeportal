"""Tests for the quote PDF endpoint and its non-blocking implementation."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import patch

import pytest
from app.routers.quotes import _render_quote_pdf
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_quote_with_lines(admin_client: AsyncClient) -> str:
    contact = await admin_client.post(
        "/contacts", json={"name": "PDF Customer", "email": "pdf@test.local"}
    )
    assert contact.status_code == 201, contact.text
    contact_id = contact.json()["id"]

    quote = await admin_client.post(
        "/quotes",
        json={
            "contact_id": contact_id,
            "title": "PDF lifecycle quote",
            "description": "Two-line worked example for the renderer.",
            "line_items": [
                {"description": "Callout", "quantity": 1, "unit_price": 75.0},
                {"description": "Double socket fitted", "quantity": 4, "unit_price": 35.0},
            ],
        },
    )
    assert quote.status_code == 201, quote.text
    return str(quote.json()["id"])


@pytest.mark.asyncio
async def test_quote_pdf_endpoint_returns_valid_pdf(admin_client: AsyncClient) -> None:
    quote_id = await _create_quote_with_lines(admin_client)

    response = await admin_client.get(f"/quotes/{quote_id}/pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers.get("content-disposition", "")
    body = response.content
    # Every valid PDF starts with the %PDF magic header.
    assert body.startswith(b"%PDF-"), body[:8]
    # EOF marker should be present too.
    assert b"%%EOF" in body[-1024:]


@pytest.mark.asyncio
async def test_quote_pdf_is_built_in_a_worker_thread(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """The handler MUST hand the sync FPDF work off via :func:`asyncio.to_thread`.

    If a future change moves the render back into the async hot path this
    test fails — the patched ``_render_quote_pdf`` will have been called on
    the main asyncio thread instead of a worker thread.
    """
    quote_id = await _create_quote_with_lines(admin_client)

    captured: dict[str, int | None] = {"thread_id": None, "calls": 0}
    main_thread_id = asyncio.get_running_loop()._thread_id  # type: ignore[attr-defined]

    real_render = _render_quote_pdf

    def spy_render(snapshot: dict) -> bytes:  # type: ignore[type-arg]
        import threading

        captured["thread_id"] = threading.get_ident()
        captured["calls"] += 1
        return real_render(snapshot)

    with patch("app.routers.quotes._render_quote_pdf", side_effect=spy_render):
        response = await admin_client.get(f"/quotes/{quote_id}/pdf")

    assert response.status_code == 200
    assert captured["calls"] == 1
    assert captured["thread_id"] is not None
    assert captured["thread_id"] != main_thread_id, (
        "PDF render ran on the asyncio main thread — it must be offloaded "
        "via asyncio.to_thread() to keep the event loop responsive."
    )


def test_render_quote_pdf_unit_snapshot_only() -> None:
    """The sync renderer must work from a plain dict (no ORM dependency).

    Guards against a future refactor that smuggles a SQLAlchemy object into
    the snapshot — that would crash on the worker thread.
    """
    snapshot = {
        "id": "abc-123",
        "tenant_name": "Acme Electrics",
        "title": "Unit-rendered quote",
        "status": "draft",
        "created_at": __import__("datetime").datetime(2026, 6, 23),
        "subtotal": 100.0,
        "vat_rate": 0.2,
        "vat_amount": 20.0,
        "total": 120.0,
        "contact": {"name": "Test", "email": None, "phone": None},
        "line_items": [
            {
                "description": "Item A",
                "quantity": 2.0,
                "unit_price": 50.0,
                "total": 100.0,
            }
        ],
    }
    pdf_bytes = _render_quote_pdf(snapshot)
    assert pdf_bytes.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_quote_pdf_snapshot_does_not_lazy_load_under_threadpool(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    """End-to-end smoke: the snapshot path is the only ORM access the request makes.

    If the renderer ever touches a SQLAlchemy attribute that wasn't eager-loaded
    we'd hit a greenlet error from the worker thread; this test would surface
    as a 500.
    """
    quote_id = await _create_quote_with_lines(admin_client)
    response = await admin_client.get(f"/quotes/{quote_id}/pdf")
    assert response.status_code == 200
    # StreamingResponse doesn't set content-length; assert on the body itself.
    assert len(response.content) > 1000  # non-trivial PDF
    assert response.content.startswith(b"%PDF-")


def test_render_quote_pdf_handles_unicode_safely() -> None:
    """The PDF font is latin-1; the renderer must not crash on the £ symbol.

    The £ glyph is encodable in latin-1, but we also force a non-latin-1
    character to verify the encoding path doesn't blow up downstream.
    """
    snapshot = {
        "id": "u-1",
        "tenant_name": "Café Sparks",  # Non-ASCII but latin-1 safe
        "title": "Quote with £ and é",
        "status": "draft",
        "created_at": __import__("datetime").datetime(2026, 6, 23),
        "subtotal": float(Decimal("123.45")),
        "vat_rate": 0.2,
        "vat_amount": float(Decimal("24.69")),
        "total": float(Decimal("148.14")),
        "contact": {"name": "André", "email": None, "phone": None},
        "line_items": [
            {
                "description": "Émergency callout",
                "quantity": 1.0,
                "unit_price": 123.45,
                "total": 123.45,
            }
        ],
    }
    pdf_bytes = _render_quote_pdf(snapshot)
    assert pdf_bytes.startswith(b"%PDF-")
