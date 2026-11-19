"""reminder_loop tick-failure alerting tests.

Drives the real loop with ``REMINDER_TICK_SECONDS=0`` and a scripted
``run_reminder_tick`` so the outage/alert/reset cycle runs without a database
or any sleeping.
"""

import asyncio

import pytest
from app import alerting, scheduler


@pytest.mark.asyncio
async def test_reminder_loop_alerts_once_per_failure_streak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    alerts: list[str] = []

    async def _record_alert(subject: str, text: str) -> dict[str, bool]:
        alerts.append(subject)
        return {"slack": True}

    monkeypatch.setattr(alerting, "send_alert", _record_alert)
    monkeypatch.setattr(scheduler, "REMINDER_TICK_SECONDS", 0)

    threshold = scheduler._TICK_FAILURE_ALERT_THRESHOLD
    # fail x threshold (alert), fail again (no extra alert), succeed (reset),
    # fail x threshold (second alert), then stop.
    outcomes: list[bool] = [False] * (threshold + 1) + [True] + [False] * threshold
    ticks = 0

    async def _scripted_tick() -> dict[str, int]:
        nonlocal ticks
        ticks += 1
        if not outcomes:
            stop.set()
            return {}
        ok = outcomes.pop(0)
        if not outcomes:
            stop.set()
        if not ok:
            raise RuntimeError("database gone")
        return {}

    monkeypatch.setattr(scheduler, "run_reminder_tick", _scripted_tick)

    await scheduler.reminder_loop(stop)

    assert ticks >= threshold + 1
    assert len(alerts) == 2
    assert all("Reminder scheduler tick failing" in subject for subject in alerts)
