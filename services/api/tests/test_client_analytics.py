"""Integration tests for authenticated client product analytics ingestion."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from app.models import Customer, Event, Tenant
from app.security import create_access_token
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


def _batch(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "category": "screen_view",
        "name": "dashboard",
        "occurred_at": f"{datetime.utcnow().isoformat()}Z",
        "session_id": str(uuid4()),
        "properties": {
            "route": "/quotes/123?token=do-not-store",
            "platform": "ios",
            "app_version": "1.0.0",
        },
    }
    event.update(overrides)
    return {"events": [event]}


async def test_staff_client_events_are_stored_with_redacted_routes(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    response = await admin_client.post("/analytics/events", json=_batch())

    assert response.status_code == 202
    assert response.json() == {"accepted": 1}
    event = (
        await db.execute(select(Event).where(Event.event_type == "analytics.screen_view"))
    ).scalar_one()
    assert event.actor_type == "user"
    assert event.payload["name"] == "dashboard"
    assert event.payload["route"] == "/quotes/:id"
    assert "token" not in event.payload["route"]
    assert event.payload["client"] is True


async def test_customer_client_events_keep_customer_attribution(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    tenant = (await db.execute(select(Tenant))).scalars().one()
    customer = Customer(
        tenant_id=tenant.id,
        email="homeowner@example.com",
        full_name="Test Homeowner",
        is_active=True,
    )
    db.add(customer)
    await db.commit()
    token = create_access_token(
        customer.id,
        tenant.id,
        role="customer",
        email=customer.email,
        subject_type="customer",
    )
    admin_client.cookies.clear()
    admin_client.headers["Authorization"] = f"Bearer {token}"

    response = await admin_client.post(
        "/analytics/events",
        json=_batch(
            category="action", name="quote_request_submit", properties={"source": "portal"}
        ),
    )

    assert response.status_code == 202
    event = (
        await db.execute(select(Event).where(Event.event_type == "analytics.action"))
    ).scalar_one()
    assert event.actor_type == "customer"
    assert event.actor_id == customer.id


async def test_client_events_require_authentication(admin_client: AsyncClient) -> None:
    admin_client.cookies.clear()
    admin_client.headers.pop("Authorization", None)

    response = await admin_client.post("/analytics/events", json=_batch())

    assert response.status_code == 401


async def test_client_events_reject_unapproved_payload_keys(
    admin_client: AsyncClient, db: AsyncSession
) -> None:
    response = await admin_client.post(
        "/analytics/events",
        json=_batch(properties={"email": "person@example.com"}),
    )

    assert response.status_code == 422
    assert "Unsupported analytics properties" in response.json()["detail"]
    assert (
        await db.execute(select(Event).where(Event.event_type == "analytics.screen_view"))
    ).scalar_one_or_none() is None


async def test_client_events_reject_future_timestamps(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/analytics/events",
        json=_batch(occurred_at=f"{(datetime.utcnow() + timedelta(hours=1)).isoformat()}Z"),
    )

    assert response.status_code == 422
    assert "too far in the future" in response.json()["detail"]


async def test_client_events_reject_old_timestamps(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/analytics/events",
        json=_batch(occurred_at=f"{(datetime.utcnow() - timedelta(days=31)).isoformat()}Z"),
    )

    assert response.status_code == 422
    assert "older than 30 days" in response.json()["detail"]


async def test_client_events_validate_numeric_properties(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/analytics/events",
        json=_batch(
            category="performance",
            name="api_request",
            properties={"duration_ms": "slow", "path": "/quotes"},
        ),
    )

    assert response.status_code == 422
    assert "duration_ms must be numeric" in response.json()["detail"]
