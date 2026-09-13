**Decisions already made (do not relitigate, do implement):**

- Attribute every AI event to `user`, `organisation`, `feature`, `prompt_version`; align column names with **OpenTelemetry GenAI semantic conventions** (`gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`).
- Store **full before/after snapshots** (AI draft + final sent version) so quality metrics are recomputable; derive metrics in code, not at capture time.
- Track `cached_input_tokens` separately and `cost_gbp` at a stored daily FX rate; reconcile estimated vs actual provider spend monthly.
- Analytics stack: keep events in our Postgres; **Metabase** and **Langfuse** self-hosted via Docker; product analytics events emitted so PostHog can be added later without schema changes.
- Pricing model at launch: **flat subscription per business, AI included unmetered on every plan** — no credits, no quotas, no overage, no per-seat pricing, unlimited users on all tiers. Tiers are differentiated by **capability** (features), never capacity (seats or AI actions). A fair-use policy (abuse-only, invisible to normal users) protects the cost tail. No free tier with AI included. 14-day trial.

---

## WORKSTREAM 1 — OBSERVABILITY LAYER

### 1.1 Event schema upgrade (migration)

- Locate the current AI-generation storage. Design `ai_call_events` (or upgrade the existing table): JSONB raw payload **plus promoted indexed columns**: `user_id`, `organisation_id`, `feature` (e.g. `quote_draft`, `drawing_analysis`), `gen_ai.request.model`, `gen_ai.provider.name`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cached_input_tokens`, `est_cost_usd`, `cost_gbp`, `fx_rate_date`, `latency_seconds`, `status` (`success|timeout|error|abandoned`), `attempt_no`, `parent_event_id` (links regenerations of the same user intent), `prompt_version`, `confidence`, `completeness`, `retrieval_status`, `trace_id`, `created_at`.
- Cost must be computed from **date-versioned provider price lists in one module** (e.g. `billing/ai_pricing.py`), never hard-coded per call site.
- Wire the writer into every AI call site via a single helper/decorator so no feature can bypass logging. Failures in logging must never break the user request (log-and-continue).

### 1.2 Feedback & quality capture

- New `ai_draft_feedback` storage: FK to the generation event, `draft_snapshot` (JSONB), `final_snapshot` (JSONB, written when the quote is sent), timestamps.
- Async task (Celery/django-q) computing per event: **line-item keep-rate** (unchanged lines / total AI lines, matched by description similarity), **price drift %**, **lines added/removed**, description-rewrite count. Replace the coarse `edited/price_drift_pct/line_count_delta` capture, keeping backwards compatibility or migrating historical rows.
- Outcome events: `quote_sent`, `quote_accepted`, `invoice_paid` — emitted from existing flows, carrying the generation `trace_id` so quality can be joined to outcomes.

### 1.3 Rollups & alerts

- Nightly job folding events into `ai_rollup_user_day` and `ai_rollup_feature_day` (tokens, cost, generations, retries, latency p50/p95, keep-rates). Dashboards query rollups, not the event table.
- Budget alerting: monthly AI budget in settings; notify (Slack webhook and/or email, configurable) at 50/80/100%. Also alert on daily spend anomalies (e.g. >3× trailing 7-day mean) and on latency p95 spikes.
- Admin ops view (Django admin or simple staff-only page): per-user monthly AI cost leaderboard with p50/p95/p99 cohort stats. No fancy frontend — the BI tool handles real dashboards.

### 1.4 Tooling (Docker, non-blocking)

- Add `docker-compose` services: **Metabase** (read-only Postgres user) and **Langfuse** (self-hosted, its own Postgres + ClickHouse). Document env vars in the project README/.env.example.
- Emit Langfuse traces from the logging helper (SDK optional-install: code must run fine without it). Include prompt text + versions so prompt changes are comparable.
- Emit product-analytics events (activation funnel: signup → first AI draft → first sent quote) behind a small `analytics.track()` shim so PostHog (or nothing) can be plugged in.

---

## WORKSTREAM 2 — PRICING (LANDING PAGE + PADDLE)

### 2.1 Model to implement (provisional numbers — see placeholders)

Flat per business, unlimited users on every tier, AI included unmetered (fair use applies). Tiers differ by capability only:

| Tier | Price (flat, per business) | Capability differentiation |
| --- | --- | --- |
| Sole Trader | £`[DECIDE: 25]`/mo | Full portal + AI quote drafting, chase sequences (F2), online payments (F1), **Xero/QuickBooks sync (F5)**, data export, customer portal + intake-brief AI |
| Pro | £`[DECIDE: 39]`/mo | + drawing/photo analysis, customer-facing AI chat assistant, certificates MVP (F8), deposits + optional line items (F6/F7), offline mode (F9), priority models |
| Team | £`[DECIDE: 69]`/mo | + multi-user scheduling, roles & permissions, shared customer portal, team reporting |
| Trial | 14 days, full features, no card required | Extend to 30 days after ≥3 sent AI quotes |

### 2.2 Tasks

- **Landing page:** rewrite the pricing section to the table above. Copy must be plain-English for tradespeople and lead with the unmetered promise — e.g. "AI included on every plan — no credits, no counting" — with per-tier feature comparison, Pro marked "Most popular", flat per-business pricing stated explicitly ("one price for your whole business — unlimited users"), and a fair-use footnote linking to the policy. State prices ex-VAT if that's current convention on the page (check). Keep the existing page's design system — match, don't redesign.
- **Fair-use policy page:** draft a short plain-English policy (generous threshold, e.g. ~`[DECIDE: 500]` AI actions/mo per business, framed as anti-abuse; "we'll always talk to you before limiting anything"; never a hard block without human review). Link from pricing footer and T&Cs.
- **Paddle:** using the Paddle dashboard config and/or API integration in the repo: create/update products and prices for the three flat tiers (monthly + annual-with-discount if annual already exists). **No metered/usage-based price and no seat-quantity logic** — three simple recurring subscriptions. Update any price-ID constants/env vars in code. Check how checkout/webhooks currently map Paddle price IDs to internal plans and update the mapping. Do NOT delete existing prices that live customers may be subscribed to — deprecate by archiving new signups only; report what you found before changing anything in the live catalog.
- **Entitlements (guardrails, not quotas):** two mechanisms only — (a) **tier feature gates** for the Pro/Team capabilities above; (b) **fair-use guardrails** fed by the Workstream 1 rollups: burst rate limits per org, automatic downgrade to a cheaper model route at extreme sustained volume, and a staff alert when an org crosses the fair-use threshold. All thresholds configurable in settings. Never surface a usage meter, counter, or block to the customer.
- **Trial logic:** 14-day full-feature trial, no card; extension to 30 days triggered by ≥3 sent AI-drafted quotes (use the outcome events from 1.2).

---

## CONSTRAINTS & ACCEPTANCE CRITERIA

- Every change behind a migration + feature-safe rollout; logging must be fail-open; no existing AI feature may break or slow materially (<50ms added latency on the request path).
- Provide management commands: `backfill_ai_events` (migrate existing JSON blobs into the new schema), `reconcile_ai_costs` (estimated vs provider invoice for a date range).
- Tests: schema round-trip, keep-rate diffing on fixture quotes, tier feature-gate enforcement, fair-use throttle/alert triggers, trial-extension trigger, Paddle webhook mapping, chase-sequence scheduling/cancellation/duplicate-guard + £-amount linter, export round-trip, streaming generation + timeout ladder, Stripe webhook fixtures.
- Update README/env docs for Metabase, Langfuse, budget alerts, and Paddle config.
- End with a summary: files changed, migrations, what needs manual action in the Paddle dashboard, and any `[DECIDE]` items still open.

## WORKSTREAM 3 — CUSTOMER PORTAL

### 3.1 Entry & acquisition surfaces

- Tradie-scoped vanity URL `mytradeportal.co.uk/t/{org_slug}` rendering a **tradie-branded landing page** (their name/logo/colours where available).
- QR code generation per org (linking to the vanity URL) plus downloadable asset pack: van-decal artwork, business-card PDF, invoice-footer snippet.
- 6-digit code entry as alternate path for verbal/print handover — resolves to the same page.
- **Embeddable quote-request widget** (JS snippet/iframe) for the tradie's own website, plus shareable link for Google Business Profile / socials.
- Tag every session with `entry_channel` (`qr_van | qr_card | code | widget | direct | app`) for attribution analytics.

### 3.2 Web-first customer flow (no app-install on the critical path)

- **Unauthenticated quote-request form** on the landing page: name, phone/email, job description, photos, preferred timing. Bot protection (Cloudflare Turnstile) + submission rate limits. **No LLM call until contact details verify.**
- **Progressive registration:** account created at submission — name + phone, OTP or magic-link verification. No password required at first use.
- Portal home after verification: request status timeline → quotes (view/accept/question) → invoices (view/pay) → chat.
- All notifications (quote ready, invoice due, reply) via SMS/email with **magic links** deep-linking to the specific object — the notification is the primary interface for occasional users.
- PWA: installable, add-to-home-screen prompt from second visit; app-store upgrade path only for repeat customers (landlords, property managers).
- Customer access model: separate lightweight auth (phone/magic-link OTP), distinct from staff auth, scoped strictly to that customer's own data.

### 3.3 Customer-side AI (flat-pricing compatible, abuse-resistant)

- **Intake brief:** customer photos + description → structured job brief for the tradie. Cheap bounded model call, one per request. Included generously on all tiers — it fills the tradie's pipeline.
- **Chat assistant (Pro tier gate):** scoped retrieval over that customer's quotes/invoices/status + FAQs; small cheap model; hard turn caps; graceful "your tradesperson will reply" handoff. Never open-ended.
- All customer AI events tagged `actor_type=customer` and attributed to the tradie's org; abuse guardrails per Workstream 2 (burst limits, cheap-route fallback, staff alerts).

---

## WORKSTREAM 4 — ONLINE PAYMENTS (STRIPE)

- **Stripe integration for tradie receivables** (spec: [PRD-Online-Payments.md](PRD-Online-Payments.md)). Evaluate Connect Express vs Standard account OAuth first; recommend one as an ADR before building. Never route tradie funds through our Paddle account.
- Tradie side: payments settings + Stripe onboarding flow, per-invoice/default card-payment toggle, invoice payment states (sent → viewed → paid → payout reconciled).
- Customer side: "Pay securely now" on invoice email/SMS magic link, portal invoice view, and invoice PDF; tradie-branded Stripe Payment Element page (Apple Pay/Google Pay/card); no account needed to pay; receipt email.
- Webhooks: `payment_intent.succeeded` (auto-mark invoice paid + emit `invoice_paid` with trace_id + notify tradie), refunds, disputes, payouts. Idempotent handlers with retry + alert on failure.
- Full refunds tradie-initiated (partial: P1). Deposit/partial payment on invoices: P1, land early beta if Phase 0 allows.
- Tests: recorded webhook fixtures, Stripe sandbox E2E (invoice → pay → auto-marked paid), no live Stripe in CI.
- Compliance guardrails: Stripe-hosted fields only (no PAN touches our servers); consumer card surcharging blocked by default pending legal review; payment metadata added to privacy notice/retention.

---

**If any `[DECIDE]` placeholder is still unfilled when you reach Workstream 2, stop and ask me for the numbers before touching Paddle.**

---