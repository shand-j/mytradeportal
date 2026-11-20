from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crewai import LLM

from .github import GitHubClient
from .release import ReleaseService
from .sandbox import DryRunWorker, RailwaySandboxWorker, Worker
from .store import RunStore

if TYPE_CHECKING:
    from .config import Settings
    from .domain import EngineeringRun


class Runtime:
    def __init__(
        self,
        settings: Settings,
        store: RunStore | None = None,
        worker: Worker | None = None,
        github: Any | None = None,
        releases: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or RunStore(settings.database_url)
        self.github = github
        if self.github is None and settings.mode == "live":
            self.github = GitHubClient(settings)
        self.worker = worker or (
            RailwaySandboxWorker(settings) if settings.mode == "live" else DryRunWorker()
        )
        self.releases: Any = releases
        if self.releases is None and self.github is not None:
            self.releases = ReleaseService(settings, self.github)
        self._llm = llm

    def llm(self) -> LLM:
        if self._llm is None:
            self._llm = LLM(
                model=self.settings.model,
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._llm

    def save(self, run: EngineeringRun) -> None:
        self.store.save(run)

    def close(self) -> None:
        if self.github is not None and hasattr(self.github, "close"):
            self.github.close()
        self.store.close()
