"""API service configuration."""

from mtp_shared import get_settings

settings = get_settings()

# Estimated LLM list prices (USD per 1K tokens) used only for internal AI
# spend attribution on quotes — never for customer billing. Keys are matched
# as substrings of the configured model id (e.g. "openai/kimi-k2.6" matches
# "kimi-k2.6"). Models missing from the map still record token counts, with
# est_cost_usd=None.
LLM_COST_PER_1K_TOKENS_USD: dict[str, dict[str, float]] = {
    # Moonshot Kimi K2.6 list-price estimate (prompt / completion per 1K tokens).
    "kimi-k2.6": {"prompt": 0.0006, "completion": 0.0025},
}
