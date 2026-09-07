"""Tests for the RAG Quote Engine modules."""

import importlib.util
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app import config as generation_config
from app.database import AsyncSessionLocal
from app.models import CostItem, QuoteRequest
from app.rag.generation import (
    FOLLOWUP_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    generate_followup,
    generate_quote_from_prompt,
)
from app.rag.retrieval import (
    _embedding_cache,
    _lexical_cache,
    embed_texts,
    search_cost_items,
    search_cost_items_with_status,
)
from app.rag.validation import validate_generated_quote
from sqlalchemy import delete as sa_delete
from sqlalchemy import func as sa_func
from sqlalchemy import select


@pytest.mark.asyncio
async def test_search_cost_items() -> None:
    retrieved_payload = {
        "code": "ELEC-SOCKET-ADD",
        "description": "Add a double socket",
        "unit": "each",
        "unit_price": "85.00",
        "category": "Sockets",
        "trade": "electrical",
        "region": "UK",
        "is_active": True,
    }
    mock_point = MagicMock()
    mock_point.payload = retrieved_payload
    mock_point.score = 0.95

    mock_query_response = MagicMock()
    mock_query_response.points = [mock_point]

    mock_client = AsyncMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = mock_query_response

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
    ):
        generation_config.settings.openai_api_key = "sk-test"
        results = await search_cost_items("add a socket")

    assert len(results) == 1
    assert results[0]["code"] == "ELEC-SOCKET-ADD"
    assert results[0]["score"] == 0.95


@pytest.mark.asyncio
async def test_generate_quote_from_prompt() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"line_items": [{"code": "ELEC-SOCKET-ADD", "quantity": 2, "reason": "two sockets"}], "notes": ""}'
            )
        )
    ]

    cost_items = [
        {
            "code": "ELEC-SOCKET-ADD",
            "description": "Add a double socket",
            "unit": "each",
            "unit_price": "85.00",
            "category": "Sockets",
        }
    ]

    with patch("app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)):
        generation_config.settings.openai_api_key = "sk-test"
        result = await generate_quote_from_prompt(
            job_description="I need two extra sockets",
            cost_items=cost_items,
            tenant_settings={},
            knowledge_chunks=[],
        )

    assert result["line_items"][0]["code"] == "ELEC-SOCKET-ADD"
    assert result["line_items"][0]["quantity"] == 2


@pytest.mark.asyncio
async def test_generate_quote_from_prompt_includes_system_prompt() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"line_items": [], "notes": ""}'))
    ]

    with patch(
        "app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)
    ) as mock_acompletion:
        generation_config.settings.openai_api_key = "sk-test"
        await generate_quote_from_prompt(
            job_description="rewire a house",
            cost_items=[],
            tenant_settings={},
            knowledge_chunks=[],
        )

    assert mock_acompletion.call_args is not None
    messages = mock_acompletion.call_args.kwargs.get("messages")
    assert messages is not None
    assert messages[0]["role"] == "system"
    assert SYSTEM_PROMPT in messages[0]["content"]


@pytest.mark.asyncio
async def test_generate_quote_from_prompt_resolves_catalogue_refs() -> None:
    """LLM returns integer indices; the server maps them back to real codes."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"line_items": ['
                    '{"description": "6242Y 2.5mm² 100m", "kind": "material", '
                    '"quantity": 1, "unit": "each", "unit_price": 92.99, '
                    '"catalogue_ref": 2, "reason": "matches spec"},'
                    '{"description": "13A double socket", "kind": "material", '
                    '"quantity": 3, "unit": "each", "unit_price": 4.99, '
                    '"catalogue_ref": "1.", "reason": "closest brand"},'
                    '{"description": "Consumer unit swap", "kind": "labour", '
                    '"quantity": 1, "unit": "job", "unit_price": 320, '
                    '"catalogue_ref": null, "reason": "labour line"},'
                    '{"description": "Bogus", "kind": "material", '
                    '"quantity": 1, "unit": "each", "unit_price": 9.99, '
                    '"catalogue_ref": 99, "reason": "out of range"}'
                    '], "notes": ""}'
                )
            )
        )
    ]
    cost_items = [
        {
            "code": "DOM-screwfix-49620",
            "description": "13A DP socket",
            "unit": "each",
            "unit_price": "4.99",
        },
        {
            "code": "DOM-screwfix-20967",
            "description": "6242Y 2.5mm² 100m drum",
            "unit": "each",
            "unit_price": "92.99",
        },
    ]

    with patch("app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)):
        generation_config.settings.openai_api_key = "sk-test"
        parsed = await generate_quote_from_prompt(
            job_description="rewire a house",
            cost_items=cost_items,
            tenant_settings={},
            knowledge_chunks=[],
        )

    lines = parsed["line_items"]
    # ref=2 → second catalogue item's code
    assert lines[0]["code"] == "DOM-screwfix-20967"
    # string "1." coerced to int 1 → first catalogue item's code
    assert lines[1]["code"] == "DOM-screwfix-49620"
    # labour: no ref, no code injected
    assert lines[2].get("code") in (None, "")
    # out-of-range ref: cleared to null, no code
    assert lines[3].get("code") in (None, "")
    assert lines[3]["catalogue_ref"] is None


@pytest.mark.asyncio
async def test_generate_quote_from_prompt_renders_knowledge_chunks() -> None:
    """When knowledge_chunks are provided, their text is embedded in the prompt."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"line_items": [], "notes": ""}'))
    ]
    knowledge = [
        {
            "text": (
                "Labour norm: Install additional double socket\nTypical hours: 1 (range 0.5-2)"
            ),
            "source": "labour_norms_uk",
            "doc_type": "labour_norm",
            "score": 0.72,
        }
    ]

    with patch(
        "app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)
    ) as mock_acompletion:
        generation_config.settings.openai_api_key = "sk-test"
        await generate_quote_from_prompt(
            job_description="add three double sockets",
            cost_items=[],
            tenant_settings={},
            knowledge_chunks=knowledge,
        )

    user_prompt = mock_acompletion.call_args.kwargs["messages"][1]["content"]
    assert "Labour norm: Install additional double socket" in user_prompt
    assert "Typical hours: 1" in user_prompt


@pytest.mark.asyncio
async def test_generate_quote_from_prompt_auto_retrieves_knowledge() -> None:
    """When knowledge_chunks is not provided, the function calls search_knowledge_chunks."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"line_items": [], "notes": ""}'))
    ]
    fake_knowledge = [
        {
            "text": "Labour norm: EICR 3-bed\nTypical hours: 4",
            "source": "labour_norms_uk",
            "doc_type": "labour_norm",
            "score": 0.6,
        }
    ]

    with (
        patch(
            "app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)
        ) as mock_acompletion,
        patch(
            "app.rag.retrieval.search_knowledge_chunks",
            new=AsyncMock(return_value=fake_knowledge),
        ) as mock_search,
    ):
        generation_config.settings.openai_api_key = "sk-test"
        await generate_quote_from_prompt(
            job_description="EICR on a 3-bed house",
            cost_items=[],
            tenant_settings={},
        )

    mock_search.assert_awaited_once()
    user_prompt = mock_acompletion.call_args.kwargs["messages"][1]["content"]
    assert "Labour norm: EICR 3-bed" in user_prompt


def test_validate_generated_quote() -> None:
    retrieved = [
        {
            "code": "ELEC-SOCKET-ADD",
            "description": "Add a double socket",
            "unit": "each",
            "unit_price": "85.00",
        }
    ]
    generated = {
        "line_items": [{"code": "ELEC-SOCKET-ADD", "quantity": 2, "reason": "kitchen and bedroom"}],
        "notes": "",
    }

    result = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings={},
    )

    assert len(result["line_items"]) == 1
    assert result["line_items"][0]["quantity"] == Decimal("2")
    assert result["line_items"][0]["unit_price"] == Decimal("85.00")
    assert result["confidence"] == 1.0
    assert not result["warnings"]


def test_validate_generated_quote_keeps_guide_priced_item() -> None:
    """Non-catalogue items are kept with the model's own guide price, not dropped."""
    retrieved = [
        {
            "code": "ELEC-SOCKET-ADD",
            "description": "Add a double socket",
            "unit": "each",
            "unit_price": "85.00",
        }
    ]
    generated = {
        "line_items": [
            {"code": "ELEC-SOCKET-ADD", "quantity": 1},
            {
                "description": "Consumer unit replacement (labour)",
                "kind": "labour",
                "quantity": 1,
                "unit": "job",
                "unit_price": 320.00,
                "code": None,
            },
        ],
        "notes": "",
    }

    result = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings={},
    )

    # Both lines are kept: one catalogue-grounded, one guide-priced.
    assert len(result["line_items"]) == 2
    grounded = result["line_items"][0]
    guide = result["line_items"][1]
    assert grounded["unit_price"] == Decimal("85.00")
    assert guide["description"] == "Consumer unit replacement (labour)"
    assert guide["unit_price"] == Decimal("320.00")
    # Half the lines are catalogue-grounded → 0.5 baseline + 0.5 * 0.5.
    assert result["confidence"] == 0.75


@pytest.mark.asyncio
async def test_search_cost_items_with_status_reports_grounded() -> None:
    mock_point = MagicMock()
    mock_point.payload = {"code": "ELEC-CU", "description": "Consumer unit", "unit_price": "180.00"}
    mock_point.score = 0.9
    mock_query_response = MagicMock()
    mock_query_response.points = [mock_point]
    mock_client = AsyncMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = mock_query_response

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
    ):
        generation_config.settings.openai_api_key = "sk-test"
        items, status = await search_cost_items_with_status("consumer unit")

    assert status == "grounded"
    assert len(items) == 1


@pytest.mark.asyncio
async def test_search_cost_items_with_status_reports_no_index() -> None:
    mock_query_response = MagicMock()
    mock_query_response.points = []
    mock_client = AsyncMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = mock_query_response

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
    ):
        generation_config.settings.openai_api_key = "sk-test"
        items, status = await search_cost_items_with_status("something obscure")

    assert status == "no_index"
    assert items == []


@pytest.mark.asyncio
async def test_search_cost_items_with_status_reports_weak_match() -> None:
    """Raw hits below the relevance floor still return top-3 as a fallback."""
    points = []
    for idx in range(5):
        point = MagicMock()
        point.payload = {
            "code": f"CODE-{idx}",
            "description": f"item {idx}",
            "unit_price": "1.00",
        }
        point.score = 0.20  # well below the default 0.45 floor
        points.append(point)
    mock_query_response = MagicMock()
    mock_query_response.points = points
    mock_client = AsyncMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = mock_query_response

    with (
        patch("app.rag.retrieval.embed_text", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("app.rag.retrieval.get_qdrant_client", return_value=mock_client),
    ):
        generation_config.settings.openai_api_key = "sk-test"
        items, status = await search_cost_items_with_status("partial rewire")

    assert status == "weak_match"
    assert len(items) == 3


@pytest.fixture
async def clean_cost_items() -> AsyncIterator[None]:
    """Ensure the shared cost_items table starts and ends empty per test.

    Rows committed outside the ``client`` fixture's rollback transaction
    persist across tests, so anything seeded here must be removed again.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(sa_delete(CostItem))
        await session.commit()
    _lexical_cache.clear()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(sa_delete(CostItem))
        await session.commit()
    _lexical_cache.clear()


def _no_embedding_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation_config.settings, "openai_api_key", None)
    monkeypatch.setattr(generation_config.settings, "embedding_api_key", None)


async def _insert_cost_items(rows: list[dict[str, Any]]) -> None:
    async with AsyncSessionLocal() as session:
        for row in rows:
            session.add(CostItem(**row))
        await session.commit()


def _cost_item_row(code: str, description: str, category: str, unit_price: str) -> dict[str, Any]:
    return {
        "code": code,
        "trade": "electrical",
        "region": "UK",
        "category": category,
        "description": description,
        "unit": "each",
        "unit_price": Decimal(unit_price),
        "currency": "GBP",
        "is_active": True,
        "source": "curated_seed",
        "extra_data": {"supplier": "Screwfix"},
    }


@pytest.mark.asyncio
async def test_search_cost_items_no_key_falls_back_to_lexical_no_index(
    monkeypatch: pytest.MonkeyPatch,
    clean_cost_items: None,
) -> None:
    """With no embedding key the lexical fallback runs; empty table → no_index."""
    _no_embedding_key(monkeypatch)

    items, status = await search_cost_items_with_status("add a socket")
    assert status == "no_index"
    assert items == []
    # The thin wrapper keeps returning just the items for existing callers.
    assert await search_cost_items("add a socket") == []


@pytest.mark.asyncio
async def test_lexical_fallback_returns_grounded_items(
    monkeypatch: pytest.MonkeyPatch,
    clean_cost_items: None,
) -> None:
    """No embedding key + seeded rows: 'consumer unit replacement' is grounded."""
    _no_embedding_key(monkeypatch)
    await _insert_cost_items(
        [
            _cost_item_row(
                "ELEC-CU-10W-SPD",
                "10-Way High Integrity Consumer Unit with SPD",
                "Consumer Units",
                "105.00",
            ),
            _cost_item_row(
                "ELEC-SOCK-2G",
                "13A 2-Gang Double Switched Socket White",
                "Switches & Sockets",
                "1.90",
            ),
            # Inactive rows must never be returned.
            {
                **_cost_item_row(
                    "ELEC-CU-OLD",
                    "Obsolete consumer unit (discontinued)",
                    "Consumer Units",
                    "50.00",
                ),
                "is_active": False,
            },
        ]
    )

    items, status = await search_cost_items_with_status("consumer unit replacement")

    assert status == "grounded"
    codes = [item["code"] for item in items]
    assert "ELEC-CU-10W-SPD" in codes
    assert "ELEC-CU-OLD" not in codes
    top = items[0]
    # Same dict shape as the vector path (extra keys may be None).
    for key in (
        "code",
        "description",
        "unit",
        "unit_price",
        "category",
        "source",
        "supplier",
        "brand",
        "sku",
        "product_url",
        "retail_price_incl_vat",
        "metre_length",
        "score",
    ):
        assert key in top
    # Matches the vector path, which serialises the Numeric(12, 4) payload as-is.
    assert top["unit_price"] == "105.0000"
    assert 0 < top["score"] <= 1


@pytest.mark.asyncio
async def test_lexical_fallback_ranks_best_token_match_first(
    monkeypatch: pytest.MonkeyPatch,
    clean_cost_items: None,
) -> None:
    """An RCBO item outranks a light switch for a 'consumer unit RCBO' query."""
    _no_embedding_key(monkeypatch)
    await _insert_cost_items(
        [
            _cost_item_row(
                "ELEC-SW-2G",
                "10AX 2-Gang Light Switch Unit White",
                "Switches & Sockets",
                "1.80",
            ),
            _cost_item_row(
                "ELEC-RCBO-32A-B",
                "32A Type B RCBO 30mA for Consumer Unit Boards",
                "Circuit Protection",
                "24.50",
            ),
        ]
    )

    items, status = await search_cost_items_with_status("consumer unit RCBO")

    assert status == "grounded"
    assert [item["code"] for item in items] == ["ELEC-RCBO-32A-B", "ELEC-SW-2G"]
    assert items[0]["score"] > items[1]["score"]


@pytest.mark.asyncio
async def test_lexical_fallback_db_error_reports_no_index(
    monkeypatch: pytest.MonkeyPatch,
    clean_cost_items: None,
) -> None:
    """A database failure must never break generation: log + ([], 'no_index')."""
    _no_embedding_key(monkeypatch)
    monkeypatch.setattr(
        "app.rag.retrieval.get_db_session",
        MagicMock(side_effect=ConnectionError("database unreachable")),
    )

    items, status = await search_cost_items_with_status("consumer unit replacement")

    assert status == "no_index"
    assert items == []


@pytest.mark.asyncio
async def test_seed_cost_items_idempotent_upsert_by_code(
    clean_cost_items: None,
    test_database_url: str,
) -> None:
    """The curated seed script creates rows once, then only updates them."""
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "seed_cost_items.py"
    spec = importlib.util.spec_from_file_location("seed_cost_items", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    first = await module.seed_cost_items(test_database_url)
    assert first["created"] == len(module.CURATED_ITEMS)
    assert first["updated"] == 0

    second = await module.seed_cost_items(test_database_url)
    assert second["created"] == 0
    assert second["updated"] == len(module.CURATED_ITEMS)

    codes = [item["code"] for item in module.CURATED_ITEMS]
    assert len(codes) == len(set(codes))  # codes are unique in the seed data itself
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(sa_func.count()).select_from(CostItem).where(CostItem.source == "curated_seed")
        )
    assert result.scalar_one() == len(codes)


@pytest.mark.asyncio
async def test_embed_texts_caches_embeddings() -> None:
    mock_response = MagicMock()
    mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

    _embedding_cache.clear()
    with patch(
        "app.rag.retrieval.aembedding", new=AsyncMock(return_value=mock_response)
    ) as mock_embed:
        generation_config.settings.openai_api_key = "sk-test"
        first = await embed_texts(["add a socket"])
        second = await embed_texts(["add   a  SOCKET"])

    assert first == second == [[0.1, 0.2, 0.3]]
    # Second call was served from the cache (normalised query matched).
    assert mock_embed.call_count == 1
    _embedding_cache.clear()


@pytest.mark.asyncio
async def test_generate_followup_returns_extracted_facts() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"confidence": 40, "complete": false, '
                    '"message": "Where is the consumer unit?", '
                    '"extracted": {"property_type": "semi-detached", "bedrooms": 3, '
                    '"ignored": {"nested": true}}}'
                )
            )
        )
    ]

    with patch("app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)):
        generation_config.settings.openai_api_key = "sk-test"
        result = await generate_followup("Consumer unit replacement", [])

    assert result["confidence"] == 40
    assert result["complete"] is False
    assert result["message"] == "Where is the consumer unit?"
    # Only flat str→str scalar facts survive sanitisation.
    assert result["extracted"] == {"property_type": "semi-detached", "bedrooms": "3"}


@pytest.mark.asyncio
async def test_generate_followup_defaults_extracted_to_empty() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"confidence": 30, "message": "More info?"}'))
    ]

    with patch("app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)):
        generation_config.settings.openai_api_key = "sk-test"
        result = await generate_followup("Socket install", [])

    assert result["extracted"] == {}
    assert result["options"] == []
    assert result["suggested_questions"] == []


@pytest.mark.asyncio
async def test_generate_followup_sanitizes_options_and_suggested_questions() -> None:
    """Options/suggested_questions are strings-only, capped in count and length."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"confidence": 45, "complete": false, "message": "Where is it?", '
                    '"options": ["Under the stairs", 42, "'
                    + "x"
                    * 100
                    + '", "In the garage", "Not sure", "One too many"], '
                    '"suggested_questions": ["How old is the wiring?", {"bad": true}, '
                    '"  ", "Second question", "Third question", "Fourth question"]}'
                )
            )
        )
    ]

    with patch("app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)):
        generation_config.settings.openai_api_key = "sk-test"
        result = await generate_followup("Consumer unit replacement", [])

    assert result["options"] == ["Under the stairs", "x" * 60, "In the garage", "Not sure"]
    assert result["suggested_questions"] == [
        "How old is the wiring?",
        "Second question",
        "Third question",
    ]


@pytest.mark.asyncio
async def test_generate_followup_final_turn_adds_suggested_questions_hint() -> None:
    """The final-turn flag tells the model to close with suggested_questions."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"confidence": 40, "message": "Last one?"}'))
    ]

    with patch(
        "app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)
    ) as mock_acompletion:
        generation_config.settings.openai_api_key = "sk-test"
        await generate_followup("Fuse board replacement", [], final_turn=True)

    messages = mock_acompletion.call_args.kwargs["messages"]
    final_user = messages[-1]
    assert final_user["role"] == "user"
    assert "LAST question" in final_user["content"]
    assert "suggested_questions" in final_user["content"]


@pytest.mark.asyncio
async def test_generate_followup_sends_alternating_role_turns() -> None:
    """Prior chat history is fed as alternating user/assistant turns, not a
    flat prose block. Matches Kimi's multi-turn convention so prompt-prefix
    caching kicks in across follow-up calls."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"confidence": 60, "message": "Next?"}'))
    ]
    prior = [
        {"role": "ai", "text": "Where is the consumer unit?"},
        {"role": "customer", "text": "Under the stairs."},
        {"role": "ai", "text": "How many circuits do you count?"},
        {"role": "customer", "text": "Ten."},
    ]

    with patch(
        "app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)
    ) as mock_acompletion:
        generation_config.settings.openai_api_key = "sk-test"
        await generate_followup("Consumer unit replacement", prior)

    messages = mock_acompletion.call_args.kwargs["messages"]
    roles = [m["role"] for m in messages]
    assert roles[0] == "system"
    assert roles[1] == "user"  # summary anchor
    assert "Quote request summary" in messages[1]["content"]
    assert roles[2:] == ["assistant", "user", "assistant", "user"]
    assert messages[2]["content"] == "Where is the consumer unit?"
    assert messages[3]["content"] == "Under the stairs."


@pytest.mark.asyncio
async def test_generate_followup_truncates_and_warns_on_long_history(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Threads longer than the cap are tail-truncated and a warning is logged."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"confidence": 60, "message": "Next?"}'))
    ]
    # 30 alternating messages > the 20-message internal cap.
    prior = [{"role": "ai" if i % 2 == 0 else "customer", "text": f"msg {i}"} for i in range(30)]

    with patch(
        "app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)
    ) as mock_acompletion:
        generation_config.settings.openai_api_key = "sk-test"
        await generate_followup("Consumer unit replacement", prior)

    messages = mock_acompletion.call_args.kwargs["messages"]
    # system + summary + 20 history messages = 22 total (no final-turn hint).
    assert len(messages) == 22
    # Most recent messages are kept; earliest are dropped.
    assert messages[-1]["content"] == "msg 29"
    assert messages[2]["content"] == "msg 10"


def test_followup_system_prompt_foregrounds_stated_problem() -> None:
    """The v2 triage prompt requires acknowledging the customer's problem first
    and offering non-engineer quick-reply options."""
    assert "Customer's stated problem" in FOLLOWUP_SYSTEM_PROMPT
    assert "BEFORE asking anything" in FOLLOWUP_SYSTEM_PROMPT
    assert "non-engineer" in FOLLOWUP_SYSTEM_PROMPT
    assert '"options"' in FOLLOWUP_SYSTEM_PROMPT
    assert '"suggested_questions"' in FOLLOWUP_SYSTEM_PROMPT


def test_validate_generated_quote_clamps_out_of_range_prices() -> None:
    generated = {
        "line_items": [
            {
                "description": "Labour (hourly)",
                "kind": "labour",
                "unit": "hour",
                "quantity": 1,
                "unit_price": 5,
            },
            {
                "description": "Gold-plated socket",
                "kind": "material",
                "unit": "each",
                "quantity": 1,
                "unit_price": 99999,
            },
        ],
        "notes": "",
    }

    result = validate_generated_quote(generated=generated, retrieved_items=[], tenant_settings={})

    assert result["line_items"][0]["unit_price"] == Decimal("25")
    assert result["line_items"][1]["unit_price"] == Decimal("5000")
    assert any("adjusted from £5 to £25" in w for w in result["warnings"])
    assert any("adjusted from £99999 to £5000" in w for w in result["warnings"])
    # The kind field is propagated into the validated line dicts.
    assert result["line_items"][0]["kind"] == "labour"
    assert result["line_items"][1]["kind"] == "material"


def test_validate_generated_quote_warns_on_zero_quantity_and_price() -> None:
    generated = {
        "line_items": [{"description": "Freebie", "quantity": 0, "unit_price": 0}],
        "notes": "",
    }

    result = validate_generated_quote(generated=generated, retrieved_items=[], tenant_settings={})

    assert len(result["line_items"]) == 1
    assert any("Zero quantity" in w for w in result["warnings"])
    assert any("Zero unit price" in w for w in result["warnings"])


def test_validate_generated_quote_adds_minimum_charge_adjustment() -> None:
    generated = {
        "line_items": [
            {
                "description": "Quick fault fix",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 60,
            }
        ],
        "notes": "",
    }

    result = validate_generated_quote(
        generated=generated,
        retrieved_items=[],
        tenant_settings={"minimum_charge": "100"},
    )

    assert len(result["line_items"]) == 2
    adjustment = result["line_items"][1]
    assert adjustment["description"] == "Minimum charge adjustment"
    assert adjustment["quantity"] == Decimal("1")
    assert adjustment["unit_price"] == Decimal("40")
    assert any("minimum charge" in w for w in result["warnings"])


def test_validate_generated_quote_no_adjustment_when_above_minimum() -> None:
    generated = {
        "line_items": [
            {
                "description": "Consumer unit swap",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 500,
            }
        ],
        "notes": "",
    }

    result = validate_generated_quote(
        generated=generated,
        retrieved_items=[],
        tenant_settings={"minimum_charge": "100"},
    )

    assert len(result["line_items"]) == 1
    assert not result["warnings"]


@pytest.mark.asyncio
async def test_generate_quote_omits_temperature_for_kimi_k_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kimi-k* models 400 on any temperature other than the default, so the
    configured temperature must be omitted for them and kept for others."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"line_items": [], "notes": ""}'))
    ]

    monkeypatch.setattr(generation_config.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(generation_config.settings, "llm_temperature", 0.2)

    with patch(
        "app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)
    ) as mock_acompletion:
        monkeypatch.setattr(generation_config.settings, "llm_model", "openai/kimi-k2.6")
        await generate_quote_from_prompt("rewire a house", [], {}, knowledge_chunks=[])
        assert "temperature" not in mock_acompletion.call_args.kwargs

        monkeypatch.setattr(generation_config.settings, "llm_model", "gpt-4o-mini")
        await generate_quote_from_prompt("rewire a house", [], {}, knowledge_chunks=[])
        assert mock_acompletion.call_args.kwargs["temperature"] == 0.2


def test_validate_generated_quote_confidence_with_completeness() -> None:
    """Confidence 2.0: 0.3 + 0.3 * grounded_ratio + 0.4 * completeness."""
    retrieved = [
        {
            "code": "ELEC-SOCKET-ADD",
            "description": "Install one additional double socket",
            "unit": "each",
            "unit_price": "85.00",
        }
    ]
    generated = {
        "line_items": [
            {"code": "ELEC-SOCKET-ADD", "quantity": 2},
            {
                "description": "Consumer unit replacement (labour)",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 320.00,
            },
        ],
        "notes": "",
    }

    # Half grounded (ratio 0.5), complete intake → 0.3 + 0.15 + 0.4 = 0.85.
    result = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings={},
        completeness=1.0,
    )
    assert result["confidence"] == 0.85

    # Same grounding, sparse intake → 0.3 + 0.15 + 0.1 = 0.55.
    result = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings={},
        completeness=0.25,
    )
    assert result["confidence"] == 0.55

    # Fully grounded + rich intake saturates at 1.0.
    fully_grounded = {"line_items": [{"code": "ELEC-SOCKET-ADD", "quantity": 1}], "notes": ""}
    result = validate_generated_quote(
        generated=fully_grounded,
        retrieved_items=retrieved,
        tenant_settings={},
        completeness=1.0,
    )
    assert result["confidence"] == 1.0


def test_validate_generated_quote_confidence_legacy_without_completeness() -> None:
    """Without a completeness score the legacy 0.5 + 0.5 * ratio formula holds."""
    retrieved = [
        {
            "code": "ELEC-SOCKET-ADD",
            "description": "Install one additional double socket",
            "unit": "each",
            "unit_price": "85.00",
        }
    ]
    generated = {
        "line_items": [
            {"code": "ELEC-SOCKET-ADD", "quantity": 2},
            {
                "description": "Consumer unit replacement (labour)",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 320.00,
            },
        ],
        "notes": "",
    }
    result = validate_generated_quote(
        generated=generated, retrieved_items=retrieved, tenant_settings={}
    )
    assert result["confidence"] == 0.75


def test_compute_retrieval_quality_flags_thin_retrieval() -> None:
    """Below-threshold citations or relevance flip ``passes_gates`` to False."""
    from app.rag.retrieval import compute_retrieval_quality

    generation_config.settings.retrieval_quality_min_citations = 2
    generation_config.settings.retrieval_quality_min_top_relevance = 0.5

    # Empty retrieval: fails both citation and relevance gates.
    empty = compute_retrieval_quality([])
    assert empty["citations"] == 0
    assert empty["top_relevance"] == 0.0
    assert empty["passes_min_citations"] is False
    assert empty["passes_min_relevance"] is False
    assert empty["passes_gates"] is False

    # Enough items and a strong top score: passes.
    strong = compute_retrieval_quality(
        [
            {"code": "A", "score": 0.62},
            {"code": "B", "score": 0.55},
        ]
    )
    assert strong["top_relevance"] == 0.62
    assert strong["citations"] == 2
    assert strong["passes_gates"] is True

    # Sufficient count but weak relevance still fails.
    weak = compute_retrieval_quality(
        [
            {"code": "A", "score": 0.30},
            {"code": "B", "score": 0.32},
        ]
    )
    assert weak["passes_min_citations"] is True
    assert weak["passes_min_relevance"] is False
    assert weak["passes_gates"] is False

    # Restore defaults for later tests in the same module.
    generation_config.settings.retrieval_quality_min_citations = 1
    generation_config.settings.retrieval_quality_min_top_relevance = 0.45


def test_validate_caps_confidence_when_retrieval_quality_fails() -> None:
    """Failing gates cap confidence and add a warning; passing gates leave it alone."""
    generated = {
        "line_items": [
            {"code": "ELEC-SOCKET-ADD", "quantity": 2},
            {
                "description": "Consumer unit replacement (labour)",
                "kind": "labour",
                "unit": "job",
                "quantity": 1,
                "unit_price": 320.00,
            },
        ],
        "notes": "",
    }
    retrieved = [
        {
            "code": "ELEC-SOCKET-ADD",
            "description": "Install one additional double socket",
            "unit": "each",
            "unit_price": "85.00",
        }
    ]
    quality_fail = {
        "top_relevance": 0.32,
        "citations": 1,
        "passes_min_citations": False,
        "passes_min_relevance": False,
        "passes_knowledge_requirement": True,
        "passes_gates": False,
        "fallback_policy": "warn_only",
        "confidence_cap": 0.6,
    }
    result = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings={},
        retrieval_quality=quality_fail,
    )
    assert result["confidence"] == 0.6
    assert result["confidence_capped"] is True
    assert any("Confidence capped" in w for w in result["warnings"])

    quality_pass = {**quality_fail, "passes_gates": True}
    result = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings={},
        retrieval_quality=quality_pass,
    )
    # No cap: legacy 0.5 + 0.5 * grounded_ratio; 1 of 2 lines grounded = 0.75.
    assert result["confidence"] == 0.75
    assert result["confidence_capped"] is False


def test_auto_ground_attaches_matching_catalogue_code() -> None:
    """Material lines Kimi left ungrounded get force-grounded via fuzzy match."""
    generated = {
        "line_items": [
            # LLM cited a real code — grounded directly.
            {
                "code": "ELEC-SOCKET-ADD",
                "description": "13A double socket",
                "kind": "material",
                "quantity": 2,
            },
            # LLM did NOT cite, but the description clearly matches a retrieved item.
            {
                "code": None,
                "description": "6242Y twin & earth cable 2.5mm² 50m",
                "kind": "material",
                "quantity": 50,
                "unit_price": 4.20,
                "unit": "m",
            },
            # Labour line — auto-ground never touches labour.
            {
                "description": "Install and terminate cable",
                "kind": "labour",
                "quantity": 4,
                "unit_price": 65.00,
                "unit": "hour",
            },
        ],
        "notes": "",
    }
    retrieved: list[dict[str, Any]] = [
        {
            "code": "ELEC-SOCKET-ADD",
            "description": "Install one additional double socket",
            "unit": "each",
            "unit_price": "85.00",
        },
        {
            "code": "DOM-screwfix-20967",
            "description": "[Cable] Prysmian 6242Y Twin & Earth Cable 2.5mm 50m drum cable_type=twin_earth",
            "unit": "m",
            "unit_price": "0.77",
            "score": 0.62,
        },
    ]
    result = validate_generated_quote(
        generated=generated, retrieved_items=retrieved, tenant_settings={}
    )

    assert result["auto_grounded"] == 1
    assert result["line_items"][0]["code"] == "ELEC-SOCKET-ADD"
    # Auto-grounded: code attached, price swapped in from catalogue.
    assert result["line_items"][1]["code"] == "DOM-screwfix-20967"
    assert result["line_items"][1]["unit_price"] == Decimal("0.77")
    # Labour line untouched by auto-grounding.
    assert result["line_items"][2]["code"] is None


def test_auto_ground_does_not_match_unrelated_lines() -> None:
    """Below-threshold token overlap leaves the line as guide-priced."""
    generated = {
        "line_items": [
            {
                "code": None,
                "description": "Consumer unit swap (labour and materials)",
                "kind": "material",
                "quantity": 1,
                "unit_price": 320.00,
                "unit": "job",
            }
        ],
        "notes": "",
    }
    retrieved = [
        {
            "code": "DOM-screwfix-99999",
            "description": "[Lighting] Aurora GU10 4W Cool White Downlight Chrome IP44",
            "unit": "each",
            "unit_price": "3.50",
            "score": 0.31,
        }
    ]
    result = validate_generated_quote(
        generated=generated, retrieved_items=retrieved, tenant_settings={}
    )

    assert result["auto_grounded"] == 0
    assert result["line_items"][0]["code"] is None
    # Guide price preserved unchanged.
    assert result["line_items"][0]["unit_price"] == Decimal("320.00")


def test_labour_snapped_to_tenant_hourly_rate() -> None:
    """Hourly labour lines are anchored to the tenant's configured rate."""
    generated = {
        "line_items": [
            {
                "code": None,
                "description": "Install and interconnect three mains alarms",
                "kind": "labour",
                "quantity": 5,
                "unit_price": 80.00,
                "unit": "hour",
            },
            {
                "code": None,
                "description": "Materials allowance",
                "kind": "material",
                "quantity": 1,
                "unit_price": 25.00,
                "unit": "each",
            },
        ],
        "notes": "",
    }
    result = validate_generated_quote(
        generated=generated,
        retrieved_items=[],
        tenant_settings={"hourly_labour_rate": "65.00"},
    )

    labour_line = result["line_items"][0]
    material_line = result["line_items"][1]
    assert result["labour_snapped"] == 1
    assert labour_line["unit_price"] == Decimal("65.00")
    # Material lines are unaffected by the labour-rate snap.
    assert material_line["unit_price"] == Decimal("25.00")


def test_labour_snap_skipped_without_tenant_rate() -> None:
    """When the tenant has no configured hourly rate, the LLM price stands."""
    generated = {
        "line_items": [
            {
                "code": None,
                "description": "Test and commission",
                "kind": "labour",
                "quantity": 2,
                "unit_price": 70.00,
                "unit": "hour",
            }
        ],
        "notes": "",
    }
    result = validate_generated_quote(generated=generated, retrieved_items=[], tenant_settings={})

    assert result["labour_snapped"] == 0
    assert result["line_items"][0]["unit_price"] == Decimal("70.00")


def test_labour_snap_skips_per_job_lines() -> None:
    """Fixed per-job labour lines keep the LLM price (only hourly is snapped)."""
    generated = {
        "line_items": [
            {
                "code": None,
                "description": "EICR (fixed price)",
                "kind": "labour",
                "quantity": 1,
                "unit_price": 180.00,
                "unit": "job",
            }
        ],
        "notes": "",
    }
    result = validate_generated_quote(
        generated=generated,
        retrieved_items=[],
        tenant_settings={"hourly_labour_rate": "65.00"},
    )

    assert result["labour_snapped"] == 0
    assert result["line_items"][0]["unit_price"] == Decimal("180.00")


def test_intake_completeness_signal_scoring() -> None:
    """_intake_completeness uses weighted signals so AI-chat extraction lifts confidence."""
    from app.routers.quotes import _INTAKE_WEIGHTS, _intake_completeness

    # Only a real description: description weight only.
    assert _intake_completeness("Replace the consumer unit") == round(
        _INTAKE_WEIGHTS["description"], 2
    )
    # Nothing usable at all.
    assert _intake_completeness("short") == 0.0

    # Every signal maxed out.
    fully_populated = QuoteRequest(
        tenant_id=uuid4(),
        source="web_form",
        raw_text="Fuse board keeps tripping",
        urgency="this_week",
        structured_data={
            "property": {"type": "semi-detached", "bedrooms": 3},
            "questionnaire": {"consumer_unit_location": "under the stairs"},
            "ai_extracted": {
                "parking": "driveway",
                "location": "kitchen",
                "quantity": "3",
                "existing_setup": "double sockets",
                "symptoms": "trips at night",
            },
        },
    )
    assert _intake_completeness("Fuse board keeps tripping", quote_request=fully_populated) == 1.0

    # Lead form only (no AI chat): description + property_type + bedrooms + urgency.
    sparse_request = QuoteRequest(
        tenant_id=uuid4(),
        source="web_form",
        raw_text="Fuse board keeps tripping",
        urgency="flexible",
        structured_data={"property": {"type": "flat", "bedrooms": 1}},
    )
    expected_sparse = (
        _INTAKE_WEIGHTS["description"]
        + _INTAKE_WEIGHTS["property_type"]
        + _INTAKE_WEIGHTS["bedrooms"]
        + _INTAKE_WEIGHTS["urgency"]
    )
    assert _intake_completeness("Fuse board keeps tripping", quote_request=sparse_request) == round(
        expected_sparse, 2
    )


def test_intake_completeness_ai_chat_meaningfully_raises_score() -> None:
    """Adding a rich AI-chat extraction should raise completeness by 0.4+."""
    from app.routers.quotes import _intake_completeness

    baseline_request = QuoteRequest(
        tenant_id=uuid4(),
        source="web_form",
        raw_text="Add two double sockets in the living room",
        urgency="this_week",
        structured_data={},
    )
    baseline = _intake_completeness("Add two double sockets", quote_request=baseline_request)

    enriched_request = QuoteRequest(
        tenant_id=uuid4(),
        source="web_form",
        raw_text="Add two double sockets in the living room",
        urgency="this_week",
        structured_data={
            "ai_extracted": {
                "property_type": "semi-detached",
                "bedrooms": "3",
                "consumer_unit_location": "under the stairs",
                "location": "living room and bedroom",
                "quantity": "3 double sockets",
                "existing_setup": "surface skirting trunking",
                "preference": "brushed brass",
            },
        },
    )
    enriched = _intake_completeness("Add two double sockets", quote_request=enriched_request)

    lift = enriched - baseline
    assert lift >= 0.4, (
        f"AI chat extraction should lift completeness by >= 0.4 (got {lift:.2f}); "
        f"baseline={baseline}, enriched={enriched}"
    )
    assert enriched >= 0.85
