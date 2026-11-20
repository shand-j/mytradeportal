from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .config import Settings
from .events import (
    normalize_github_issue,
    normalize_production_alert,
    normalize_testflight_submission,
)
from .orchestrator import Orchestrator
from .runtime import Runtime
from .security import github_signature_valid, signed_payload_valid, token_valid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, orchestrator: Orchestrator | None = None
) -> FastAPI:
    config = settings or Settings()
    coordinator = orchestrator or Orchestrator(Runtime(config))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await coordinator.start()
        try:
            yield
        finally:
            await coordinator.stop()

    app = FastAPI(title="MyTradePortal Engineering Orchestrator", lifespan=lifespan)
    app.state.orchestrator = coordinator

    def authorize(x_engineering_token: str = Header(default="")) -> None:
        if not token_valid(config.api_auth_token.get_secret_value(), x_engineering_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "config": config.public_config()}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        coordinator.runtime.store.ping()
        return {"status": "ready"}

    @app.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        x_hub_signature_256: str = Header(default=""),
    ) -> JSONResponse:
        body = await request.body()
        if not github_signature_valid(
            config.github_webhook_secret.get_secret_value(), body, x_hub_signature_256
        ):
            raise HTTPException(status_code=401, detail="Invalid GitHub signature")
        payload = await request.json()
        event = normalize_github_issue(payload)
        if event is None:
            return JSONResponse({"status": "ignored"}, status_code=202)
        if event.repository != config.repository:
            raise HTTPException(status_code=403, detail="Repository is not configured")
        return await _submit(coordinator, event)

    @app.post("/webhooks/alerts")
    async def alert_webhook(
        request: Request,
        x_engineering_signature: str = Header(default=""),
        x_engineering_timestamp: str = Header(default=""),
    ) -> JSONResponse:
        body = await request.body()
        if not signed_payload_valid(
            config.alert_webhook_secret.get_secret_value(),
            body,
            x_engineering_signature,
            x_engineering_timestamp,
        ):
            raise HTTPException(status_code=401, detail="Invalid or stale alert signature")
        event = normalize_production_alert(await request.json())
        if event is None:
            return JSONResponse({"status": "ignored"}, status_code=202)
        if event.repository != config.repository:
            raise HTTPException(status_code=403, detail="Repository is not configured")
        return await _submit(coordinator, event)

    @app.post("/webhooks/testflight")
    async def testflight_relay_webhook(
        request: Request,
        x_engineering_signature: str = Header(default=""),
        x_engineering_timestamp: str = Header(default=""),
    ) -> JSONResponse:
        body = await request.body()
        if not signed_payload_valid(
            config.testflight_webhook_secret.get_secret_value(),
            body,
            x_engineering_signature,
            x_engineering_timestamp,
        ):
            raise HTTPException(status_code=401, detail="Invalid or stale TestFlight signature")
        event = normalize_testflight_submission(await request.json(), config.repository)
        return await _submit(coordinator, event)

    @app.get("/runs", dependencies=[Depends(authorize)])
    def list_runs(limit: int = 100) -> list[dict[str, Any]]:
        return [
            run.model_dump(mode="json")
            for run in coordinator.runtime.store.list_recent(min(limit, 200))
        ]

    @app.get("/runs/{run_id}", dependencies=[Depends(authorize)])
    def get_run(run_id: str) -> dict[str, Any]:
        run = coordinator.runtime.store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404)
        return run.model_dump(mode="json")

    @app.post("/runs/{run_id}/retry", dependencies=[Depends(authorize)])
    async def retry_run(run_id: str) -> dict[str, Any]:
        run = await coordinator.retry(run_id)
        if run is None:
            raise HTTPException(status_code=404)
        return run.model_dump(mode="json")

    @app.post("/internal/testflight/poll", dependencies=[Depends(authorize)])
    async def poll_testflight() -> list[dict[str, Any]]:
        runs = await coordinator.poll_testflight()
        return [run.model_dump(mode="json") for run in runs]

    return app


async def _submit(coordinator: Orchestrator, event: Any) -> JSONResponse:
    run, created = await coordinator.submit(event)
    return JSONResponse(
        {"run_id": run.id, "status": run.status.value, "created": created},
        status_code=202 if created else 200,
    )
