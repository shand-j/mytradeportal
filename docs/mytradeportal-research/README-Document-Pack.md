# MyTradePortal — Beta-to-Launch Document Pack

Everything needed to plan, build, and govern the observability layer, flat AI-included pricing, and the customer-facing portal. All links are relative — keep these files together in one directory.

## Documents

| File | Type | Audience | Purpose |
|---|---|---|---|
| [K3-Agent-Prompt-Observability-Layer-and-Pricing.md](K3-Agent-Prompt-Observability-Layer-and-Pricing.md) | Agent prompt | K3 coding agent | Self-contained implementation brief: 3 workstreams, plan-approval gate, `[DECIDE]` placeholders |
| [PRD-Observability-Layer.md](PRD-Observability-Layer.md) | PRD | Contributors | Event schema, quality capture, rollups, alerts, Metabase/Langfuse |
| [PRD-Pricing-and-Billing.md](PRD-Pricing-and-Billing.md) | PRD | Contributors + stakeholders | Locked pricing decisions, tiers, fair use, Paddle, guardrails |
| [PRD-Customer-Portal.md](PRD-Customer-Portal.md) | PRD | Contributors | Web-first customer flows, QR/code/widget entry, customer-side AI |
| [Delivery-Plan-Pre-Beta-to-Launch.md](Delivery-Plan-Pre-Beta-to-Launch.md) | Plan | Everyone | Beta blockers vs beta-phase vs pre-launch; launch gates; operating rhythm |
| [Backlog-Management.md](Backlog-Management.md) | Process | Contributors + stakeholders | Triage categories, trade-off rule, locked-decision filter |
| [Dev-Test-Strategy.md](Dev-Test-Strategy.md) | Process | Contributors | Test pyramid, AI-specific testing, environments, UAT smoke list |
| [Stakeholder-Communication-and-Documentation.md](Stakeholder-Communication-and-Documentation.md) | Process | Founder + stakeholders | Friday one-pager, dashboard surfacing, ADRs, doc ownership |
| [MyTradePortal-AI-Cost-Observability-Pricing-Strategy.md](MyTradePortal-AI-Cost-Observability-Pricing-Strategy.md) | Research | Reference | Evidence base: benchmarks, competitor pricing, model economics, citations |

## The three-question tour

- **What must be done before beta?** → Delivery Plan, *Phase 0* (ten items, each with a done-when).
- **How is beta run?** → Delivery Plan, *operating rhythm* + launch gates; Backlog doc for change control; Dev-Test doc for quality bar.
- **How do stakeholders stay informed?** → Stakeholder doc: Friday one-pager, three named dashboards, decision records.

## Locked decisions (challenge only with new evidence)

1. AI included unmetered on every plan — no credits, quotas, or overage.
2. Flat per-business pricing, unlimited users — no seats.
3. Tiers differ by capability, never capacity.
4. Customer portal is web-first; no app install on the customer critical path.
5. Observability before pricing finalisation — telemetry sets the launch dials.
6. Online payments are table stakes (Tradify parity) — pre-beta blocker, Stripe for receivables, Paddle for our subscription, no take-rate at beta.

## Action checklist

- [ ] Fill `[DECIDE]` placeholders in the K3 prompt (defaults inline) — final values at Phase 3.3
- [ ] Hand the K3 prompt to the coding agent; review its implementation plan
- [ ] Complete Phase 0 blockers before onboarding the first beta tradie
- [ ] Set up tracker per Backlog doc; run first fortnightly triage
- [ ] Send first Friday one-pager the week beta starts
