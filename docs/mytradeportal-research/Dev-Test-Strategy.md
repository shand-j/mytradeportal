# Dev-Test Strategy

| | |
|---|---|
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · Governs work from: [PRD-Observability-Layer.md](PRD-Observability-Layer.md), [PRD-Pricing-and-Billing.md](PRD-Pricing-and-Billing.md), [PRD-Customer-Portal.md](PRD-Customer-Portal.md) |
| **Audience** | Internal contributors |

## 1. Test pyramid for this stack

| Layer | What | Tools | When |
|---|---|---|---|
| Unit | Keep-rate diffing, cost computation from price lists, feature gates, fair-use thresholds, trial extension trigger, magic-link generation | pytest | Every PR |
| Integration | Logging helper fail-open behaviour, rollup job correctness, Paddle webhook→plan mapping, OTP flow, object-level authorization (customer sees only own data) | pytest + test DB | Every PR |
| Contract | Paddle webhook payload handling (recorded fixtures), provider API response parsing (recorded LLM responses — never live calls in CI) | pytest + fixtures/vcr | Every PR |
| E2E (thin) | QR landing → form → verify → submission; signup → first AI draft → sent quote; trial extension end-to-end | Playwright against staging | Pre-release |
| Manual/UAT | Beta-cohort smoke list (§5) on staging before each weekly batch release | Checklist | Weekly release |

**Hard rules:** no live LLM calls in CI (recorded fixtures only); no live Paddle in CI (sandbox + recorded webhooks); migrations tested up *and down* on a production-like dump before any release touching `ai_call_events`.

## 2. Environments

- **Local:** docker-compose full stack (app, Postgres, worker, Metabase/Langfuse optional).
- **Staging:** mirrors production config incl. worker + rollup schedule (shortened windows); Paddle **sandbox**; LLM calls routed to cheapest model with low caps; seed data incl. a demo tradie org with QR/code and fixture customers.
- **Production:** beta cohort. Feature flags for anything user-visible shipping before it's fully baked.

## 3. AI-specific testing (the part most teams skip)

- **Fixture quotes:** a library of draft→final quote pairs with known keep-rates/price drift; the diffing pipeline must reproduce known values exactly.
- **Prompt regression:** golden set of representative job inputs; on any `prompt_version` change, run the golden set on staging, diff outputs structurally (line counts, price ranges, schema validity), and record keep-rate baseline expectations. Human review of 5 samples before promoting a prompt version.
- **Cost ceiling test:** synthetic burst against staging must trigger burst limits and cheap-route fallback (proves guardrails work before a real abuser finds them).
- **Guardrail invisibility test:** normal-usage simulation must never surface a meter, block, or warning — this is a product promise, tested like a feature.
- **Fail-open test:** kill the logging backend mid-request; user request must succeed; dropped events counted and alerted.

## 4. Definition of Done (all workstreams)

Tests per §1 for the touched layer · migration up/down verified · feature flag or safe rollout for user-visible change · observability event(s) emitted for any new AI call or user flow (no new feature ships dark) · docs updated (README/env/API note as applicable) · release note line written for the stakeholder changelog.

## 5. Beta UAT smoke list (staging, before each weekly batch)

1. Tradie: generate AI quote → edit → send (keep-rate event fires).
2. Customer: QR URL → submit request with photo → verify → see status.
3. Tradie: sees intake brief; responds.
4. Customer: magic link from notification → views quote → accepts.
5. Payments: invoice sent → customer "Pay securely now" (Stripe sandbox) → invoice auto-marked paid → tradie notified → `invoice_paid` event present; full refund works.
6. Trial: org with ≥3 sent AI quotes gets extension.
7. Staff: ops cost view shows yesterday's org costs; alert test fires.
8. Gates: Sole Trader org cannot access Pro feature; no customer-visible usage element anywhere.
9. Parity spot-check: any Tradify Lite capability touched this release still matches [Tradify-Parity-Checklist.md](Tradify-Parity-Checklist.md).

## 6. Bug handling in beta

P0s (see [Backlog-Management.md](Backlog-Management.md)) reproduce on staging first, fix with regression test, ship immediately. Everything else batches weekly. Every P0 fix must answer: which test would have caught this, and is it now written?
