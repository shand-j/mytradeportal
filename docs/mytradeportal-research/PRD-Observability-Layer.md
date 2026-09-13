# PRD — AI Observability Layer

| | |
|---|---|
| **Status** | Approved for planning |
| **Owner** | Founder (product) / Lead dev (delivery) |
| **Phase** | Pre-beta blocker — must ship before beta onboarding |
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · [K3 Prompt](K3-Agent-Prompt-Observability-Layer-and-Pricing.md) · Related: [PRD-Pricing-and-Billing.md](PRD-Pricing-and-Billing.md), [PRD-Customer-Portal.md](PRD-Customer-Portal.md) |
| **Evidence base** | [MyTradePortal-AI-Cost-Observability-Pricing-Strategy.md](MyTradePortal-AI-Cost-Observability-Pricing-Strategy.md) (research report, §§1–4) |

## 1. Problem Statement

AI inference is our largest variable cost and is currently invisible at the unit level. We log per-generation JSON blobs, but they lack identity attribution (user/org/feature), capture quality signals too coarsely to compute accuracy, and record no downstream outcomes. Without this layer we cannot: price flat plans safely, detect margin erosion, measure AI quality, detect abuse, or answer investor/stakeholder questions about unit economics. **Every downstream decision in the pack (pricing dials, fair-use thresholds, tier gates) depends on this data existing.**

## 2. Goals & Non-Goals

**Goals**
- Per-organisation, per-feature, per-user cost attribution for every AI call, in GBP, reconciled monthly against provider invoices.
- Quality measurement: line-item keep-rate, price drift, calibration of self-reported confidence vs observed outcomes.
- Operational guardrails: budget alerts, anomaly detection, per-org cost leaderboards.
- Trace-level debugging via self-hosted Langfuse; business dashboards via self-hosted Metabase; product-analytics shim for future PostHog.

**Non-goals (explicitly out of scope)**
- Customer-facing usage dashboards or meters (rejected — AI is unmetered).
- Real-time evaluation on the request path (all quality scoring is async).
- Data warehouse / ELT infrastructure (rollups in Postgres are sufficient at beta scale).
- LLM-as-a-judge eval suites (phase 2, after keep-rate baselines exist).

## 3. Current State

The AI pipeline logs a JSON blob per generation containing `rag.llm_usage` (model, est_cost_usd, prompt/completion tokens), `confidence`, `completeness`, `retrieval_status`, `generation_seconds`, `ai_draft` (line items, total), and `ai_feedback` (`edited`, `price_drift_pct`, `line_count_delta`). Gaps: no `user_id`/`org_id`/`feature`/`prompt_version`, no cache-token split, no retry chain linkage, no draft-vs-final snapshots, no outcome linkage, no GBP normalisation, `retrieval_status: "no_index"` observed in samples.

## 4. Requirements

### 4.1 Event schema (P0)

`ai_call_events` table — JSONB raw payload plus promoted indexed columns:

| Column | Type | Notes |
|---|---|---|
| `id`, `trace_id`, `parent_event_id` | uuid | `parent_event_id` links regenerations of one user intent |
| `user_id`, `organisation_id` | FK, indexed | Nullable user for system jobs |
| `actor_type` | enum | `staff` / `customer` / `system` |
| `feature` | varchar, indexed | `quote_draft`, `drawing_analysis`, `customer_intake_brief`, `customer_chat`, … |
| `gen_ai.provider.name`, `gen_ai.request.model` | varchar | OTel GenAI naming |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cached_input_tokens` | int | Cache split mandatory |
| `est_cost_usd`, `cost_gbp`, `fx_rate_date` | decimal/date | GBP at stored daily rate |
| `latency_seconds`, `status` (`success|timeout|error|abandoned`), `attempt_no` | — | Retry-chain aware |
| `prompt_version`, `confidence`, `completeness`, `retrieval_status` | — | Promoted for slicing |
| `payload` | JSONB | Full raw blob |
| `entry_channel` | varchar, nullable | Populated for customer-originated events (see portal PRD) |
| `created_at` | timestamptz, indexed | |

- Single logging helper/decorator wraps **every** AI call site; fail-open (logging errors never break user requests); <50ms added latency.
- Cost computed from date-versioned provider price lists in one module (`billing/ai_pricing.py`) — never hard-coded at call sites.

### 4.2 Quality capture (P0)

- `ai_draft_feedback`: FK to event, `draft_snapshot` JSONB, `final_snapshot` JSONB (written on quote send), timestamps.
- Async task computes per event: **line-item keep-rate** (unchanged ÷ total AI lines, description-similarity matching), **price drift %**, lines added/removed, description-rewrite count.
- Migrate/replace the coarse `edited | price_drift_pct | line_count_delta` capture; backfill historical rows where snapshots exist.
- Outcome events `quote_sent`, `quote_accepted`, `invoice_paid` emitted from existing flows, carrying `trace_id`.

### 4.3 Rollups & alerts (P0)

- Nightly job → `ai_rollup_org_day`, `ai_rollup_feature_day`: tokens, cost, generations, retries, latency p50/p95, keep-rates. All dashboards query rollups, never the event table.
- Alerts (Slack webhook + email, configurable): monthly AI budget at 50/80/100%; daily spend anomaly >3× trailing-7-day mean; latency p95 spike; org crossing fair-use threshold (feeds Pricing PRD guardrails).
- Staff-only ops view: per-org monthly AI cost leaderboard, cohort p50/p95/p99.

### 4.4 Tooling (P1)

- `docker-compose` services: **Metabase** (read-only DB user) and **Langfuse** (self-hosted: app + Postgres + ClickHouse). Env vars documented in README/.env.example.
- Langfuse traces emitted from the logging helper behind optional SDK import; prompt text + versions included.
- `analytics.track()` shim emitting activation funnel events (signup → first AI draft → first sent quote); PostHog pluggable later.

### 4.5 Operations (P0)

- Management commands: `backfill_ai_events` (existing blobs → new schema), `reconcile_ai_costs <range>` (estimated vs provider invoice; alert if drift >10%).

## 5. Metrics & Success Criteria

| Metric | Target at beta exit |
|---|---|
| % of AI calls attributed (user/org/feature) | 100% |
| Estimated vs actual provider cost drift | <10% monthly |
| Keep-rate computable for sent quotes | ≥90% of sent AI-drafted quotes |
| Dashboard freshness | T+1 day |
| Added request-path latency from logging | <50ms |

## 6. Dependencies & Risks

- **Dependency:** nothing — this is the foundation layer. Pricing guardrails and portal AI attribution consume its outputs.
- **Risk:** prompt text contains customer personal data → self-hosted tooling keeps data in our infra; document retention limits and access controls (UK GDPR); privacy notice update (see Delivery Plan compliance tasks).
- **Risk:** rollup job failure silently empties dashboards → alert on job failure, not just on data thresholds.

## 7. Out of Scope / Future

LLM-as-judge evaluation sweeps, customer-facing analytics, ClickHouse migration for events (only if event volume outgrows Postgres), per-feature cost budgets with auto-throttling.
