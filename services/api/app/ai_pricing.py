"""Date-versioned AI price lists for internal spend attribution.

Replaces the single flat ``LLM_COST_PER_1K_TOKENS_USD`` map that used to live
in ``app.config``. Prices are **USD per 1K tokens**, list-price estimates used
only for internal cost attribution on AI calls — never for customer billing.

Each model maps to a list of ``(effective_from, input_per_1k, output_per_1k,
cached_input_per_1k)`` entries so a price change is recorded additively and
historical events can be re-costed at their own date (the backfill script and
the reconcile job rely on this). Keys are matched as substrings of the model
id (e.g. ``openai/kimi-k2.6`` matches ``kimi-k2.6``), same as the old map.
Models missing from the list still record token counts, with
``est_cost_usd=None``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# (effective_from, input_per_1k, output_per_1k, cached_input_per_1k).
# ``cached_input_per_1k=None`` means the provider has no separate cached rate —
# cached tokens are then billed at the plain input rate.
PriceEntry = tuple[date, Decimal, Decimal, Decimal | None]

PRICE_LISTS: dict[str, list[PriceEntry]] = {
    # Moonshot Kimi K2.6 (list-price estimates).
    "kimi-k2.6": [
        (date(2025, 1, 1), Decimal("0.0008"), Decimal("0.0030"), None),
        (date(2025, 9, 1), Decimal("0.0006"), Decimal("0.0025"), None),
    ],
    # OpenAI gpt-4o-mini (public list prices; cached input at half price).
    "gpt-4o-mini": [
        (date(2024, 7, 18), Decimal("0.00015"), Decimal("0.0006"), Decimal("0.000075")),
    ],
    # OpenAI text-embedding-3-large (input only; embeddings have no output).
    "text-embedding-3-large": [
        (date(2024, 1, 25), Decimal("0.00013"), Decimal("0"), None),
    ],
}

_USD_QUANTUM = Decimal("0.000001")


def _match_price_list(model: str) -> list[PriceEntry] | None:
    """Return the price entries whose key appears in the model id, if any."""
    lowered = model.lower()
    return next(
        (entries for key, entries in PRICE_LISTS.items() if key in lowered),
        None,
    )


def _entry_at(entries: list[PriceEntry], at_date: date) -> PriceEntry:
    """Pick the entry in force on ``at_date`` (latest ``effective_from`` ≤ it).

    Dates before the earliest known entry fall back to that earliest entry so
    historical backfills still get a number rather than ``None``.
    """
    applicable = [entry for entry in entries if entry[0] <= at_date]
    if not applicable:
        return min(entries, key=lambda entry: entry[0])
    return max(applicable, key=lambda entry: entry[0])


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    at_date: date | None = None,
) -> Decimal | None:
    """Estimate the USD cost of one AI call from the date-versioned price list.

    ``input_tokens`` must EXCLUDE cached input tokens — pass those separately
    via ``cached_input_tokens`` so they are billed at the (cheaper) cached
    rate when the model has one. Returns ``None`` when the model is not in any
    price list; the caller still records the token counts.
    """
    entries = _match_price_list(model)
    if entries is None:
        return None
    _, input_per_1k, output_per_1k, cached_per_1k = _entry_at(entries, at_date or date.today())
    cached_rate = cached_per_1k if cached_per_1k is not None else input_per_1k
    cost = (
        Decimal(input_tokens) * input_per_1k
        + Decimal(output_tokens) * output_per_1k
        + Decimal(cached_input_tokens) * cached_rate
    ) / 1000
    return cost.quantize(_USD_QUANTUM)
