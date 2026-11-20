from pathlib import Path

from engineering_orchestrator.domain import EngineeringRun, RunStatus
from engineering_orchestrator.store import RunStore
from fakes import github_event


def test_store_is_idempotent_and_recovers_incomplete_runs(tmp_path: Path) -> None:
    store = RunStore(f"sqlite:///{tmp_path}/runs.db")
    run = EngineeringRun.from_event(github_event())
    created, first = store.create(run)
    duplicate, second = store.create(EngineeringRun.from_event(github_event()))
    assert first is True
    assert second is False
    assert created.id == duplicate.id

    run.mark(RunStatus.IMPLEMENTING)
    store.save(run)
    requeued = store.requeue_incomplete()
    assert [item.id for item in requeued] == [run.id]
    assert store.get(run.id).status == RunStatus.QUEUED

    run.mark(RunStatus.AWAITING_REVIEW)
    store.save(run)
    assert store.requeue_incomplete() == []
    assert store.ping()
    store.close()
