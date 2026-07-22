"""Bill of Quantities generation engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ocerp.services.agent_graph import run_quote_graph

if TYPE_CHECKING:
    from mtp_shared import BoQGenerateRequest, BoQGenerateResponse

    from ocerp.services.knowledge_store import KnowledgeStore


class BoQBackend:
    """Abstract backend for BoQ generation."""

    async def generate(self, request: BoQGenerateRequest) -> BoQGenerateResponse:
        raise NotImplementedError


class DdcLlmBackend(BoQBackend):
    """Generate a BoQ using the code-first agent graph.

    The graph retrieves cost items, calls an LLM to produce generic
    requirements, applies deterministic scope/labour/pricing rules, resolves
    SKUs, and validates the output.  See ``agent_graph.py`` for the node-level
    implementation.
    """

    def __init__(self, knowledge_store: KnowledgeStore | None = None) -> None:
        # Allow tests to inject a fake KnowledgeStore without standing up Qdrant.
        self._knowledge_store = knowledge_store

    async def generate(self, request: BoQGenerateRequest) -> BoQGenerateResponse:
        return await run_quote_graph(request, knowledge_store=self._knowledge_store)


def get_backend(name: str) -> BoQBackend:
    """Return a BoQ backend by name."""
    if name == "ddc_llm":
        return DdcLlmBackend()
    raise ValueError(f"Unknown backend: {name}")
