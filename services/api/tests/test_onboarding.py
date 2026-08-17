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
