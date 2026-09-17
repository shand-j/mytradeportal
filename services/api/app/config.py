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

# Fair-use AI guardrails (flat pricing: AI is unmetered for customers, so
# these protect cost without ever surfacing a usage meter). Per-org burst
# limit: ai_call_events counted for the current UTC hour; HTTP 429 +
# Retry-After when exceeded. Monthly soft threshold: when a tenant's
# current-month AI action count (ai_call_events excluding outcome rows)
# reaches it, the tenant is switched to the cheap model route and staff get
# ONE internal ops alert per org per month — never customer-visible.
AI_BURST_LIMIT_PER_HOUR: int = int(os.environ.get("AI_BURST_LIMIT_PER_HOUR", "60"))
AI_FAIR_USE_MONTHLY_THRESHOLD: int = int(os.environ.get("AI_FAIR_USE_MONTHLY_THRESHOLD", "500"))

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
# Monthly cost-drift reconciliation (#60): the provider's invoiced USD total
# for the month just closed, compared on the month-boundary rollup tick
# against the platform-estimated spend summed from ai_rollup_feature_day
# (converted at the stored USD→GBP rate). Empty = drift check off; the manual
# scripts/reconcile_ai_costs.py run remains the fallback.
AI_MONTHLY_INVOICE_USD: str = os.environ.get("AI_MONTHLY_INVOICE_USD", "").strip()
ALERT_EMAIL_TO: str = os.environ.get("ALERT_EMAIL_TO", "").strip()
SLACK_ALERT_WEBHOOK_URL: str = os.environ.get("SLACK_ALERT_WEBHOOK_URL", "").strip()

# --- Staff ops endpoints (platform-level, cross-tenant) ----------------------
# Comma-separated email allowlist identifying platform staff (founders/ops)
# for cross-tenant endpoints such as GET /staff/ops/ai-costs. There is no
# platform-tenant staff account: the caller must be an authenticated active
# user AND their email must appear here. Empty = the gate rejects everyone
# (endpoint answers 403), so an unconfigured environment exposes nothing.
PLATFORM_STAFF_EMAILS: str = os.environ.get("PLATFORM_STAFF_EMAILS", "").strip()

# --- Stripe Connect (customer → tradie invoice card payments) --------------
# Destination charges on Express connected accounts, no platform application
# fee. Paddle remains for OUR SaaS subscription only — tradie receivables
# never touch Paddle (ADR-003). Empty STRIPE_SECRET_KEY disables the whole
# feature: staff endpoints answer 503 ``payments_not_configured`` and public
# invoice pages simply omit the Pay button.
STRIPE_SECRET_KEY: str = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET: str = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
# Connect client id (ca_...) — reserved for future OAuth-style onboarding
# links; Express account links work without it.
STRIPE_CONNECT_CLIENT_ID: str = os.environ.get("STRIPE_CONNECT_CLIENT_ID", "").strip()
# Publishable key (pk_...) for the future Stripe.js /pay landing page. The API
# only ever hands out PaymentIntent client secrets; the publishable key is
# documented here so the landing site build can pick it up. Public by design.
STRIPE_PUBLISHABLE_KEY: str = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()

# --- Public intake: inline AI check + guest chat threads --------------------
# The sync intake check is a single cheap-model LLM call the public
# quote-request endpoint optionally awaits (sync_check=true). It must never
# block the submission: a hard asyncio timeout bounds it and every failure
# fails open to status "unavailable".
INTAKE_TRIAGE_MODEL: str = os.environ.get("INTAKE_TRIAGE_MODEL", "gpt-4o-mini").strip()
INTAKE_TRIAGE_TIMEOUT_SECONDS: float = float(os.environ.get("INTAKE_TRIAGE_TIMEOUT_SECONDS", "12"))
# Lifetime of the guest-scoped JWT that lets an unauthenticated homeowner
# answer AI triage questions inline on their quote-request thread.
GUEST_THREAD_TTL_MINUTES: int = int(os.environ.get("GUEST_THREAD_TTL_MINUTES", "120"))

# --- Customer portal (magic-link auth on per-tenant subdomains) --------------
# Base domain for tenant portal subdomains: ``https://{slug}.{PORTAL_BASE_DOMAIN}``.
PORTAL_BASE_DOMAIN: str = os.environ.get("PORTAL_BASE_DOMAIN", "mytradeportal.co.uk").strip()
# Days a customer portal magic-link token stays valid; re-issuing revokes the
# customer's earlier tokens so only the newest emailed link works.
PORTAL_MAGIC_TTL_DAYS: int = int(os.environ.get("PORTAL_MAGIC_TTL_DAYS", "30"))

# --- Resend inbound webhooks (bounce/delivery-failure alerts) -----------------
# Svix signing secret (whsec_...) for POST /webhooks/resend. Empty disables
# the endpoint: it answers 503 so Resend keeps retrying until configured.
RESEND_WEBHOOK_SECRET: str = os.environ.get("RESEND_WEBHOOK_SECRET", "").strip()
