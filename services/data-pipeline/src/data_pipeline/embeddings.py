"""Embedding helpers for the data pipeline.

Mirrors the OCERP retrieval embedding configuration so that vectors produced
by the pipeline are compatible with the cost_items Qdrant collection.
"""

from typing import Any

from litellm import aembedding
from openai import APIError

from data_pipeline.config import settings


def _is_ollama_model(model: str) -> bool:
    return model.startswith("ollama/")


def get_embedding_dimension() -> int:
    """Return the vector dimension for the configured embedding model."""
    if settings.embedding_dimensions:
        return settings.embedding_dimensions

    known_dimensions = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "ollama/nomic-embed-text": 768,
        "nomic-embed-text": 768,
    }
    return known_dimensions.get(settings.embedding_model, 1536)


def _embedding_kwargs(texts: list[str]) -> dict[str, Any]:
    """Build the kwargs for litellm.aembedding based on the provider."""
    kwargs: dict[str, Any] = {
        "model": settings.embedding_model,
        "input": texts,
    }
    if _is_ollama_model(settings.embedding_model):
        kwargs["api_base"] = settings.ollama_api_base
    elif settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    return kwargs


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return embedding vectors for the supplied texts."""
    if not texts:
        return []
    try:
        response = await aembedding(**_embedding_kwargs(texts))
    except APIError as exc:
        raise RuntimeError(f"Embedding failed: {exc.message}") from exc
    return [item.get("embedding") for item in response.data]


async def embed_text(text: str) -> list[float]:
    """Return a single embedding vector for the supplied text."""
    return (await embed_texts([text]))[0]
