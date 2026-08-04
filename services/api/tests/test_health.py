"""Tests for /health and /health/ready endpoints."""

from decimal import Decimal

import pytest
from app.config import settings as api_settings
from app.main import app
from app.models import CostItem
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_health_liveness_is_always_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_reports_ready_when_gate_disabled(client: AsyncClient) -> None:
    """With the default MIN_ACTIVE_COST_ITEMS=0 the gate reports ready."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["min_active_cost_items"] == 0
    assert payload["active_cost_items"] >= 0


@pytest.mark.asyncio
async def test_readiness_returns_503_when_catalogue_below_threshold(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_settings, "min_active_cost_items", 5)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "not_ready"
    assert detail["reason"] == "catalogue_below_minimum"
    assert detail["min_active_cost_items"] == 5


@pytest.mark.asyncio
async def test_readiness_excludes_dom_seed_rows(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOM-SEED-* legacy rows must not count toward the readiness threshold."""
    # Seed rows should be excluded regardless of is_active.
    db.add(
        CostItem(
            code="DOM-SEED-TEST-1",
            trade="electrical",
            region="UK",
            category="Test",
            description="Legacy seed row",
            unit="each",
            unit_price=Decimal("1.00"),
            currency="GBP",
            is_active=True,
            source="domestic_pipeline",
            extra_data={"supplier": "seed"},
        )
    )
    # A real catalogue row from the pipeline should count.
    db.add(
        CostItem(
            code="DOM-screwfix-123",
            trade="electrical",
            region="UK",
            category="Cable",
            description="2.5mm T&E cable",
            unit="m",
            unit_price=Decimal("0.72"),
            currency="GBP",
            is_active=True,
            source="domestic_pipeline",
            extra_data={"supplier": "Screwfix"},
        )
    )
    await db.commit()

    # Threshold of 1 must be met by the single real row (seed row excluded).
    monkeypatch.setattr(api_settings, "min_active_cost_items", 1)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["active_cost_items"] == 1

    # Threshold of 2 must fail because only one non-seed row exists.
    monkeypatch.setattr(api_settings, "min_active_cost_items", 2)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["active_cost_items"] == 1
