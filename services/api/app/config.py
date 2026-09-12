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

# Global kill-switch for AI-usage entitlement enforcement (W2-A). When false
# (the default until the Paddle price mapping is proven in sandbox), the
# ``require_ai_allowance`` dependency is a no-op pass-through and no tenant is
# ever blocked or warned. Set ENTITLEMENTS_ENABLED=true to enforce.
ENTITLEMENTS_ENABLED: bool = os.environ.get("ENTITLEMENTS_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# LLM/embedding list prices moved to ``app.ai_pricing`` (date-versioned price
# lists; ``estimate_llm_cost_usd`` in ``app.rag.generation`` delegates there).
