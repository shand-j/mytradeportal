"""Qdrant vector database client and helpers for the data pipeline."""

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from data_pipeline.config import settings
from data_pipeline.embeddings import get_embedding_dimension


def get_qdrant_client() -> AsyncQdrantClient:
    """Return an async Qdrant client from settings."""
    return AsyncQdrantClient(url=settings.qdrant_url, check_compatibility=False)


async def ensure_collection(
    client: AsyncQdrantClient,
    collection_name: str = settings.qdrant_collection_name,
    vector_size: int | None = None,
    distance: Distance = Distance.COSINE,
) -> None:
    """Create a Qdrant collection if it does not already exist.

    If the collection exists with a different vector size it is recreated so
    that the configured embedding model can be used.
    """
    vector_size = vector_size or get_embedding_dimension()
    exists = await client.collection_exists(collection_name)
    if exists:
        info = await client.get_collection(collection_name)
        current_size = info.config.params.vectors.size  # type: ignore[union-attr]
        if current_size != vector_size:
            await client.delete_collection(collection_name)
            exists = False

    if not exists:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
        )
