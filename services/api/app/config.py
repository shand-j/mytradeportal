"""API service configuration."""

import os

from mtp_shared import get_settings

settings = get_settings()

# Branded public base URL for calendar subscription links (webcal/.ics).
# Overrides ``settings.app_public_url`` for feed URLs only, so the link users
# subscribe to presents a branded domain instead of the raw service origin.
# Empty falls back to ``app_public_url``, then to the request origin.
CALENDAR_FEED_BASE_URL: str = os.environ.get("CALENDAR_FEED_BASE_URL", "")

# In-process reminder scheduler (quote/invoice follow-up emails). Runs as an
# asyncio task started from the app lifespan; no extra infra. Disable per
# environment (e.g. PR previews) with REMINDER_SCHEDULER_ENABLED=false.
REMINDER_SCHEDULER_ENABLED: bool = os.environ.get(
    "REMINDER_SCHEDULER_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}
# Seconds between reminder sweeps. The first sweep runs one full interval
# after startup so a fresh deploy never immediately blasts customers.
REMINDER_TICK_SECONDS: int = int(os.environ.get("REMINDER_TICK_SECONDS", "3600"))

# Estimated LLM list prices (USD per 1K tokens) used only for internal AI
# spend attribution on quotes — never for customer billing. Keys are matched
# as substrings of the configured model id (e.g. "openai/kimi-k2.6" matches
# "kimi-k2.6"). Models missing from the map still record token counts, with
# est_cost_usd=None.
LLM_COST_PER_1K_TOKENS_USD: dict[str, dict[str, float]] = {
    # Moonshot Kimi K2.6 list-price estimate (prompt / completion per 1K tokens).
    "kimi-k2.6": {"prompt": 0.0006, "completion": 0.0025},
}
