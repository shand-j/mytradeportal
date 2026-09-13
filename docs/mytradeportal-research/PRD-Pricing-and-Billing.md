# PRD — Pricing, Packaging & Billing (Flat, AI Included)

|  |  |
| --- | --- |
| **Status** | Model approved; numbers provisional pending beta telemetry |
| **Owner** | Founder |
| **Phase** | Pre-beta: entitlement machinery + guardrails. Landing page + Paddle go-live: pre-launch (after beta pricing review) |
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · [K3 Prompt](K3-Agent-Prompt-Observability-Layer-and-Pricing.md) · Depends on: [PRD-Observability-Layer.md](PRD-Observability-Layer.md) |
| **Evidence base** | [MyTradePortal-AI-Cost-Observability-Pricing-Strategy.md](MyTradePortal-AI-Cost-Observability-Pricing-Strategy.md) (§§5–7) |

## 1. Decision Record (locked)

- **Flat subscription per business. No per-seat pricing. Unlimited users on every tier.** Seat ranges are a quota in disguise and punish exactly the growing businesses we want.
- **AI included unmetered on every plan.** No credits, no allowances, no overage, no customer-visible counters. AI is expected, not metered.
- **Tiers differentiated by capability, never capacity.** Higher tiers unlock expensive/advanced features; they never buy "more of the same".
- **Fair-use policy protects the cost tail** — anti-abuse framing, generous threshold, human review before any restriction, invisible to normal users.
- **No free tier with AI.** 14-day full-feature trial, no card; engagement-gated extension to 30 days.
- **Billing via Paddle** (merchant of record). Three flat recurring subscriptions only — no metered prices, no seat quantities.

## 2. Pricing Structure (provisional numbers)

| Tier | Price (flat/business/mo) | Capability differentiation |
| --- | --- | --- |
| **Sole Trader** | £`[DECIDE: 25]` | Full portal + AI quote drafting, chase sequences (F2), online payments (F1), **Xero/QuickBooks sync (F5)**, data export, customer portal + intake-brief AI |
| **Pro** | £`[DECIDE: 39]` | + drawing/photo analysis, customer-facing AI chat assistant, certificates MVP (F8), deposits + optional line items (F6/F7), offline mode (F9), priority models |
| **Team** | £`[DECIDE: 69]` | + multi-user scheduling, roles & permissions, shared customer portal, team reporting |
| **Trial** | — | 14 days full features, no card; +16 days after ≥3 sent AI-drafted quotes |

**Xero/QuickBooks sync is on every tier** — Tradify includes accounting sync on Lite, so gating it was a parity hole (corrected September 2026). Post-beta features (F11 EICR, F12 recurring jobs, F13 profit-per-job, F14 time tracking) are allocated by beta evidence; F12–F14 lean Team, F11 extends the Pro trade-moat.

**Attack lines this packaging enables:** Tradify gates AI (SmartRead/SmartWrite) behind Plus at ~£46/user with a fair-usage throttle — ours is on every plan, unmetered; Tradify per-seat pricing costs a 5-person crew £170+/mo on Lite — our Team tier is £69 flat; Tradify gates reminders and progress invoicing above Lite — our chase and deposits are included at £25/£39.

Numbers are placeholders pending the beta pricing review (see Delivery Plan, Phase 3): final values set from p50/p95 per-org AI cost, Van Westendorp interviews, and competitor anchor (£15–£40 band). Annual discount preserved if it already exists.

## 3. Requirements

### 3.1 Landing page (P1 — pre-launch)

- Pricing section rewritten to the table above. Copy leads with the unmetered promise: *"AI included on every plan — no credits, no counting"* and *"one price for your whole business — unlimited users"*.
- Per-tier feature comparison; Pro marked "Most popular"; fair-use footnote linking to policy page; ex-VAT convention matched to current page.
- No redesign — match existing design system.

### 3.2 Fair-use policy page (P0 — before beta)

- Plain-English page: threshold ~`[DECIDE: 500]` AI actions/mo per business (set at 3–5× beta p95 once telemetry exists); framed as anti-abuse; commitment to contact before any restriction; never a hard block without human review. Linked from pricing footer and T&Cs.

### 3.3 Paddle (P1 — pre-launch)

- Three products/prices (monthly; annual if existing). No metered price, no quantity logic.
- Update price-ID constants/env vars and webhook→plan mapping in code.
- **Never delete prices with live subscribers** — archive from new signups only; report live catalog state before changes.

### 3.4 Entitlements & guardrails (P0 — before beta)

- **Tier feature gates** for Pro/Team capabilities (server-side checks, consistent helper).
- **Fair-use guardrails** fed by observability rollups: per-org burst rate limits; automatic cheaper-model routing at extreme sustained volume; staff alert at threshold. All configurable. Never customer-visible.
- Trial logic incl. engagement extension trigger (consumes outcome events from Observability PRD).

## 4. Economics Guardrails (from research)

- Target: p95 org AI cost ≤ 10% of tier price; IER ≥ 8:1 at p50. Measured monthly from observability rollups.
- If breached: move the expensive feature up a tier → route it cheaper → talk to the outlier. Headline price changes are the last resort.
- Review cadence: monthly cost review; quarterly pricing review.

## 5. Risks

- **Power-user concentration**: top 5% of orgs driving disproportionate spend — mitigated by fair use + cheap-route fallback + telemetry visibility.
- **Customer-side AI volume** (see Portal PRD): intake briefs are deliberately generous (acquisition engine); chat assistant is Pro-gated and turn-capped.
- **Price anchoring**: AI-native competitors sit at £20 flat; our answer is capability breadth + unmetered AI, not a price war.
- **Grandfathering**: beta users get founding-member terms; define in beta comms before launch pricing lands.

## 6. Out of Scope / Future

Outcome-linked pricing (per-won-quote) — hold for v2+ once win-rate attribution exists; customer-facing usage statements (only if ever needed); usage-based billing machinery (Metronome/Stripe-style) — deliberately rejected by this PRD.