"""API service configuration."""

import os

from mtp_shared import get_settings

settings = get_settings()

# Branded public base URL for calendar subscription links (webcal/.ics).
# Set this to the API's public origin in production. Empty falls back to the
# request origin (the API's own host) and only then to ``app_public_url`` —
# which points at the back office, where the feed path does not exist.
CALENDAR_FEED_BASE_URL: str = os.environ.get("CALENDAR_FEED_BASE_URL", "")

# Public base URL for the customer-facing quote/invoice web pages hosted on
# the landing site (``/{kind}/{token}``). Used when minting
# ``DocumentAccessToken`` links in quote/invoice emails.
PUBLIC_DOCS_BASE_URL: str = os.environ.get(
    "PUBLIC_DOCS_BASE_URL", "https://www.mytradeportal.co.uk"
).rstrip("/")

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

# In-process nightly rollup scheduler (W1-C): folds ai_call_events into the
# ai_rollup_* tables, refreshes the weekly FX rate, and fires budget/anomaly
# alerts. Same asyncio-task-in-lifespan pattern as the reminder scheduler.
# Disable per environment with ROLLUP_SCHEDULER_ENABLED=false.
ROLLUP_SCHEDULER_ENABLED: bool = os.environ.get(
    "ROLLUP_SCHEDULER_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}
# Seconds between loop ticks. Each tick only checks the clock; the actual fold
# runs once per UTC day at ROLLUP_RUN_HOUR_UTC:ROLLUP_RUN_MINUTE_UTC (default
# 02:30 UTC). On startup after the run time the missed fold runs immediately.
ROLLUP_TICK_SECONDS: int = int(os.environ.get("ROLLUP_TICK_SECONDS", "300"))
ROLLUP_RUN_HOUR_UTC: int = int(os.environ.get("ROLLUP_RUN_HOUR_UTC", "2"))
ROLLUP_RUN_MINUTE_UTC: int = int(os.environ.get("ROLLUP_RUN_MINUTE_UTC", "30"))
# Weekly FX refresh: the nightly tick fetches USD→GBP when the newest fx_rates
# row is older than this many days. Failures keep the last-known rate.
FX_REFRESH_MAX_AGE_DAYS: int = int(os.environ.get("FX_REFRESH_MAX_AGE_DAYS", "7"))

# AI spend budget + anomaly alerts (W1-C). Empty budget = budget alerts off.
# Anomaly alerts always evaluate but only dispatch when at least one channel
# (email or Slack) is configured; both are no-ops when unset.
AI_MONTHLY_BUDGET_GBP: str = os.environ.get("AI_MONTHLY_BUDGET_GBP", "").strip()
ALERT_EMAIL_TO: str = os.environ.get("ALERT_EMAIL_TO", "").strip()
SLACK_ALERT_WEBHOOK_URL: str = os.environ.get("SLACK_ALERT_WEBHOOK_URL", "").strip()
