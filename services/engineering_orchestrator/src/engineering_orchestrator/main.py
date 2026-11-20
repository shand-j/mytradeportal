#!/usr/bin/env python
from __future__ import annotations

import asyncio
import json
import sys

from .config import Settings
from .domain import EngineeringEvent, EventSource
from .orchestrator import Orchestrator
from .runtime import Runtime


async def run_event(event: EngineeringEvent) -> None:
    orchestrator = Orchestrator(Runtime(Settings()))
    await orchestrator.start()
    try:
        run, _ = await orchestrator.submit(event)
        await orchestrator.queue.join()
        completed = orchestrator.runtime.store.get(run.id)
        if completed is not None:
            print(completed.model_dump_json(indent=2))
    finally:
        await orchestrator.stop()


def kickoff() -> None:
    if len(sys.argv) > 1:
        event = EngineeringEvent.model_validate(json.loads(sys.argv[1]))
    else:
        event = EngineeringEvent(
            source=EventSource.GITHUB_ISSUE,
            external_id="local:dry-run",
            repository="shand-j/mytradeportal",
            title="Local orchestrator dry run",
            body="No repository or external system is changed in dry-run mode.",
        )
    asyncio.run(run_event(event))


def run_with_trigger() -> None:
    kickoff()


def plot() -> None:
    from .flow import EngineeringFlow

    settings = Settings()
    runtime = Runtime(settings)
    EngineeringFlow(runtime=runtime).plot("engineering_flow.html", show=False)
    runtime.close()


if __name__ == "__main__":
    kickoff()
