"""Knowledge retrieval router for the agentic quoting framework."""

from __future__ import annotations

from fastapi import APIRouter, status

from ocerp.services.knowledge_store import (
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    KnowledgeStore,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post(
    "/search",
    response_model=list[KnowledgeSearchResult],
    status_code=status.HTTP_200_OK,
    summary="Search quoting knowledge",
    description="Semantic search over the quoting knowledge base with optional filters.",
)
async def search_knowledge(request: KnowledgeSearchRequest) -> list[KnowledgeSearchResult]:
    """Search the quoting knowledge base."""
    store = KnowledgeStore()
    return await store.search(request)
