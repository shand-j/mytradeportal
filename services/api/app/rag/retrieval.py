"""Vector retrieval of cost items from Qdrant."""

from typing import Any

from litellm import aembedding
from openai import APIError
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import settings
from app.qdrant import ensure_collection, get_qdrant_client


def get_embedding_dimension() -> int:
    """Return the vector dimension for the configured embedding model."""
    if settings.embedding_dimensions:
        return settings.embedding_dimensions

    known_dimensions = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }
    return known_dimensions.get(settings.embedding_model, 1536)


def _embedding_kwargs(texts: list[str]) -> dict[str, Any]:
    """Build the kwargs for litellm.aembedding."""
    kwargs: dict[str, Any] = {
        "model": settings.embedding_model,
        "input": texts,
    }
    if settings.openai_api_key:
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


async def search_cost_items(
    query: str,
    trade: str = "electrical",
    region: str = "UK",
    top_k: int | None = None,
    sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Embed a query and return the most similar cost items from Qdrant.

    By default only ``domestic_pipeline`` (scraped supplier) items are returned
    so generated quotes are grounded in real catalogue prices.
    """
    vector = await embed_text(query)
    limit = top_k or settings.rag_top_k

    qdrant = get_qdrant_client()
    await ensure_collection(
        qdrant,
        settings.qdrant_collection_name,
        vector_size=get_embedding_dimension(),
    )

    active_sources = sources if sources is not None else ["domestic_pipeline"]
    must_conditions: list[Any] = [
        FieldCondition(key="trade", match=MatchValue(value=trade)),
        FieldCondition(key="region", match=MatchValue(value=region)),
        FieldCondition(key="is_active", match=MatchValue(value=True)),
    ]
    if active_sources:
        must_conditions.append(
            Filter(
                should=[
                    FieldCondition(key="source", match=MatchValue(value=s)) for s in active_sources
                ]
            )
        )

    response = await qdrant.query_points(
        collection_name=settings.qdrant_collection_name,
        query=vector,
        limit=limit,
        query_filter=Filter(must=must_conditions),
        with_payload=True,
    )

    return [
        {
            "code": point.payload.get("code") if point.payload else None,
            "description": point.payload.get("description") if point.payload else None,
            "unit": point.payload.get("unit") if point.payload else None,
            "unit_price": point.payload.get("unit_price") if point.payload else None,
            "category": point.payload.get("category") if point.payload else None,
            "source": point.payload.get("source") if point.payload else None,
            "supplier": point.payload.get("supplier") if point.payload else None,
            "brand": point.payload.get("brand") if point.payload else None,
            "sku": point.payload.get("sku") if point.payload else None,
            "product_url": point.payload.get("product_url") if point.payload else None,
            "retail_price_incl_vat": point.payload.get("retail_price_incl_vat")
            if point.payload
            else None,
            "metre_length": point.payload.get("metre_length") if point.payload else None,
            "score": point.score,
        }
        for point in response.points
    ]
