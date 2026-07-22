"""Tests for analytics dashboard endpoints."""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_contact(client: AsyncClient, name: str) -> dict[str, Any]:
    response = await client.post(
        "/contacts",
        json={"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"},
    )
    assert response.status_code == 201
    return response.json()


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
    return response.json()


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
    return response.json()


async def test_dashboard_returns_expected_structure(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "kpi" in data
    assert "revenue_chart" in data
    assert "service_breakdown" in data
    assert "recent_activity" in data
    assert "voice_stats" in data


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
    assert Decimal(str(data["kpi"]["revenue_this_month"])) == Decimal("480.00")


async def test_ai_insights_returns_expected_structure(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/analytics/ai-insights")
    assert response.status_code == 200
    data = response.json()
    assert "ai_quote_performance" in data
    assert "demand_forecast" in data
    assert "voice_analytics" in data
    assert "predictions" in data["demand_forecast"]
    assert "insight" in data["demand_forecast"]
