from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, String, UniqueConstraint, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from .domain import TERMINAL_STATUSES, EngineeringRun, RunStatus

if TYPE_CHECKING:
    from collections.abc import Iterable


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    __tablename__ = "engineering_runs"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[str] = mapped_column(String(500), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    run_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RunStore:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def create(self, run: EngineeringRun) -> tuple[EngineeringRun, bool]:
        record = self._record(run)
        try:
            with Session(self.engine) as session:
                session.add(record)
                session.commit()
            return run, True
        except IntegrityError:
            existing = self.get_by_external(run.event.source.value, run.event.external_id)
            if existing is None:
                raise
            return existing, False

    def save(self, run: EngineeringRun) -> None:
        run.updated_at = datetime.now(UTC)
        with Session(self.engine) as session:
            record = session.get(RunRecord, run.id)
            if record is None:
                record = self._record(run)
                session.add(record)
            else:
                self._update_record(record, run)
            session.commit()

    def get(self, run_id: str) -> EngineeringRun | None:
        with Session(self.engine) as session:
            record = session.get(RunRecord, run_id)
            return self._run(record) if record is not None else None

    def get_by_external(self, source: str, external_id: str) -> EngineeringRun | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(RunRecord).where(
                    RunRecord.source == source, RunRecord.external_id == external_id
                )
            )
            return self._run(record) if record is not None else None

    def list_recent(self, limit: int = 100) -> list[EngineeringRun]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(RunRecord).order_by(RunRecord.created_at.desc()).limit(limit)
            ).all()
            return [self._run(record) for record in records]

    def requeue_incomplete(self) -> list[EngineeringRun]:
        requeued: list[EngineeringRun] = []
        for run in self.list_recent(1000):
            if run.status not in TERMINAL_STATUSES:
                run.mark(RunStatus.QUEUED)
                self.save(run)
                requeued.append(run)
        return requeued

    def add_many(self, runs: Iterable[EngineeringRun]) -> None:
        for run in runs:
            self.save(run)

    @staticmethod
    def _run(record: RunRecord) -> EngineeringRun:
        return EngineeringRun.model_validate(record.run_data)

    @staticmethod
    def _record(run: EngineeringRun) -> RunRecord:
        return RunRecord(
            id=run.id,
            source=run.event.source.value,
            external_id=run.event.external_id,
            status=run.status.value,
            run_data=run.model_dump(mode="json"),
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    @staticmethod
    def _update_record(record: RunRecord, run: EngineeringRun) -> None:
        record.status = run.status.value
        record.run_data = run.model_dump(mode="json")
        record.updated_at = run.updated_at
