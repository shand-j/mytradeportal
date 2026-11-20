"""Mechanical triage completeness guard (circuit count on board jobs).

Self-reported model confidence must not close a consumer-unit / fuse-board
conversation while the circuit count is unknown — the quote engine prices
RCBO work per circuit. These tests run the REAL generate_followup with only
the LiteLLM call mocked.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.rag import generation

_JOB = (
    "Customer's stated problem: replace the old fuse box with a modern RCBO "
    "board in a 3-bed detached house (consumer_unit)."
)
_CLOSURE = "Thank you for the details. The electrician will review your request."


def _llm_response(payload: dict[str, Any]) -> SimpleNamespace:
    import json

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload)),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=50, completion_tokens=25, prompt_tokens_details=None),
    )


def _patch_llm(payload: dict[str, Any]) -> Any:
    return (
        patch.object(
            generation,
            "_resolve_followup_route",
            return_value=("gpt-4o-mini", "test-key", None),
        ),
        patch.object(generation, "acompletion", new=AsyncMock(return_value=_llm_response(payload))),
    )


async def _call(payload: dict[str, Any], job: str = _JOB, **kwargs: Any) -> dict[str, Any]:
    route_patch, llm_patch = _patch_llm(payload)
    with route_patch, llm_patch:
        return await generation.generate_followup(job, [], **kwargs)


@pytest.mark.asyncio
async def test_confident_closure_without_circuit_count_is_downgraded() -> None:
    result = await _call({"confidence": 85, "complete": True, "message": _CLOSURE})
    assert result["complete"] is False
    assert result["confidence"] == 79
    assert "circuits" in result["message"]
    assert result["message"] == generation._CIRCUIT_QUESTION


@pytest.mark.asyncio
async def test_models_own_circuit_question_is_preserved() -> None:
    question = "How many circuits are on your fuse box?"
    result = await _call({"confidence": 60, "complete": False, "message": question})
    assert result["complete"] is False
    assert result["message"] == question


@pytest.mark.asyncio
async def test_circuit_count_in_request_allows_closure() -> None:
    result = await _call(
        {"confidence": 85, "complete": True, "message": _CLOSURE},
        job=_JOB + " The board has 8 circuits.",
    )
    assert result["complete"] is True
    assert result["confidence"] == 85


@pytest.mark.asyncio
async def test_circuit_count_in_prior_reply_allows_closure() -> None:
    route_patch, llm_patch = _patch_llm({"confidence": 90, "complete": True, "message": _CLOSURE})
    with route_patch, llm_patch:
        result = await generation.generate_followup(
            _JOB,
            [{"role": "user", "content": "It has 8 circuits including the main switch."}],
        )
    assert result["complete"] is True


@pytest.mark.asyncio
async def test_extracted_circuit_fact_allows_closure() -> None:
    result = await _call(
        {
            "confidence": 85,
            "complete": True,
            "message": _CLOSURE,
            "extracted": {"circuit_count": "8"},
        }
    )
    assert result["complete"] is True


@pytest.mark.asyncio
async def test_final_turn_always_closes() -> None:
    result = await _call({"confidence": 85, "complete": True, "message": _CLOSURE}, final_turn=True)
    assert result["complete"] is True
    assert result["message"] == _CLOSURE


@pytest.mark.asyncio
async def test_non_circuit_job_unaffected() -> None:
    result = await _call(
        {"confidence": 85, "complete": True, "message": _CLOSURE},
        job="Install two double sockets in the bedroom.",
    )
    assert result["complete"] is True
