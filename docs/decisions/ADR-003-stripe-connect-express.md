# ADR-003 — Stripe Connect Express for customer → tradie payments

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-13 |
| **Reference** | [docs/mytradeportal-research/PRD-Online-Payments.md](../mytradeportal-research/PRD-Online-Payments.md) |

## Context

Online payments are competitive table stakes — Tradify includes card payments
on every tier including Lite, so beta without them fails parity on day one and
forfeits the "get paid faster" story. We needed a model where customer money
reaches the tradie without us holding funds or taking on FCA-regulated money
flow ourselves. Options evaluated: Stripe Connect Express vs Connect Standard.

## Decision

- Customer → tradie payments run on **Stripe Connect with Express accounts**
  and **destination charges**. Tradies complete KYC once, inside our app;
  Stripe handles the regulated money flow; we never hold funds.
- **Express over Standard**: Express gives in-app KYC onboarding UX and
  Stripe-managed compliance. Standard was rejected — its onboarding is
  clunkier for non-technical tradies and would suppress connection rates
  against the ≥60% beta target.
- **No platform take-rate at beta.** We charge the subscription only;
  processing fees are Stripe's, passed through transparently. A take-rate is a
  post-PMF decision.
- **Stripe-hosted fields / Payment Element only** — no PAN data ever touches
  our servers.
- **UK consumer-card surcharging is disabled** (B2C surcharges are banned in
  the UK); any B2B surcharging is off by default and flagged for legal review
  before enabling.
- **Paddle remains merchant of record for our subscription only.** The two
  money flows never mix — a payment to a tradie must never touch our Paddle
  balance. The legacy Paddle invoice-checkout path is removed.

## Consequences

- Payments settings page (Express onboarding, status, payout explainer) and the
  pay page (Stripe Payment Element, Apple Pay/Google Pay) are P0 beta blockers
  (Delivery Plan item 0.11).
- Webhooks (`payment_intent.succeeded`, `charge.refunded`, `charge.disputed`,
  `payout.paid`) are idempotent and alert on failure; `invoice_paid` closes the
  quote→cash loop in analytics.
- Payments are on every tier — not a Pro gate.
- A future take-rate or provider change requires a new ADR superseding this one.
