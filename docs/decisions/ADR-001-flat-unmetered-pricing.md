# ADR-001 — Flat, unmetered pricing (AI included on every tier)

| | |
|---|---|
| **Status** | Accepted (amended 2026-09-19 — see note) |
| **Date** | 2026-09-13 |
| **Reference** | [docs/mytradeportal-research/PRD-Pricing-and-Billing.md](../mytradeportal-research/PRD-Pricing-and-Billing.md) |

> **Amendment (2026-09-19, issue #190):** the founder reversed the "no seats"
> clause for multi-user invites: each tier now carries a hard **seat cap**
> (`Plan.seats` — sole_trader 1, pro 5, team 15) enforced by
> `POST /users/invite`. Pricing stays flat per business — seats are a limit,
> not a meter: no per-seat charges, no seat quantities in Paddle, and AI
> remains unmetered on every tier. Everything else in this ADR stands.

## Context

We needed a pricing model that survives flat-rate AI costs. The research report
(`MyTradePortal-AI-Cost-Observability-Pricing-Strategy.md`) recommended a hybrid
per-seat + metered-overage model, and that hybrid was briefly implemented in
this repo (commits `c37f481` / `8f0ea11` / `ba4e52c`). On review it was
rejected: seat pricing punishes exactly the growing trade businesses we want,
and metering makes AI feel like a tax at the moment it should feel like the
product. Competitor evidence (Tradify gating AI behind Plus at ~£46/user with a
fair-usage throttle) showed the hybrid model is the thing we should be
attacking, not copying.

## Decision

- **Flat per-business subscription. Unlimited users. No seats.**
- **AI included unmetered on every tier** — no credits, no allowances, no
  overage, no customer-visible counters.
- **Tiers differ by capability, never capacity** — higher tiers unlock
  expensive/advanced features; they never buy "more of the same".
- **Fair-use guardrails protect the cost tail** — anti-abuse framing, generous
  threshold, human review before any restriction, invisible to normal users.
- Provisional prices: **£25 / £39 / £69** per business per month until the
  Phase 3.3 evidence review (p50/p95 per-org AI cost, Van Westendorp
  interviews, competitor anchor) sets final numbers.

## Consequences

- Paddle holds **three flat recurring subscriptions only** — no metered prices,
  no seat quantities, no quota counters anywhere in the codebase.
- The hybrid implementation from `c37f481` / `8f0ea11` / `ba4e52c` is
  superseded; metering scaffolding is removed, not dormant.
- Margin safety comes from observability (cost rollups, budget/anomaly alerts)
  plus invisible fair-use guardrails — never from charging for usage.
- Requests to reintroduce metering or seat quotas are closed against this ADR
  unless accompanied by new evidence (see Backlog-Management, locked-decision
  filter).
- Economics guardrails: p95 org AI cost ≤ 10% of tier price; IER ≥ 8:1 at p50;
  reviewed monthly.
