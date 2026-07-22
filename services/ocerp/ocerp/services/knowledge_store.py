"""Knowledge retrieval helper for the agentic quoting framework.

Provides semantic search over the `quoting_knowledge` Qdrant collection loaded by
`services/data-pipeline/src/data_pipeline/knowledge_loader.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from litellm import aembedding
from pydantic import BaseModel, Field
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

from ocerp.config import settings
from ocerp.qdrant import get_qdrant_client


class KnowledgeSearchRequest(BaseModel):
    """Request body for knowledge search."""

    query: str
    job_type: str | None = Field(default=None, description="Filter by job-type tag")
    rule_tier: str | None = Field(
        default=None,
        description="Filter by rule tier: mandatory, default, suggestion, reference",
    )
    doc_type: str | None = Field(default=None, description="Filter by document type")
    limit: int = Field(default=5, ge=1, le=50)


class KnowledgeSearchResult(BaseModel):
    """A single knowledge search result."""

    id: str
    score: float
    text: str
    source: str
    section_path: list[str]
    rule_tier: str
    job_types: list[str]
    doc_type: str


class KnowledgeStore:
    """Store and retrieve quoting knowledge from Qdrant."""

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        self.client = client or get_qdrant_client()
        self.collection_name = settings.qdrant_knowledge_collection_name
        self._vector_size: int | None = None

    @staticmethod
    def _is_ollama_model(model: str) -> bool:
        return model.startswith("ollama/")

    @classmethod
    def _embedding_kwargs(cls, texts: list[str]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": settings.embedding_model,
            "input": texts,
        }
        if cls._is_ollama_model(settings.embedding_model):
            kwargs["api_base"] = settings.ollama_api_base
        elif settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key
        return kwargs

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for the supplied texts."""
        if not texts:
            return []
        response = await aembedding(**self._embedding_kwargs(texts))
        return [item.get("embedding") for item in response.data]

    async def embed_text(self, text: str) -> list[float]:
        """Return a single embedding vector."""
        return (await self.embed_texts([text]))[0]

    def _get_embedding_dimension(self) -> int:
        """Return vector dimension for the configured embedding model."""
        if settings.embedding_dimensions:
            return settings.embedding_dimensions
        known_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "ollama/nomic-embed-text": 768,
            "nomic-embed-text": 768,
        }
        return known_dimensions.get(settings.embedding_model, 1536)

    async def ensure_collection(self) -> None:
        """Create the knowledge collection if it does not exist."""
        vector_size = self._get_embedding_dimension()
        exists = await self.client.collection_exists(self.collection_name)
        if exists:
            info = await self.client.get_collection(self.collection_name)
            current_size = info.config.params.vectors.size  # type: ignore[union-attr]
            if current_size != vector_size:
                await self.client.delete_collection(self.collection_name)
                exists = False

        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def _build_filter(self, request: KnowledgeSearchRequest) -> Filter | None:
        """Build a Qdrant filter from the search request."""
        conditions: list[Any] = []
        if request.job_type:
            conditions.append(
                FieldCondition(key="job_types", match=MatchValue(value=request.job_type))
            )
        if request.rule_tier:
            conditions.append(
                FieldCondition(key="rule_tier", match=MatchValue(value=request.rule_tier))
            )
        if request.doc_type:
            conditions.append(
                FieldCondition(key="doc_type", match=MatchValue(value=request.doc_type))
            )
        if not conditions:
            return None
        return Filter(must=conditions)

    def _hit_to_result(self, hit: Any) -> KnowledgeSearchResult:
        payload = hit.payload or {}
        return KnowledgeSearchResult(
            id=str(hit.id),
            score=hit.score,
            text=payload.get("text", ""),
            source=payload.get("source", ""),
            section_path=payload.get("section_path", []),
            rule_tier=payload.get("rule_tier", "reference"),
            job_types=payload.get("job_types", []),
            doc_type=payload.get("doc_type", "prose"),
        )

    async def search(self, request: KnowledgeSearchRequest) -> list[KnowledgeSearchResult]:
        """Search the knowledge collection."""
        await self.ensure_collection()
        vector = await self.embed_text(request.query)
        search_filter = self._build_filter(request)
        response = await self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=search_filter,
            limit=request.limit,
            with_payload=True,
        )
        return [self._hit_to_result(hit) for hit in response.points]

    async def upsert_chunk(
        self,
        chunk_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Upsert a single knowledge chunk (useful for tests and small updates)."""
        await self.ensure_collection()
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=chunk_id, vector=vector, payload=payload)],
        )


async def search_knowledge(
    query: str,
    *,
    job_type: str | None = None,
    rule_tier: str | None = None,
    doc_type: str | None = None,
    limit: int = 5,
) -> list[KnowledgeSearchResult]:
    """Convenience helper: search knowledge with optional filters."""
    store = KnowledgeStore()
    return await store.search(
        KnowledgeSearchRequest(
            query=query,
            job_type=job_type,
            rule_tier=rule_tier,
            doc_type=doc_type,
            limit=limit,
        )
    )
