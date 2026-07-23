"""Vector retrieval of cost items from Qdrant for the OpenConstructionERP service."""

from typing import Any

from litellm import aembedding
from openai import APIError
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select

from ocerp.config import settings
from ocerp.database import get_db_session
from ocerp.models import CostItem
from ocerp.qdrant import ensure_collection, get_qdrant_client


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
    source: str | None = None,
    sources: list[str] | None = None,
    category: str | None = None,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Embed a query and return the most similar cost items from Qdrant."""
    vector = await embed_text(query)
    limit = top_k or settings.rag_top_k

    qdrant = get_qdrant_client()
    await ensure_collection(
        qdrant,
        settings.qdrant_collection_name,
        vector_size=get_embedding_dimension(),
    )

    must_conditions: list[Any] = [
        FieldCondition(key="trade", match=MatchValue(value=trade)),
        FieldCondition(key="region", match=MatchValue(value=region)),
        FieldCondition(key="is_active", match=MatchValue(value=True)),
    ]

    active_sources = sources if sources is not None else ([source] if source else None)
    if active_sources:
        must_conditions.append(
            Filter(
                should=[
                    FieldCondition(key="source", match=MatchValue(value=s)) for s in active_sources
                ]
            )
        )

    active_categories = categories if categories is not None else ([category] if category else None)
    if active_categories:
        must_conditions.append(
            Filter(
                should=[
                    FieldCondition(key="category", match=MatchValue(value=c))
                    for c in active_categories
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


async def get_cost_items_by_codes(codes: list[str]) -> list[dict[str, Any]]:
    """Fetch active cost items by their codes from the operational database."""
    if not codes:
        return []
    async with get_db_session() as session:
        result = await session.execute(
            select(CostItem).where(CostItem.code.in_(codes), CostItem.is_active.is_(True))
        )
        return [
            {
                "code": item.code,
                "description": item.description,
                "unit": item.unit,
                "unit_price": str(item.unit_price),
                "category": item.category,
                "source": item.source,
                "supplier": item.extra_data.get("supplier") if item.extra_data else None,
                "brand": item.extra_data.get("brand") if item.extra_data else None,
                "sku": item.extra_data.get("sku") if item.extra_data else None,
                "product_url": item.extra_data.get("product_url") if item.extra_data else None,
                "retail_price_incl_vat": str(item.extra_data.get("retail_price_incl_vat"))
                if item.extra_data and item.extra_data.get("retail_price_incl_vat") is not None
                else None,
                "metre_length": item.extra_data.get("metre_length") if item.extra_data else None,
            }
            for item in result.scalars().all()
        ]
