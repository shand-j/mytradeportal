"""Vector retrieval of cost items from Qdrant, with a Postgres lexical fallback."""

import hashlib
import re
import time
from typing import Any

import httpx
import structlog
from litellm import aembedding
from openai import APIError
from qdrant_client.models import (
    FieldCondition,
    Filter,
    HasIdCondition,
    HasVectorCondition,
    IsEmptyCondition,
    IsNullCondition,
    MatchAny,
    MatchValue,
    NestedCondition,
    SliceCondition,
)
from sqlalchemy import or_, select

from app.config import settings
from app.database import get_db_session
from app.models import CostItem
from app.qdrant import ensure_collection, get_qdrant_client
from app.rag.intent import extract_query_intent

FilterCondition = (
    FieldCondition
    | IsEmptyCondition
    | IsNullCondition
    | HasIdCondition
    | HasVectorCondition
    | SliceCondition
    | NestedCondition
    | Filter
)

logger = structlog.get_logger("api.rag")

# In-process embedding cache: embeddings for identical queries are stable, so
# repeat catalogue lookups (generate → refine → regenerate) skip the remote
# embedding call entirely. Bounded so a busy worker cannot grow without limit.
_EMBEDDING_CACHE_TTL_SECONDS = 24 * 60 * 60
_EMBEDDING_CACHE_MAX_ENTRIES = 512
_embedding_cache: dict[str, tuple[float, list[float]]] = {}


def _embedding_cache_key(text: str) -> str:
    """Stable cache key: sha256 of the model plus the normalised query text."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(f"{settings.embedding_model}:{normalized}".encode()).hexdigest()


def _embedding_cache_get(key: str) -> list[float] | None:
    entry = _embedding_cache.get(key)
    if entry is None:
        return None
    created_at, vector = entry
    if time.monotonic() - created_at > _EMBEDDING_CACHE_TTL_SECONDS:
        _embedding_cache.pop(key, None)
        return None
    return vector


def _embedding_cache_put(key: str, vector: list[float]) -> None:
    if len(_embedding_cache) >= _EMBEDDING_CACHE_MAX_ENTRIES:
        # Evict the oldest quarter in one pass rather than one entry at a time.
        oldest = sorted(_embedding_cache, key=lambda k: _embedding_cache[k][0])
        for stale_key in oldest[: _EMBEDDING_CACHE_MAX_ENTRIES // 4]:
            _embedding_cache.pop(stale_key, None)
    _embedding_cache[key] = (time.monotonic(), vector)


# Lexical fallback retrieval (used when no embedding provider is configured).
#
# The production LLM (Kimi) has no embeddings API, so when no embedding key is
# configured the catalogue is searched directly in Postgres with a simple
# token-overlap score instead of vector similarity.

# Words that carry no catalogue-matching signal on their own.
_LEXICAL_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "on",
        "with",
        "install",
        "installation",
        "supply",
        "replacement",
        "replace",
        "new",
        "add",
        "fit",
        "fitting",
        "upgrade",
        "remove",
    }
)

# Cap the tokens used in the SQL pre-filter so pathological queries cannot
# build unbounded OR chains; ranking still uses every token.
_LEXICAL_MAX_SQL_TOKENS = 12

# Short-TTL per-process cache: catalogue rows can change between deploys, so
# unlike embeddings these results are only reused for a few minutes.
_LEXICAL_CACHE_TTL_SECONDS = 5 * 60
_LEXICAL_CACHE_MAX_ENTRIES = 256
_lexical_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _tokenize_query(query: str) -> list[str]:
    """Split a query into lowercase alphanumeric tokens minus stopwords."""
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    seen: set[str] = set()
    meaningful: list[str] = []
    for token in tokens:
        if len(token) < 2 or token in _LEXICAL_STOPWORDS or token in seen:
            continue
        seen.add(token)
        meaningful.append(token)
    return meaningful


def _lexical_cache_key(query: str, trade: str, region: str, limit: int) -> str:
    normalized = " ".join(query.lower().split())
    return hashlib.sha256(f"{trade}:{region}:{limit}:{normalized}".encode()).hexdigest()


def _lexical_cache_get(key: str) -> list[dict[str, Any]] | None:
    entry = _lexical_cache.get(key)
    if entry is None:
        return None
    created_at, items = entry
    if time.monotonic() - created_at > _LEXICAL_CACHE_TTL_SECONDS:
        _lexical_cache.pop(key, None)
        return None
    return items


def _lexical_cache_put(key: str, items: list[dict[str, Any]]) -> None:
    if len(_lexical_cache) >= _LEXICAL_CACHE_MAX_ENTRIES:
        oldest = sorted(_lexical_cache, key=lambda k: _lexical_cache[k][0])
        for stale_key in oldest[: _LEXICAL_CACHE_MAX_ENTRIES // 4]:
            _lexical_cache.pop(stale_key, None)
    _lexical_cache[key] = (time.monotonic(), items)


def _cost_item_to_result(item: CostItem, score: float) -> dict[str, Any]:
    """Shape a CostItem row exactly like a Qdrant search result."""
    extra = item.extra_data or {}
    return {
        "code": item.code,
        "description": item.description,
        "unit": item.unit,
        "unit_price": str(item.unit_price),
        "category": item.category,
        "source": item.source,
        "supplier": extra.get("supplier"),
        "brand": extra.get("brand"),
        "sku": extra.get("sku"),
        "product_url": extra.get("product_url"),
        "retail_price_incl_vat": str(extra.get("retail_price_incl_vat"))
        if extra.get("retail_price_incl_vat") is not None
        else None,
        "metre_length": extra.get("metre_length"),
        "score": score,
    }


async def _lexical_search_cost_items_with_status(
    query: str,
    trade: str,
    region: str,
    top_k: int | None,
) -> tuple[list[dict[str, Any]], str]:
    """Search cost_items in Postgres by token overlap (no embeddings needed).

    SQL pre-filters active rows whose description contains any query token,
    then Python ranks them by the ratio of distinct query tokens that appear
    in the description/category. Returns the same ``(items, status)`` contract
    as the vector path. Never raises: any database error is logged and reported
    as ``([], "no_index")`` so quote generation can still proceed ungrounded.
    """
    limit = top_k or settings.rag_top_k
    tokens = _tokenize_query(query)
    if not tokens:
        logger.debug("lexical_retrieval_skipped", reason="no_meaningful_tokens")
        return [], "no_index"

    cache_key = _lexical_cache_key(query, trade, region, limit)
    cached = _lexical_cache_get(cache_key)
    if cached is not None:
        logger.debug("lexical_retrieval_cache_hit", item_count=len(cached))
        return cached, "grounded" if cached else "no_index"

    started = time.perf_counter()
    try:
        token_filters = [
            CostItem.description.ilike(f"%{token}%") for token in tokens[:_LEXICAL_MAX_SQL_TOKENS]
        ]
        async with get_db_session() as db:
            result = await db.execute(
                select(CostItem).where(
                    CostItem.trade == trade,
                    CostItem.region == region,
                    CostItem.is_active.is_(True),
                    or_(*token_filters),
                )
            )
            rows = list(result.scalars().all())
    except Exception as exc:
        logger.error(
            "lexical_retrieval_error",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        return [], "no_index"

    scored: list[tuple[float, str, CostItem]] = []
    for row in rows:
        haystack = f"{row.description} {row.category}".lower()
        hits = sum(1 for token in tokens if token in haystack)
        if hits:
            scored.append((hits / len(tokens), row.code, row))
    # Highest token-hit ratio first; code tie-break keeps the order stable.
    scored.sort(key=lambda entry: (-entry[0], entry[1]))

    items = [_cost_item_to_result(row, score) for score, _, row in scored[:limit]]
    retrieval_status = "grounded" if items else "no_index"
    _lexical_cache_put(cache_key, items)
    logger.info(
        "lexical_retrieval_completed",
        status=retrieval_status,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        item_count=len(items),
        candidate_count=len(rows),
        top_k=limit,
        query_chars=len(query),
    )
    return items, retrieval_status


def get_embedding_dimension() -> int:
    """Return the vector dimension for the configured embedding model."""
    if settings.embedding_dimensions:
        return int(settings.embedding_dimensions)

    known_dimensions: dict[str, int] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }
    return known_dimensions.get(settings.embedding_model, 1536)


def _embedding_kwargs(texts: list[str]) -> dict[str, Any]:
    """Build the kwargs for litellm.aembedding."""
    kwargs: dict[str, Any] = {
        "model": settings.embedding_model,
        "input": texts,
        "timeout": settings.llm_timeout_seconds,
        "num_retries": 1,
    }
    if settings.resolved_embedding_api_key:
        kwargs["api_key"] = settings.resolved_embedding_api_key
    if settings.embedding_api_base:
        kwargs["api_base"] = settings.embedding_api_base
    return kwargs


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return embedding vectors for the supplied texts (cached per text)."""
    if not texts:
        return []
    if not settings.resolved_embedding_api_key:
        raise RuntimeError("Embedding API key is not configured")

    results: dict[int, list[float]] = {}
    missing: list[tuple[int, str]] = []
    for index, text in enumerate(texts):
        cached = _embedding_cache_get(_embedding_cache_key(text))
        if cached is None:
            missing.append((index, text))
        else:
            results[index] = cached

    if missing:
        started = time.perf_counter()
        try:
            response = await aembedding(**_embedding_kwargs([text for _, text in missing]))
        except APIError as exc:
            logger.error(
                "llm_error",
                phase="embedding",
                model=settings.embedding_model,
                error_type=type(exc).__name__,
            )
            raise RuntimeError(f"Embedding failed: {exc.message}") from exc
        except (httpx.HTTPError, ConnectionError, OSError) as exc:
            logger.error(
                "llm_error",
                phase="embedding",
                model=settings.embedding_model,
                error_type=type(exc).__name__,
            )
            raise RuntimeError(f"Embedding service unavailable: {exc}") from exc
        logger.info(
            "embedding_generated",
            model=settings.embedding_model,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            text_count=len(missing),
            cache_hits=len(texts) - len(missing),
        )
        for (index, text), item in zip(missing, response.data, strict=True):
            vector = item.get("embedding")
            _embedding_cache_put(_embedding_cache_key(text), vector)
            results[index] = vector

    return [results[index] for index in range(len(texts))]


async def embed_text(text: str) -> list[float]:
    """Return a single embedding vector for the supplied text."""
    return (await embed_texts([text]))[0]


async def search_knowledge_chunks(
    query: str,
    *,
    top_k: int = 3,
    doc_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search the quoting-knowledge collection for guidance chunks.

    Returns items with ``text``, ``source``, ``section_path``, ``doc_type``,
    ``job_types``, and ``score``. Empty list on any failure — knowledge is
    supplementary; quote generation must not break if it is missing.
    """
    if not settings.resolved_embedding_api_key:
        return []
    try:
        vector = await embed_text(query)
    except Exception:
        logger.warning("knowledge_embed_failed", query_chars=len(query))
        return []

    qdrant = get_qdrant_client()
    try:
        await ensure_collection(
            qdrant,
            collection_name=settings.qdrant_knowledge_collection_name,
            vector_size=len(vector),
        )
    except Exception:
        logger.warning(
            "knowledge_collection_check_failed",
            collection=settings.qdrant_knowledge_collection_name,
        )
        return []

    must_conditions: list[FilterCondition] = []
    if doc_types:
        must_conditions.append(FieldCondition(key="doc_type", match=MatchAny(any=list(doc_types))))

    started = time.perf_counter()
    try:
        response = await qdrant.query_points(
            collection_name=settings.qdrant_knowledge_collection_name,
            query=vector,
            limit=top_k,
            query_filter=Filter(must=must_conditions) if must_conditions else None,
            with_payload=True,
        )
    except Exception as exc:
        logger.warning(
            "knowledge_retrieval_error",
            collection=settings.qdrant_knowledge_collection_name,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        return []

    items: list[dict[str, Any]] = []
    for point in response.points:
        payload = point.payload or {}
        items.append(
            {
                "text": payload.get("text"),
                "source": payload.get("source"),
                "section_path": payload.get("section_path") or [],
                "doc_type": payload.get("doc_type"),
                "job_types": payload.get("job_types") or [],
                "score": point.score,
            }
        )
    logger.info(
        "knowledge_retrieval_completed",
        collection=settings.qdrant_knowledge_collection_name,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        item_count=len(items),
        doc_types=doc_types,
        query_chars=len(query),
    )
    return items


async def search_cost_items_with_status(
    query: str,
    trade: str = "electrical",
    region: str = "UK",
    top_k: int | None = None,
    sources: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Embed a query and return the most similar cost items from Qdrant.

    Returns ``(items, status)`` where status is one of:

    - ``"grounded"`` — the catalogue search returned at least one item
      whose vector-similarity score cleared ``rag_min_relevance``
    - ``"weak_match"`` — vector search returned items but none cleared
      the relevance floor. The top three raw hits are returned anyway so
      the LLM has *something* to work with, and the retrieval-quality
      gate downstream will correctly cap confidence.
    - ``"no_index"`` — the search ran but returned zero results (also used
      when the search itself failed, so generation continues ungrounded)
    - ``"skipped_no_key"`` — retrieval could not run at all (reserved; with
      no embedding provider configured the Postgres lexical fallback runs
      instead, so this is no longer emitted by the no-key path)

    When no embedding API key is configured, retrieval falls back to a lexical
    token-overlap search of the Postgres ``cost_items`` table (the production
    LLM has no embeddings API). The lexical path searches all active sources
    and ignores the ``sources`` filter.

    By default only ``domestic_pipeline`` (scraped supplier) items are returned
    so generated quotes are grounded in real catalogue prices.
    """
    if not settings.resolved_embedding_api_key:
        logger.debug("retrieval_fallback", reason="no_embedding_key", mode="lexical")
        return await _lexical_search_cost_items_with_status(
            query, trade=trade, region=region, top_k=top_k
        )

    try:
        vector = await embed_text(query)
    except Exception as exc:
        # Embedding provider blip (DNS/connection) must not 500 quote
        # generation — degrade to the Postgres lexical search instead.
        logger.warning(
            "retrieval_fallback",
            reason="embedding_error",
            mode="lexical",
            error_type=type(exc).__name__,
        )
        return await _lexical_search_cost_items_with_status(
            query, trade=trade, region=region, top_k=top_k
        )
    limit = top_k or settings.rag_top_k

    qdrant = get_qdrant_client()

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

    # Query-side intent filters (e.g. alarm_purpose=fire) rule out semantic
    # siblings that vector similarity alone cannot separate. Empty intent =
    # vector-only search, preserving the previous behaviour for ambiguous
    # queries.
    query_intent = extract_query_intent(query)
    for attr_key, attr_value in query_intent.items():
        must_conditions.append(
            FieldCondition(key=f"attr_{attr_key}", match=MatchValue(value=attr_value))
        )

    started = time.perf_counter()
    try:
        await ensure_collection(
            qdrant,
            settings.qdrant_collection_name,
            vector_size=get_embedding_dimension(),
        )
        response = await qdrant.query_points(
            collection_name=settings.qdrant_collection_name,
            query=vector,
            limit=limit,
            query_filter=Filter(must=must_conditions),
            with_payload=True,
        )
    except Exception as exc:
        # Qdrant/DNS blips are transient and must not 500 quote generation —
        # degrade to the Postgres lexical search so quotes still generate.
        logger.warning(
            "retrieval_fallback",
            reason="qdrant_error",
            mode="lexical",
            collection=settings.qdrant_collection_name,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        return await _lexical_search_cost_items_with_status(
            query, trade=trade, region=region, top_k=top_k
        )

    items = [
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
    # Drop weak matches so the LLM prompt is not padded with irrelevant items
    # that dilute the "MUST cite" instruction. When intent filters already
    # constrain the pool to the right *kind* of item (e.g. cable_type=swa),
    # relax the floor: any survivor is on-purpose by construction, so vector
    # score just orders them rather than gating them.
    raw_count = len(items)
    min_relevance = settings.rag_min_relevance / 2 if query_intent else settings.rag_min_relevance
    if min_relevance > 0.0 and items:
        filtered = [item for item in items if (item.get("score") or 0.0) >= min_relevance]
        if filtered:
            items = filtered
            retrieval_status = "grounded"
        else:
            # Broad queries (e.g. "partial rewire") can leave every hit below the
            # floor. Keep the top three so the LLM + auto-grounder aren't blind;
            # the retrieval-quality gate will cap confidence downstream.
            items = items[:3]
            retrieval_status = "weak_match"
    else:
        retrieval_status = "grounded" if items else "no_index"
    logger.info(
        "retrieval_completed",
        status=retrieval_status,
        collection=settings.qdrant_collection_name,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        item_count=len(items),
        raw_item_count=raw_count,
        min_relevance=min_relevance,
        top_k=limit,
        query_chars=len(query),
        intent_filters=len(query_intent),
    )
    return items, retrieval_status


async def search_cost_items(
    query: str,
    trade: str = "electrical",
    region: str = "UK",
    top_k: int | None = None,
    sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Embed a query and return the most similar cost items from Qdrant.

    Thin wrapper around :func:`search_cost_items_with_status` for callers that
    only need the items.
    """
    items, _ = await search_cost_items_with_status(
        query, trade=trade, region=region, top_k=top_k, sources=sources
    )
    return items


def compute_retrieval_quality(
    items: list[dict[str, Any]],
    *,
    knowledge_available: bool | None = None,
) -> dict[str, Any]:
    """Score retrieval quality against the configured ``retrieval_quality_*`` gates.

    The fields on ``mtp_shared.config`` defined the shape of the quality signal
    (min citations / min top-relevance / knowledge availability / fallback
    policy / confidence cap) but no code read them; this consolidates that
    logic in one place so the eval harness, the quotes router, and the
    validation layer all agree on what "good enough" retrieval means.

    Returned dict:
    - ``top_relevance``: max ``score`` on any returned item (0.0 when empty).
    - ``citations``: ``len(items)``.
    - ``passes_min_citations``: ``citations >= settings.retrieval_quality_min_citations``.
    - ``passes_min_relevance``: ``top_relevance >= settings.retrieval_quality_min_top_relevance``.
    - ``passes_knowledge_requirement``: ``True`` unless the
      require-knowledge-available gate is on and ``knowledge_available=False``.
    - ``passes_gates``: all three gates above.
    - ``fallback_policy``: from settings (``warn_only`` | ``deterministic_only``).
    - ``confidence_cap``: from settings; the validation layer caps the
      per-quote confidence to this value when ``passes_gates=False``.
    """
    scores = [item.get("score") or 0.0 for item in items]
    top_relevance = max(scores) if scores else 0.0
    citations = len(items)

    passes_min_citations = citations >= settings.retrieval_quality_min_citations
    passes_min_relevance = top_relevance >= settings.retrieval_quality_min_top_relevance
    if settings.retrieval_quality_require_knowledge_available:
        passes_knowledge_requirement = bool(knowledge_available)
    else:
        passes_knowledge_requirement = True

    return {
        "top_relevance": round(top_relevance, 4),
        "citations": citations,
        "passes_min_citations": passes_min_citations,
        "passes_min_relevance": passes_min_relevance,
        "passes_knowledge_requirement": passes_knowledge_requirement,
        "passes_gates": (
            passes_min_citations and passes_min_relevance and passes_knowledge_requirement
        ),
        "fallback_policy": settings.retrieval_quality_fallback_policy,
        "confidence_cap": settings.retrieval_quality_confidence_cap,
    }
