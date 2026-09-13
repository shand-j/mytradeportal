# PRD — Online Payments (Customer → Tradie)

| | |
|---|---|
| **Status** | Table stakes — beta blocker |
| **Owner** | Founder (product) / Lead dev (delivery) |
| **Phase** | **Pre-beta (Phase 0).** Tradify includes online & card payments on every tier including Lite; shipping beta without them breaks competitive parity and removes our "get paid faster" story |
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · [K3 Prompt](K3-Agent-Prompt-Observability-Layer-and-Pricing.md) · Depends on: [PRD-Observability-Layer.md](PRD-Observability-Layer.md) (`invoice_paid` event) · Consumed by: [PRD-Customer-Portal.md](PRD-Customer-Portal.md) (pay from portal) |
| **Evidence** | Tradify Lite feature list: "Online & Credit Card Payments" ([tradifyhq.com/pricing](https://www.tradifyhq.com/pricing)); Tradify Stripe help doc ([help.tradifyhq.com](https://help.tradifyhq.com/hc/en-us/articles/360033458194-Using-Stripe-Credit-Card-Payments-in-Tradify)) |

## 1. Decision Record (locked)

- **Provider: Stripe** for customer→tradie payments. Paddle remains our *subscription* billing (merchant of record for our SaaS fees); Stripe handles the *tradie's* receivables. The two systems never mix — a payment to a tradie must never touch our Paddle balance.
- **Model: tradie-connected accounts** (Stripe Connect, destination charges) OR per-tradie own-Stripe-account OAuth. Decide at planning against effort/compliance — see open questions. Default recommendation: **Connect Express accounts** — tradie onboards with KYC once inside our app, we never hold funds, Stripe handles FCA-regulated money flow.
- **No platform take-rate at beta.** We charge the subscription only; processing fees are Stripe's, passed through transparently (Tradify does the same). A take-rate is a post-PMF monetisation decision, not a beta one.
- **Payments are in every tier** — like Tradify. Not a Pro gate.

## 2. Requirements

### 2.1 Tradie side (P0)

- Payments settings page: connect Stripe (Express onboarding flow), connection status, payout schedule explainer.
- Per-invoice and default-on toggle: "accept online card payments".
- Payment status on invoices: sent → viewed → paid (auto-marked via webhook) → payout reconciled.
- Optional surcharging: off by default; if enabled, must comply with UK rules (consumer card surcharges are banned — implement as "disabled for B2C" guardrail; flag for legal review before enabling anything).

### 2.2 Customer side (P0)

- **"Pay securely now" button** on: invoice email/SMS (magic link), portal invoice view, and invoice PDF.
- Payment page: tradie-branded, amount, reference, Apple Pay/Google Pay/card via Stripe Payment Element. No account required to pay.
- Receipt email to customer; confirmation notification to tradie; `invoice_paid` outcome event emitted with `trace_id` (Observability PRD) — closes the quote→cash loop in our analytics.
- Partial payments/deposits: support a deposit amount on an invoice (common in trades) — P1, can land early beta if Phase 0 is tight.

### 2.3 Ops & edge cases (P0)

- Webhook handling: `payment_intent.succeeded`, `charge.refunded`, `charge.disputed`, `payout.paid`; idempotent handlers; failed-webhook retry + alert.
- Refunds: tradie-initiated from invoice view (P0 simple full refund; partial refunds P1).
- Failed payments surfaced to tradie with reason; customer can retry without contacting us.
- Test coverage per Dev-Test Strategy: recorded webhook fixtures, sandbox E2E (invoice → pay → auto-marked paid), no live Stripe in CI.

## 3. Compliance notes

- We never hold customer funds; Stripe Connect keeps money flow regulated under Stripe's FCA permissions. Confirm with Stripe whether Express or Standard fits our liability posture (Standard = tradie's own account, less our involvement; Express = better UX, we own more of the flow). Record the choice as an ADR.
- UK GDPR: payment metadata (name, amount, invoice ref) added to privacy notice and retention schedule (Delivery Plan item 0.9).
- PCI: Stripe-hosted fields/Payment Element only — we never touch PAN data. State this in docs.

## 4. Metrics

| Metric | Beta target |
|---|---|
| % of beta tradies who connect payments | ≥60% |
| Invoices with online payment enabled | ≥70% of sent invoices |
| Median days invoice→paid (online vs manual) | Measure — this is the headline ROI stat for marketing |
| Payment page completion rate | ≥80% |

## 5. Out of Scope / Future

Platform take-rate; instalment/finance options (e.g. Klar.na-style job financing); direct debit/BACS via GoCardless; payment links standalone from invoices; on-site QR "scan to pay" (Tradify has this — strong phase-2 candidate aligned with our QR asset pack).
