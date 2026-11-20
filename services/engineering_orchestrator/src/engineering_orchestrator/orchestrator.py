from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .domain import EngineeringEvent, EngineeringRun, EventSource, RunStatus
from .flow import EngineeringFlow
from .testflight import AppStoreConnectClient

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .runtime import Runtime

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.tasks: list[asyncio.Task[None]] = []
        self.testflight: AppStoreConnectClient | None = None

    async def start(self) -> None:
        for run in self.runtime.store.requeue_incomplete():
            self.queue.put_nowait(run.id)
        self.tasks = [
            asyncio.create_task(self._worker_loop(index))
            for index in range(self.runtime.settings.worker_count)
        ]
        if self.runtime.settings.testflight_enabled and self.runtime.settings.mode == "live":
            self.testflight = AppStoreConnectClient(self.runtime.settings)
            self.tasks.append(asyncio.create_task(self._testflight_loop()))

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        if self.testflight is not None:
            self.testflight.close()
        self.runtime.close()

    async def submit(self, event: EngineeringEvent) -> tuple[EngineeringRun, bool]:
        existing = self.runtime.store.get_by_external(event.source.value, event.external_id)
        if existing is not None:
            return existing, False
        run, created = await asyncio.to_thread(
            self.runtime.store.create, EngineeringRun.from_event(event)
        )
        if not created:
            return run, False
        if (
            event.source in {EventSource.TESTFLIGHT_CRASH, EventSource.TESTFLIGHT_FEEDBACK}
            and self.runtime.settings.mode == "live"
            and self.runtime.github is not None
        ):
            try:
                issue = await asyncio.to_thread(
                    self.runtime.github.create_issue,
                    event.title,
                    event.body,
                    [
                        "agent:ready",
                        "testflight",
                        "bug" if event.source == EventSource.TESTFLIGHT_CRASH else "feedback",
                    ],
                )
            except Exception as exc:
                run.error = f"Could not create the TestFlight GitHub issue: {exc}"
                run.mark(RunStatus.FAILED)
                self.runtime.store.save(run)
                return run, True
            run.event.issue_number = int(issue["number"])
            run.event.metadata["url"] = issue["html_url"]
            self.runtime.store.save(run)
        self.queue.put_nowait(run.id)
        return run, True

    async def retry(self, run_id: str) -> EngineeringRun | None:
        run = self.runtime.store.get(run_id)
        if run is None:
            return None
        if not run.terminal:
            return run
        run.error = ""
        run.release = None
        run.mark(RunStatus.QUEUED)
        self.runtime.store.save(run)
        self.queue.put_nowait(run.id)
        return run

    async def poll_testflight(self) -> Sequence[EngineeringRun]:
        if self.testflight is None:
            self.testflight = AppStoreConnectClient(self.runtime.settings)
        events = await asyncio.to_thread(self.testflight.poll)
        runs: list[EngineeringRun] = []
        for event in events:
            run, _ = await self.submit(event)
            runs.append(run)
        return runs

    async def _worker_loop(self, index: int) -> None:
        while True:
            run_id = await self.queue.get()
            try:
                run = self.runtime.store.get(run_id)
                if run is None or run.terminal:
                    continue
                flow = EngineeringFlow(runtime=self.runtime)
                await asyncio.to_thread(flow.kickoff, inputs={"run_id": run_id})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Engineering worker %s failed run %s", index, run_id)
                run = self.runtime.store.get(run_id)
                if run is not None:
                    run.error = str(exc)[:12000]
                    run.mark(RunStatus.FAILED)
                    self.runtime.store.save(run)
            finally:
                self.queue.task_done()

    async def _testflight_loop(self) -> None:
        while True:
            try:
                await self.poll_testflight()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("TestFlight polling failed")
            await asyncio.sleep(self.runtime.settings.testflight_poll_seconds)
