"""Tests for the RAG Quote Engine modules."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app import config as generation_config
from app.rag.generation import SYSTEM_PROMPT, generate_quote_from_prompt
from app.rag.retrieval import search_cost_items
from app.rag.validation import validate_generated_quote


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
        results = await search_cost_items("add a socket")

    assert len(results) == 1
    assert results[0]["code"] == "ELEC-SOCKET-ADD"
    assert results[0]["score"] == 0.95


@pytest.mark.asyncio
async def test_generate_quote_from_prompt() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"line_items": [{"code": "ELEC-SOCKET-ADD", "quantity": 2, "reason": "two sockets"}], "notes": ""}'))
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
        )

    assert result["line_items"][0]["code"] == "ELEC-SOCKET-ADD"
    assert result["line_items"][0]["quantity"] == 2


@pytest.mark.asyncio
async def test_generate_quote_from_prompt_includes_system_prompt() -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"line_items": [], "notes": ""}'))]

    with patch("app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)) as mock_acompletion:
        generation_config.settings.openai_api_key = "sk-test"
        await generate_quote_from_prompt(
            job_description="rewire a house",
            cost_items=[],
            tenant_settings={},
        )

    assert mock_acompletion.call_args is not None
    messages = mock_acompletion.call_args.kwargs.get("messages")
    assert messages is not None
    assert messages[0]["role"] == "system"
    assert SYSTEM_PROMPT in messages[0]["content"]


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
        "line_items": [
            {"code": "ELEC-SOCKET-ADD", "quantity": 2, "reason": "kitchen and bedroom"}
        ],
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


def test_validate_generated_quote_warns_on_unknown_code() -> None:
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
            {"code": "UNKNOWN", "quantity": 1},
        ],
        "notes": "",
    }

    result = validate_generated_quote(
        generated=generated,
        retrieved_items=retrieved,
        tenant_settings={},
    )

    assert len(result["line_items"]) == 1
    assert result["confidence"] == 0.5
    assert any("UNKNOWN" in w for w in result["warnings"])
