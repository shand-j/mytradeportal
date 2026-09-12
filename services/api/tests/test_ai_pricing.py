"""Unit tests for the date-versioned AI price lists (no DB required)."""

from datetime import date
from decimal import Decimal

from app.ai_pricing import estimate_cost
from app.rag.generation import estimate_llm_cost_usd


def test_kimi_price_is_date_versioned() -> None:
    """Entries before/after the 2025-09-01 price change resolve differently."""
    old = estimate_cost("openai/kimi-k2.6", 1000, 1000, at_date=date(2025, 3, 1))
    new = estimate_cost("openai/kimi-k2.6", 1000, 1000, at_date=date(2026, 1, 1))
    assert old == Decimal("0.003800")  # 0.0008 + 0.0030 per 1k
    assert new == Decimal("0.003100")  # 0.0006 + 0.0025 per 1k


def test_model_key_matches_as_substring() -> None:
    """Provider-prefixed ids (openai/kimi-k2.6) match the bare key."""
    assert estimate_cost("openai/kimi-k2.6", 1000, 0, at_date=date(2026, 1, 1)) == Decimal(
        "0.000600"
    )


def test_gpt_4o_mini_with_cached_input_tokens() -> None:
    """Cached input tokens bill at the cheaper cached rate, separately."""
    cost = estimate_cost("gpt-4o-mini", 1000, 1000, 500, at_date=date(2026, 1, 1))
    # (1000 * 0.00015 + 1000 * 0.0006 + 500 * 0.000075) / 1000
    assert cost == Decimal("0.000788")


def test_model_without_cached_rate_bills_cached_at_input_rate() -> None:
    """kimi-k2.6 has no cached price — cached tokens fall back to input rate."""
    cost = estimate_cost("kimi-k2.6", 1000, 0, 500, at_date=date(2026, 1, 1))
    # (1000 * 0.0006 + 500 * 0.0006) / 1000
    assert cost == Decimal("0.000900")


def test_embedding_model_input_only() -> None:
    assert estimate_cost("text-embedding-3-large", 2000, 0) == Decimal("0.000260")


def test_unknown_model_returns_none() -> None:
    assert estimate_cost("claude-3-opus", 1000, 1000) is None


def test_date_before_earliest_entry_uses_earliest_entry() -> None:
    cost = estimate_cost("kimi-k2.6", 1000, 0, at_date=date(2020, 1, 1))
    assert cost == Decimal("0.000800")


def test_estimate_llm_cost_usd_delegates_and_keeps_signature() -> None:
    """Backwards-compatible wrapper: float in, None for unknown models."""
    assert estimate_llm_cost_usd("openai/kimi-k2.6", 1000, 1000) == 0.0031
    assert estimate_llm_cost_usd("unknown-model", 1000, 1000) is None
