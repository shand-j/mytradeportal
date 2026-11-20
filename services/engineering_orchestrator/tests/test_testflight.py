from __future__ import annotations

from typing import TYPE_CHECKING

from engineering_orchestrator.testflight import AppStoreConnectClient
from fakes import make_settings

if TYPE_CHECKING:
    from pathlib import Path


def test_testflight_poller_normalizes_crash_and_feedback(tmp_path: Path, monkeypatch) -> None:
    client = AppStoreConnectClient(make_settings(tmp_path, appstore_app_id="app-1"))

    def submissions(path: str):
        if "Crash" in path:
            return [{"id": "crash-1", "attributes": {"comment": "It crashed"}}]
        return [{"id": "feedback-1", "attributes": {"comment": "Please improve search"}}]

    monkeypatch.setattr(client, "_paginate", submissions)
    monkeypatch.setattr(client, "_crash_log", lambda submission: "symbolicated stack")
    events = client.poll()
    assert len(events) == 2
    assert events[0].source.value == "testflight_crash"
    assert events[0].body == "It crashed\n\nsymbolicated stack"
    assert events[1].source.value == "testflight_feedback"
