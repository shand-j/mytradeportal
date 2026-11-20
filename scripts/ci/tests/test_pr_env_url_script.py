from __future__ import annotations

import json
import os
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

SCRIPT = Path(__file__).resolve().parents[1] / "pr_env_url.sh"


class _GraphqlHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        query = payload.get("query", "")

        if "project(id: $id)" in query:
            body = {
                "data": {
                    "project": {
                        "environments": {
                            "edges": [{"node": n} for n in self.server.env_nodes]  # type: ignore[attr-defined]
                        }
                    }
                }
            }
        else:
            body = {
                "data": {
                    "environment": {
                        "serviceInstances": {"edges": []},
                    }
                }
            }

        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _fake_railway(env_nodes: list[dict[str, object]]) -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _GraphqlHandler)
    server.env_nodes = env_nodes  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _run_script(api_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "RAILWAY_TOKEN": "test-token",
            "RAILWAY_PROJECT_ID": "project-123",
            "RAILWAY_API_URL": api_url,
        }
    )
    return subprocess.run(
        [str(SCRIPT), "357"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_fails_fast_when_only_production_is_visible() -> None:
    with _fake_railway(
        [{"id": "env-prod", "name": "production", "isEphemeral": False, "meta": {}}]
    ) as api_url:
        result = _run_script(api_url)

    assert result.returncode == 5
    assert "authorization failure discovering PR environments" in result.stderr
    assert "RAILWAY_TOKEN_PR_VERIFY" in result.stderr
    assert "read access to all project environments" in result.stderr


def test_keeps_retryable_exit_when_non_production_envs_are_visible() -> None:
    with _fake_railway(
        [
            {"id": "env-prod", "name": "production", "isEphemeral": False, "meta": {}},
            {"id": "env-staging", "name": "staging", "isEphemeral": False, "meta": {}},
        ]
    ) as api_url:
        result = _run_script(api_url)

    assert result.returncode == 3
    assert "no ephemeral PR environment found for PR #357" in result.stderr
