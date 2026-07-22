"""Tests for tenant settings endpoints."""

from uuid import uuid4

import pytest
from app.models import Tenant, User
from app.rls import set_tenant_in_session
from app.security import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_get_current_tenant(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/tenants/me")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == admin_client.headers["X-Tenant-ID"]
    assert "name" in data


async def test_patch_tenant_settings_requires_auth(client: AsyncClient) -> None:
    response = await client.patch("/tenants/me", json={"name": "Hacked"})
    assert response.status_code == 401


async def test_patch_tenant_name_and_settings(admin_client: AsyncClient) -> None:
    response = await admin_client.patch(
        "/tenants/me",
        json={
            "name": "Updated Electrical",
            "settings": {
                "hourly_labour_rate": "45.00",
                "daily_labour_rate": "360.00",
                "mate_daily_rate": "220.00",
                "mate_percent": "60",
                "markup_percentage": "20",
                "min_margin_percent": "15",
                "price_tolerance_percent": "10",
                "minimum_charge": "95",
                "vat_rate": "20",
                "branding": {"primary_color": "#000000"},
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Electrical"
    assert data["settings"]["hourly_labour_rate"] == "45.00"
    assert data["settings"]["daily_labour_rate"] == "360.00"
    assert data["settings"]["mate_daily_rate"] == "220.00"
    assert data["settings"]["mate_percent"] == "60"
    assert data["settings"]["min_margin_percent"] == "15"
    assert data["settings"]["price_tolerance_percent"] == "10"
    assert data["settings"]["minimum_charge"] == "95"
    assert data["settings"]["vat_rate"] == "20"
    assert data["settings"]["branding"]["primary_color"] == "#000000"
    assert data["hourlyLaborRate"] == pytest.approx(45.0)
    assert data["dailyLaborRate"] == pytest.approx(360.0)
    assert data["mateDailyRate"] == pytest.approx(220.0)
    assert data["matePercent"] == pytest.approx(60.0)
    assert data["primaryColor"] == "#000000"
    assert data["minMarginPercent"] == pytest.approx(15.0)
    assert data["priceTolerancePercent"] == pytest.approx(10.0)
    assert data["minimumCharge"] == pytest.approx(95.0)
    assert data["vatRate"] == pytest.approx(20.0)


async def test_patch_tenant_settings_user_must_belong_to_tenant(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    tenant_a = Tenant(slug=f"tenant-a-{uuid4().hex[:8]}", name="Tenant A")
    tenant_b = Tenant(slug=f"tenant-b-{uuid4().hex[:8]}", name="Tenant B")
    db.add_all([tenant_a, tenant_b])
    await db.flush()
    await set_tenant_in_session(db, tenant_b.id)

    password = "password-123"
    user_b = User(
        tenant_id=tenant_b.id,
        email="userb@test.local",
        full_name="User B",
        role="admin",
        password_hash=get_password_hash(password),
        is_active=True,
    )
    db.add(user_b)
    await db.commit()

    login = await client.post(
        "/auth/login",
        headers={"host": f"{tenant_b.slug}.localhost"},
        json={"email": user_b.email, "password": password},
    )
    assert login.status_code == 200

    response = await client.patch(
        "/tenants/me",
        headers={"X-Tenant-ID": str(tenant_a.id)},
        json={"name": "Should Fail"},
    )
    assert response.status_code == 403
