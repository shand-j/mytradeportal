"""Embedding model → vector dimension map shared by all services.

Single source of truth for the Qdrant vector size of each supported embedding
model, consumed by the API retrieval path and the data-pipeline ingest so both
always agree on the collection dimension.
"""

EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

# Fallback when the model is not in the table. Matches OpenAI's
# text-embedding-3-small/-ada-002 family size.
_DEFAULT_EMBEDDING_DIMENSION = 1536


def get_embedding_dimension(model: str) -> int:
    """Return the vector dimension for the given embedding model."""
    return EMBEDDING_DIMENSIONS.get(model, _DEFAULT_EMBEDDING_DIMENSION)
