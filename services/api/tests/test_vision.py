"""Tests for the photo-observation (vision captioning) step."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app import config as generation_config
from app.rag.generation import _build_user_prompt, generate_quote_from_prompt
from app.rag.vision import ImageRef, build_data_url, caption_images
from app.schemas import QuoteRead


def _mock_vision_response(content: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


def test_build_data_url_inlines_bytes() -> None:
    data_url = build_data_url(b"\xff\xd8\xff", "image/jpeg")
    assert data_url is not None
    assert data_url.startswith("data:image/jpeg;base64,")


def test_build_data_url_rejects_empty_and_oversized() -> None:
    assert build_data_url(b"", "image/jpeg") is None
    assert build_data_url(b"x" * (8 * 1024 * 1024 + 1), "image/jpeg") is None


@pytest.mark.asyncio
async def test_caption_images_sends_photo_to_vision_model() -> None:
    mock_response = _mock_vision_response(
        "The photo shows an old consumer unit with rewireable fuses and no RCD protection."
    )
    with patch("app.rag.vision.acompletion", new=AsyncMock(return_value=mock_response)) as call:
        generation_config.settings.llm_api_key = ""
        generation_config.settings.openai_api_key = "sk-test"
        observations = await caption_images(
            [ImageRef(url="https://example.com/photos/consumer-unit.jpg")]
        )

    assert observations == [
        "The photo shows an old consumer unit with rewireable fuses and no RCD protection."
    ]
    kwargs = call.call_args.kwargs
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/photos/consumer-unit.jpg"},
    }


@pytest.mark.asyncio
async def test_caption_images_fail_open_on_provider_error() -> None:
    with patch("app.rag.vision.acompletion", new=AsyncMock(side_effect=RuntimeError("down"))):
        generation_config.settings.openai_api_key = "sk-test"
        observations = await caption_images([ImageRef(url="https://example.com/photo.jpg")])

    assert observations == []


@pytest.mark.asyncio
async def test_caption_images_without_api_key_returns_empty() -> None:
    generation_config.settings.llm_api_key = ""
    generation_config.settings.openai_api_key = ""
    try:
        observations = await caption_images([ImageRef(url="https://example.com/photo.jpg")])
    finally:
        generation_config.settings.openai_api_key = "sk-test"
    assert observations == []


def test_build_user_prompt_renders_image_observations() -> None:
    prompt = _build_user_prompt(
        "Replace the consumer unit",
        None,
        [],
        {},
        image_observations=["The photo shows a rewireable-fuse consumer unit."],
    )
    assert "Observations from customer photos" in prompt
    assert "- The photo shows a rewireable-fuse consumer unit." in prompt


def test_build_user_prompt_omits_observations_section_when_none() -> None:
    prompt = _build_user_prompt("Replace the consumer unit", None, [], {})
    assert "Observations from customer photos" not in prompt


@pytest.mark.asyncio
async def test_generate_quote_from_prompt_conditions_on_image_observations() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"line_items": [], "notes": ""}'))
    ]

    with patch("app.rag.generation.acompletion", new=AsyncMock(return_value=mock_response)) as call:
        generation_config.settings.openai_api_key = "sk-test"
        await generate_quote_from_prompt(
            job_description="Fuse board keeps tripping",
            cost_items=[],
            tenant_settings={},
            knowledge_chunks=[],
            image_observations=["The photo shows a rewireable-fuse consumer unit."],
        )

    user_prompt = call.call_args.kwargs["messages"][1]["content"]
    assert "Observations from customer photos" in user_prompt
    assert "rewireable-fuse consumer unit" in user_prompt


def _quote_payload(extra_data: dict[str, Any]) -> dict[str, Any]:
    tenant_id = uuid4()
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "contact_id": uuid4(),
        "title": "Consumer unit upgrade",
        "description": None,
        "status": "draft",
        "subtotal": "100.00",
        "vat_rate": "0.20",
        "vat_amount": "20.00",
        "total": "120.00",
        "valid_until": None,
        "approved_at": None,
        "sent_at": None,
        "line_items": [],
        "bill_of_quantities": None,
        "quote_request_id": None,
        "created_at": datetime(2026, 9, 18, 10, 0, 0),
        "updated_at": datetime(2026, 9, 18, 10, 0, 0),
        "contact": {
            "id": uuid4(),
            "tenant_id": tenant_id,
            "name": "Lead Owner",
            "email": None,
            "phone": None,
            "address": None,
            "postcode": None,
            "notes": None,
            "created_at": datetime(2026, 9, 18, 10, 0, 0),
            "updated_at": datetime(2026, 9, 18, 10, 0, 0),
        },
        "extra_data": extra_data,
    }


def test_quote_read_exposes_ai_observations() -> None:
    quote = QuoteRead.model_validate(
        _quote_payload(
            {"rag": {"observations": ["The photo shows a rewireable-fuse consumer unit."]}}
        )
    )
    assert quote.ai_observations == ["The photo shows a rewireable-fuse consumer unit."]


def test_quote_read_ai_observations_default_empty() -> None:
    quote = QuoteRead.model_validate(_quote_payload({"rag": {"confidence": 0.5}}))
    assert quote.ai_observations == []
