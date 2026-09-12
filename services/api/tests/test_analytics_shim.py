"""Unit tests for the product analytics shim (``app.analytics``)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import app.analytics as analytics
import pytest
from app.analytics import track
from app.config import settings
from app.models import Event, Tenant
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_track_writes_event_row_with_analytics_prefix(
    client: AsyncClient, db: AsyncSession
) -> None:
    tenant = Tenant(slug=f"test-{uuid4().hex[:8]}", name="Analytics Tenant")
    db.add(tenant)
    await db.flush()

    user_id = uuid4()
    await track(
        "first_quote_sent",
        tenant_id=tenant.id,
        user_id=user_id,
        db=db,
        plan="pro",
        quote_id=str(uuid4()),
    )

    rows = (
        (await db.execute(select(Event).where(Event.event_type == "analytics.first_quote_sent")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.tenant_id == tenant.id
    assert row.actor_type == "user"
    assert row.actor_id == user_id
    assert row.entity_type == "tenant"
    assert row.entity_id == tenant.id
    assert row.payload["plan"] == "pro"
    assert "quote_id" in row.payload


async def test_track_without_user_is_system_actor(client: AsyncClient, db: AsyncSession) -> None:
    tenant = Tenant(slug=f"test-{uuid4().hex[:8]}", name="System Actor Tenant")
    db.add(tenant)
    await db.flush()

    await track("tenant_signup", tenant_id=tenant.id, db=db)

    row = (
        (await db.execute(select(Event).where(Event.event_type == "analytics.tenant_signup")))
        .scalars()
        .one()
    )
    assert row.actor_type == "system"
    assert row.actor_id is None


async def test_track_is_fail_open_on_db_error() -> None:
    """A failing session must never propagate — analytics is best-effort."""
    broken = AsyncMock(spec=AsyncSession)
    broken.execute.side_effect = RuntimeError("db is down")

    # Must not raise.
    await track("first_ai_draft", tenant_id=uuid4(), db=broken)


async def test_track_without_tenant_skips_db_write() -> None:
    """The events table is tenant-scoped; untenanted events are DB-skipped."""
    # No tenant_id, no db session — must complete without touching the DB.
    await track("demo_quote_generated", source="landing")


async def test_posthog_disabled_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analytics, "_posthog_client", None)
    monkeypatch.setattr(settings, "posthog_api_key", "")
    assert analytics._get_posthog_client() is None


async def test_posthog_passthrough_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a key set and the (optional) library present, events are mirrored."""
    capture = MagicMock()
    fake_client = MagicMock()
    fake_client.capture = capture
    fake_module = MagicMock()
    fake_module.Posthog = MagicMock(return_value=fake_client)

    monkeypatch.setattr(analytics, "_posthog", fake_module)
    monkeypatch.setattr(analytics, "_posthog_client", None)
    monkeypatch.setattr(settings, "posthog_api_key", "phc_test")
    monkeypatch.setattr(settings, "posthog_host", "https://eu.i.posthog.com")

    tenant_id = uuid4()
    user_id = uuid4()
    # tenant_id=None path: no DB write attempted, PostHog still receives it.
    await track("tenant_signup", user_id=user_id, plan="pro")

    fake_module.Posthog.assert_called_once_with("phc_test", host="https://eu.i.posthog.com")
    capture.assert_called_once()
    kwargs = capture.call_args.kwargs
    assert kwargs["distinct_id"] == str(user_id)
    assert kwargs["event"] == "tenant_signup"
    assert kwargs["properties"]["plan"] == "pro"

    # tenant_id set: properties carry it.
    capture.reset_mock()
    await track("first_ai_draft", tenant_id=tenant_id, db=AsyncMock(spec=AsyncSession))
    kwargs = capture.call_args.kwargs
    assert kwargs["distinct_id"] == str(tenant_id)
    assert kwargs["properties"]["tenant_id"] == str(tenant_id)
