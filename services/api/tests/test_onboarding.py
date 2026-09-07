"""Tests for the progressive business-onboarding endpoints."""

from httpx import AsyncClient

_LAUNCH_GATE_STEPS = ["business_identity", "compliance", "services"]


async def _complete_step(client: AsyncClient, step: str, value: dict[str, object]) -> None:
    response = await client.patch(
        f"/onboarding/step/{step}",
        json={"step": step, "value": value},
    )
    assert response.status_code == 200, response.text


async def test_multiple_steps_persist_across_requests(admin_client: AsyncClient) -> None:
    """Each launch-gate step, sent in a separate request, must persist.

    Regression: the endpoint mutated the JSONB ``onboarding_progress`` dict in
    place and reassigned the same reference, so SQLAlchemy did not detect the
    change and every step after the first was silently dropped.
    """
    await _complete_step(admin_client, "business_identity", {"trading_name": "Acme"})
    await _complete_step(admin_client, "compliance", {"scheme": "napit"})
    await _complete_step(admin_client, "services", {"services": ["ev_charger"]})

    status = await admin_client.get("/onboarding/status")
    assert status.status_code == 200
    body = status.json()

    progress = body["onboarding_progress"]
    for step in _LAUNCH_GATE_STEPS:
        assert step in progress, f"{step} was not persisted"
        assert progress[step]["completed"] is True

    assert body["pending_steps"] == []


async def test_launch_succeeds_after_all_steps(admin_client: AsyncClient) -> None:
    for step in _LAUNCH_GATE_STEPS:
        await _complete_step(admin_client, step, {})

    launch = await admin_client.post("/onboarding/launch")
    assert launch.status_code == 200
    assert launch.json()["status"] == "active"


async def test_launch_blocked_when_steps_pending(admin_client: AsyncClient) -> None:
    await _complete_step(admin_client, "business_identity", {})

    launch = await admin_client.post("/onboarding/launch")
    assert launch.status_code == 400
    assert "pending" in launch.json()["detail"].lower()


async def test_onboarding_metrics_persist_to_tenant_settings(
    admin_client: AsyncClient,
) -> None:
    """quotes_per_week / avg_minutes_per_quote from an onboarding step land in
    tenant.settings (verbatim, no server-side computation)."""
    await _complete_step(
        admin_client,
        "business_identity",
        {"trading_name": "Acme", "quotes_per_week": 12, "avg_minutes_per_quote": 45},
    )

    tenant = await admin_client.get("/tenants/me")
    assert tenant.status_code == 200
    settings = tenant.json()["settings"]
    assert settings["quotes_per_week"] == 12
    assert settings["avg_minutes_per_quote"] == 45


async def test_onboarding_metrics_via_tenant_update(admin_client: AsyncClient) -> None:
    """The same fields are accepted by PATCH /tenants/me (camelCase aliases)."""
    response = await admin_client.patch(
        "/tenants/me", json={"quotesPerWeek": 8, "avgMinutesPerQuote": 30}
    )
    assert response.status_code == 200, response.text

    tenant = await admin_client.get("/tenants/me")
    settings = tenant.json()["settings"]
    assert settings["quotes_per_week"] == 8
    assert settings["avg_minutes_per_quote"] == 30


async def test_brand_colours_persist_via_tenant_update(admin_client: AsyncClient) -> None:
    """primary_color / secondary_color persist through the settings path."""
    response = await admin_client.patch(
        "/tenants/me", json={"primaryColor": "#112233", "secondaryColor": "#445566"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["primaryColor"] == "#112233"
    assert body["secondaryColor"] == "#445566"

    tenant = await admin_client.get("/tenants/me")
    settings = tenant.json()["settings"]
    assert settings["primary_color"] == "#112233"
    assert settings["secondary_color"] == "#445566"
