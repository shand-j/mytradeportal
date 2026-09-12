"""Regression tests for the N21/C6 retrieval fixes.

N21: quotes returned "no catalog match" for items that ARE in the catalogue.
Root cause: the retrieval read path called ``ensure_collection`` with the
configured embedding dimensions; when prod bumped EMBEDDING_MODEL from
text-embedding-3-small (1536) to 3-large (3072), the first query deleted and
recreated the entire indexed collection, and every subsequent search silently
returned zero results. These tests pin the fixed behaviour:

- the read path NEVER creates/deletes/recreates collections
- a missing / dimension-mismatched / empty / unreachable index degrades to
  the Postgres lexical fallback and logs at error level with the cause
- C6: catalogue units flow into grounded line items; only non-catalogue
  fallback lines may default to "ea"
"""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app import config as generation_config
from app.rag import retrieval
from app.rag.retrieval import get_embedding_dimension, search_cost_items_with_status
from app.rag.validation import validate_generated_quote


def _configured_dims() -> int:
    return get_embedding_dimension()


def _mock_qdrant_client(
    *,
    collection_exists: bool = True,
    collection_dims: int | None = None,
    points: list[Any] | None = None,
) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.collection_exists.return_value = collection_exists
    mock_info = MagicMock()
    mock_info.config.params.vectors.size = (
        collection_dims if collection_dims is not None else _configured_dims()
    )
    mock_client.get_collection.return_value = mock_info
    if points is not None:
        mock_query_response = MagicMock()
        mock_query_response.points = points
        mock_client.query_points.return_value = mock_query_response
    return mock_client


def _make_point(code: str, description: str, unit: str, score: float = 0.9) -> MagicMock:
    point = MagicMock()
    point.payload = {
        "code": code,
        "description": description,
        "unit": unit,
        "unit_price": "12.50",
        "category": "Cable",
        "source": "domestic_pipeline",
    }
    point.score = score
    return point


@pytest.fixture
def _embedding_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation_config.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(generation_config.settings, "embedding_api_key", "sk-test")


@pytest.mark.asyncio
async def test_dimension_mismatch_never_deletes_collection_and_degrades_loudly(
    _embedding_key: None,
) -> None:
    """The N21 root cause: index at 1536, config at 3072 → read path must not
    wipe the collection; it logs an error and falls back to lexical search."""
    mismatched_dims = 1536 if _configured_dims() != 1536 else 3072
    mock_client = _mock_qdrant_client(collection_dims=mismatched_dims)
    lexical = AsyncMock(return_value=([], "no_index"))

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieval._lexical_search_cost_items_with_status", new=lexical),
        patch.object(retrieval, "logger", new=MagicMock()) as mock_logger,
    ):
        items, status = await search_cost_items_with_status("consumer unit replacement")

    assert (items, status) == ([], "no_index")
    # The collection was NOT deleted or recreated — the read path is read-only.
    mock_client.delete_collection.assert_not_called()
    mock_client.create_collection.assert_not_called()
    mock_client.query_points.assert_not_called()
    # The mismatch is logged at error level with cause + remediation.
    error_events = [call.args[0] for call in mock_logger.error.call_args_list]
    assert "retrieval_collection_dimension_mismatch" in error_events
    assert "retrieval_fallback" in error_events
    lexical.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_collection_falls_back_without_creating(_embedding_key: None) -> None:
    mock_client = _mock_qdrant_client(collection_exists=False)
    lexical = AsyncMock(return_value=([], "no_index"))

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieval._lexical_search_cost_items_with_status", new=lexical),
        patch.object(retrieval, "logger", new=MagicMock()) as mock_logger,
    ):
        items, status = await search_cost_items_with_status("twin and earth cable")

    assert (items, status) == ([], "no_index")
    mock_client.create_collection.assert_not_called()
    mock_client.delete_collection.assert_not_called()
    error_events = [call.args[0] for call in mock_logger.error.call_args_list]
    assert "retrieval_collection_missing" in error_events
    lexical.assert_awaited_once()


@pytest.mark.asyncio
async def test_qdrant_query_error_logs_error_and_degrades_to_lexical(
    _embedding_key: None,
) -> None:
    mock_client = _mock_qdrant_client()
    mock_client.query_points.side_effect = ConnectionError("qdrant unreachable")
    lexical_items = [{"code": "ELEC-CU", "description": "Consumer unit", "score": 0.8}]
    lexical = AsyncMock(return_value=(lexical_items, "grounded"))

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieval._lexical_search_cost_items_with_status", new=lexical),
        patch.object(retrieval, "logger", new=MagicMock()) as mock_logger,
    ):
        items, status = await search_cost_items_with_status("consumer unit")

    assert status == "grounded"
    assert items == lexical_items
    error_events = [call.args[0] for call in mock_logger.error.call_args_list]
    assert "retrieval_fallback" in error_events
    fallback_call = mock_logger.error.call_args_list[0]
    assert fallback_call.kwargs["reason"] == "qdrant_error"
    assert "qdrant unreachable" in fallback_call.kwargs["error"]


@pytest.mark.asyncio
async def test_empty_vector_index_falls_back_to_lexical(_embedding_key: None) -> None:
    """A healthy-but-empty index (post-recreate, pre-ingest) must not silently
    report no_index while Postgres has matching rows."""
    mock_client = _mock_qdrant_client(points=[])
    lexical_items = [
        {"code": "DOM-screwfix-20967", "description": "6242Y twin & earth", "score": 0.75}
    ]
    lexical = AsyncMock(return_value=(lexical_items, "grounded"))

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieval._lexical_search_cost_items_with_status", new=lexical),
        patch.object(retrieval, "logger", new=MagicMock()) as mock_logger,
    ):
        items, status = await search_cost_items_with_status("twin and earth cable")

    assert status == "grounded"
    assert items == lexical_items
    error_events = [call.args[0] for call in mock_logger.error.call_args_list]
    assert "retrieval_index_empty" in error_events


@pytest.mark.asyncio
async def test_healthy_collection_returns_grounded_without_mutation(
    _embedding_key: None,
) -> None:
    mock_client = _mock_qdrant_client(
        points=[_make_point("DOM-screwfix-49620", "13A double socket", "each")]
    )
    lexical = AsyncMock(return_value=([], "no_index"))

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieval._lexical_search_cost_items_with_status", new=lexical),
    ):
        items, status = await search_cost_items_with_status("add a socket")

    assert status == "grounded"
    assert items[0]["code"] == "DOM-screwfix-49620"
    assert items[0]["unit"] == "each"
    mock_client.delete_collection.assert_not_called()
    mock_client.create_collection.assert_not_called()
    lexical.assert_not_called()


def test_get_embedding_dimension_prefers_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EMBEDDING_DIMENSIONS (pinned identically for api + data-pipeline in
    Railway IaC) wins over the model lookup table."""
    monkeypatch.setattr(generation_config.settings, "embedding_dimensions", 3072)
    monkeypatch.setattr(generation_config.settings, "embedding_model", "text-embedding-3-small")
    assert get_embedding_dimension() == 3072

    monkeypatch.setattr(generation_config.settings, "embedding_dimensions", None)
    monkeypatch.setattr(generation_config.settings, "embedding_model", "text-embedding-3-small")
    assert get_embedding_dimension() == 1536
    monkeypatch.setattr(generation_config.settings, "embedding_model", "text-embedding-3-large")
    assert get_embedding_dimension() == 3072


# --- C6: catalogue units flow into line items -----------------------------


def test_grounded_line_uses_catalogue_unit_over_llm_unit() -> None:
    """C6: a cable line grounded to a per-metre catalogue item bills in "m",
    even when the LLM labelled the line "job"."""
    retrieved = [
        {
            "code": "DOM-screwfix-20967",
            "description": "[Cable] 6242Y Twin & Earth Cable 2.5mm 100m Drum",
            "unit": "m",
            "unit_price": "0.93",
            "score": 0.9,
        }
    ]
    generated = {
        "line_items": [
            {
                "description": "Twin & earth cable",
                "kind": "material",
                "quantity": 30,
                "unit": "job",
                "unit_price": 27.90,
                "code": "DOM-screwfix-20967",
            }
        ],
        "notes": "",
    }

    result = validate_generated_quote(generated, retrieved, tenant_settings={})

    line = result["line_items"][0]
    assert line["unit"] == "m"
    assert line["unit_price"] == Decimal("0.93")


def test_auto_grounded_line_uses_catalogue_unit() -> None:
    """C6: the deterministic auto-grounder also takes the catalogue unit."""
    retrieved = [
        {
            "code": "DOM-screwfix-20967",
            "description": "[Cable] 6242Y Twin Earth Cable 2.5mm 100m Drum",
            "unit": "m",
            "unit_price": "0.93",
            "score": 0.9,
        }
    ]
    generated = {
        "line_items": [
            {
                "description": "Twin earth cable",
                "kind": "material",
                "quantity": 30,
                "unit": "job",
                "unit_price": 30.00,
            }
        ],
        "notes": "",
    }

    result = validate_generated_quote(generated, retrieved, tenant_settings={})

    assert result["auto_grounded"] == 1
    line = result["line_items"][0]
    assert line["code"] == "DOM-screwfix-20967"
    assert line["unit"] == "m"


def test_non_catalogue_lines_keep_llm_unit_or_default() -> None:
    """C6: only non-catalogue fallback lines may default to "ea"; labour
    without a unit defaults to "hour"; an explicit LLM unit is respected."""
    generated = {
        "line_items": [
            {
                "description": "Bespoke containment fabrication",
                "kind": "material",
                "quantity": 1,
                "unit_price": 120.00,
            },
            {
                "description": "Installation labour",
                "kind": "labour",
                "quantity": 3,
                "unit_price": 65.00,
            },
            {
                "description": "Whole-job fixed price line",
                "kind": "material",
                "quantity": 1,
                "unit": "job",
                "unit_price": 250.00,
            },
        ],
        "notes": "",
    }

    result = validate_generated_quote(generated, retrieved_items=[], tenant_settings={})

    units = [line["unit"] for line in result["line_items"]]
    assert units == ["ea", "hour", "job"]
