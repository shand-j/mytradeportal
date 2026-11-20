from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

os.environ["CREWAI_STORAGE_DIR"] = str(Path(__file__).parent / ".crewai-test-storage")


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.chdir(tmp_path)
