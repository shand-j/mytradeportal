"""Tests for analytics dashboard endpoints."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_contact(client: AsyncClient, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_quote(client: AsyncClient, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/quotes",
        json={
            "contact_id": contact_id,
            "title": "Rewire quote",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "500.00"},
                {"description": "Parts", "quantity": "2", "unit_price": "50.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def _create_invoice(client: AsyncClient, contact_id: str) -> dict[str, Any]:
    response = await client.post(
        "/invoices",
        json={
            "contact_id": contact_id,
            "invoice_number": "INV-101",
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "400.00"},
            ],
        },
    )
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def test_dashboard_returns_expected_structure(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "kpi" in data
    assert "revenue_chart" in data
    assert "service_breakdown" in data
    assert "recent_activity" in data
    assert "voice_stats" in data
    # Voice AI is not yet implemented; voice_stats is returned as null.
    assert data["voice_stats"] is None


async def test_dashboard_kpis_reflect_data(admin_client: AsyncClient) -> None:
    contact = await _create_contact(admin_client, "Analytics Customer")
    quote = await _create_quote(admin_client, contact["id"])
    await admin_client.post(f"/quotes/{quote['id']}/approve", json={"approved": True})

    invoice = await _create_invoice(admin_client, contact["id"])
    await admin_client.post(f"/invoices/{invoice['id']}/mark-paid")

    response = await admin_client.get("/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["kpi"]["pending_quotes"] == 0
    assert data["kpi"]["active_jobs"] == 0
    # Bootstrap tenant has not answered the onboarding Tax step, so it is not
    # VAT registered: £100 x 4 at 0% VAT.
    assert Decimal(str(data["kpi"]["revenue_this_month"])) == Decimal("400.00")


async def test_ai_insights_returns_expected_structure(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/analytics/ai-insights")
    assert response.status_code == 200
    data = response.json()
    assert "ai_quote_performance" in data
    assert isinstance(data["ai_quote_performance"], dict)
    assert "total_generated" in data["ai_quote_performance"]
    # New optional fields are always present (null when no AI data exists).
    assert "edit_rate" in data["ai_quote_performance"]
    assert "avg_price_drift_pct" in data["ai_quote_performance"]
    # Demand forecasting and voice analytics are not yet implemented; they are
    # returned as null until their feature flags are enabled.
    assert data.get("demand_forecast") is None
    assert data.get("voice_analytics") is None


async def _create_ai_quote(admin_client: AsyncClient, contact_id: str) -> dict[str, Any]:
    generated = {
        "line_items": [
            {
                "description": "Security light installation (labour)",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 300.00,
            }
        ],
        "notes": "",
    }
    with (
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=([], "no_index")),
        ),
        patch(
            "app.routers.quotes.generate_quote_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
    ):
        created = await admin_client.post(
            "/quotes/generate",
            json={
                "contact_id": contact_id,
                "description": "Install a security light",
                "use_ocerp": False,
            },
        )
    assert created.status_code == 201, created.text
    data: dict[str, Any] = created.json()
    return data


async def test_ai_insights_counts_ai_quotes_and_generation_time(
    admin_client: AsyncClient,
) -> None:
    contact = await _create_contact(admin_client, "AI Stats Customer")
    await _create_ai_quote(admin_client, contact["id"])

    response = await admin_client.get("/analytics/ai-insights")
    assert response.status_code == 200
    perf = response.json()["ai_quote_performance"]

    current_month = perf["monthly_data"][-1]
    assert current_month["ai_quotes"] == 1
    assert current_month["manual_quotes"] == 0

    # Mocked calls complete instantly, but the timing is still recorded.
    assert perf["average_generation_time"] is not None
    # No update/send happened yet, so no feedback has been recorded.
    assert perf["edit_rate"] is None
    assert perf["avg_price_drift_pct"] is None


async def test_ai_insights_reports_edit_feedback_after_update(admin_client: AsyncClient) -> None:
    contact = await _create_contact(admin_client, "AI Feedback Customer")
    quote = await _create_ai_quote(admin_client, contact["id"])

    # The electrician edits the draft: different price and an extra line.
    updated = await admin_client.patch(
        f"/quotes/{quote['id']}",
        json={
            "line_items": [
                {"description": "Labour", "quantity": "1", "unit_price": "360.00"},
                {"description": "Sundries", "quantity": "1", "unit_price": "40.00"},
            ]
        },
    )
    assert updated.status_code == 200, updated.text

    response = await admin_client.get("/analytics/ai-insights")
    assert response.status_code == 200
    perf = response.json()["ai_quote_performance"]

    assert perf["edit_rate"] == 1.0
    # AI draft total was 360.00; the edited quote totals 480.00 → +33.33%.
    assert perf["avg_price_drift_pct"] == 33.33


async def test_dashboard_kpis_include_ai_time_saved(admin_client: AsyncClient) -> None:
    """AI-drafted quotes roll up into the dashboard's time-saved KPI."""
    contact = await _create_contact(admin_client, "AI Time Saved Customer")
    await _create_ai_quote(admin_client, contact["id"])

    response = await admin_client.get("/analytics/dashboard")
    assert response.status_code == 200
    kpi = response.json()["kpi"]

    assert kpi["ai_generated_quotes"] == 1
    # 1 AI quote x 25 min manual drafting baseline = 0.4 hrs (rounded to 1dp).
    assert kpi["ai_time_saved_hours"] == 0.4


async def test_dashboard_kpis_ai_time_saved_defaults_zero(admin_client: AsyncClient) -> None:
    """Tenants with no AI quotes get zero-valued time-saved KPIs."""
    response = await admin_client.get("/analytics/dashboard")
    assert response.status_code == 200
    kpi = response.json()["kpi"]

    assert kpi["ai_generated_quotes"] == 0
    assert kpi["ai_time_saved_hours"] == 0.0


async def test_ai_insights_reports_ai_spend(admin_client: AsyncClient) -> None:
    """LLM token usage recorded on quotes rolls up into spend totals."""
    contact = await _create_contact(admin_client, "AI Spend Customer")

    generated = {
        "line_items": [
            {
                "description": "Security light installation (labour)",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 300.00,
            }
        ],
        "notes": "",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
    }
    with (
        patch(
            "app.routers.quotes.search_cost_items_with_status",
            new=AsyncMock(return_value=([], "no_index")),
        ),
        patch(
            "app.routers.quotes.generate_quote_from_prompt",
            new=AsyncMock(return_value=generated),
        ),
    ):
        created = await admin_client.post(
            "/quotes/generate",
            json={
                "contact_id": contact["id"],
                "description": "Install a security light",
                "use_ocerp": False,
            },
        )
    assert created.status_code == 201, created.text

    response = await admin_client.get("/analytics/ai-insights")
    assert response.status_code == 200
    perf = response.json()["ai_quote_performance"]

    assert perf["ai_quotes_with_usage"] == 1
    # The default test model is not in the pricing map → tokens recorded but
    # no cost estimate → total is null.
    assert perf["total_ai_cost_usd"] is None
