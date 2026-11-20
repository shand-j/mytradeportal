from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from engineering_orchestrator.api import create_app
from engineering_orchestrator.domain import RunStatus
from engineering_orchestrator.orchestrator import Orchestrator
from fakes import FakeWorker, make_runtime
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from pathlib import Path


def test_signed_github_webhook_end_to_end_and_deduplicated(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, worker=FakeWorker(dry_run=True))
    coordinator = Orchestrator(runtime)
    app = create_app(runtime.settings, coordinator)
    payload = {
        "action": "opened",
        "issue": {
            "number": 9,
            "title": "Webhook regression",
            "body": "Reproduce it",
            "labels": [{"name": "agent:ready"}, {"name": "bug"}],
        },
        "repository": {"full_name": "owner/repo"},
    }
    body = json.dumps(payload).encode()
    digest = hmac.new(b"github-secret", body, hashlib.sha256).hexdigest()
    headers = {"X-Hub-Signature-256": f"sha256={digest}"}
    with TestClient(app) as client:
        response = client.post("/webhooks/github", content=body, headers=headers)
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        for _ in range(100):
            run = runtime.store.get(run_id)
            if run and run.status == RunStatus.COMPLETED:
                break
            time.sleep(0.01)
        assert run is not None and run.status == RunStatus.COMPLETED

        duplicate = client.post("/webhooks/github", content=body, headers=headers)
        assert duplicate.status_code == 200
        assert duplicate.json()["run_id"] == run_id
        assert client.get(f"/runs/{run_id}").status_code == 401
        authorized = client.get(
            f"/runs/{run_id}", headers={"X-Engineering-Token": "operator-token"}
        )
        assert authorized.status_code == 200
        assert authorized.json()["id"] == run_id
        assert client.get("/ready").status_code == 200


def test_invalid_signature_is_rejected_before_ingestion(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, worker=FakeWorker(dry_run=True))
    app = create_app(runtime.settings, Orchestrator(runtime))
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github", content=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"}
        )
        assert response.status_code == 401
        assert runtime.store.list_recent() == []


def test_signed_alert_enters_dry_run_without_hotfix(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, worker=FakeWorker(dry_run=True))
    app = create_app(runtime.settings, Orchestrator(runtime))
    payload = {
        "alert_id": "alert-9",
        "repository": "owner/repo",
        "title": "API unavailable",
        "status": "firing",
        "severity": "critical",
        "service": "api",
        "deployed_sha": "a" * 40,
        "rollback_sha": "c" * 40,
    }
    body = json.dumps(payload).encode()
    timestamp = datetime.now(UTC).isoformat()
    signature = hmac.new(
        b"alert-secret", f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/alerts",
            content=body,
            headers={
                "X-Engineering-Timestamp": timestamp,
                "X-Engineering-Signature": signature,
            },
        )
        assert response.status_code == 202
        run = runtime.store.get(response.json()["run_id"])
        assert run is not None
        assert run.event.is_incident
