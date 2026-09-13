# Delivery Plan — Pre-Beta, Beta, Launch

| | |
|---|---|
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · Consumes: [PRD-Observability-Layer.md](PRD-Observability-Layer.md), [PRD-Pricing-and-Billing.md](PRD-Pricing-and-Billing.md), [PRD-Customer-Portal.md](PRD-Customer-Portal.md) |
| **Audience** | Internal contributors (delivery detail) and semi-technical stakeholders (phases + gates) |

## How to read this plan

Work is divided into **Beta Blockers** (must exist before the first beta tradie is onboarded), **Beta-phase work** (built while beta runs, in dependency order), and **Pre-launch work** (triggered by beta evidence). Nothing pre-launch starts before its evidence exists — the point of beta is that the numbers, not opinions, set the launch dials.

## Phase 0 — Beta Blockers (weeks 1–3)

| # | Item | Source | Done when |
|---|---|---|---|
| 0.1 | Event schema upgrade + logging helper (fail-open) | Obs PRD §4.1 | 100% of AI calls attributed; migration + backfill run |
| 0.2 | Feedback snapshots + async keep-rate pipeline | Obs PRD §4.2 | Keep-rate computable on new sent quotes |
| 0.3 | Outcome events (sent/accepted/paid) | Obs PRD §4.2 | Events flowing with trace_id |
| 0.4 | Nightly rollups + budget/anomaly alerts | Obs PRD §4.3 | Alert fires in test; rollup job failure alerts |
| 0.5 | Staff ops cost view | Obs PRD §4.3 | Per-org leaderboard visible |
| 0.6 | Tier feature-gate helper + fair-use guardrails | Pricing PRD §3.4 | Gates enforce; throttles configurable; nothing customer-visible |
| 0.7 | Fair-use policy page (threshold placeholder OK) | Pricing PRD §3.2 | Page live, linked from T&Cs |
| 0.8 | Trial logic + engagement extension | Pricing PRD §3.4 | Extension triggers on ≥3 sent AI quotes |
| 0.9 | Compliance: privacy notice covers AI processing + analytics + payment metadata; retention limits; access controls | Portal PRD §6, Payments PRD §3 | Reviewed and published |
| 0.10 | Beta comms pack: onboarding guide, expectations, founding-member terms | Stakeholder doc §3 | Sent to first cohort |
| 0.11 | **Online payments (Stripe Connect)**: tradie onboarding flow, pay button on invoice email/portal/PDF, webhooks → auto-mark paid, `invoice_paid` event, refunds (full), receipts | [PRD-Online-Payments.md](PRD-Online-Payments.md) | Sandbox E2E passes: invoice → customer pays → invoice auto-marked paid → tradie notified |

**Why these block:** items 0.1–0.5 are the measurement system — every day of beta without them is data we can never recover. 0.6–0.8 make flat pricing safe to operate. 0.9 is a legal precondition for capturing customer data. **0.11 is competitive table stakes — Tradify includes online payments on its Lite tier, so a beta without them fails parity on day one and forfeits the "get paid faster" story that justifies switching.**

## Phase 1 — Early Beta (weeks 3–6)

| # | Item | Notes |
|---|---|---|
| 1.1 | Onboard beta cohort wave 1 (5–10 tradies) | Recruit across trades; log entry into cohort register |
| 1.2 | Metabase + Langfuse docker services | Connect Metabase to rollups; traces flowing |
| 1.3 | Customer portal: entry surfaces (vanity URL, QR + asset pack, 6-digit code) | Portal PRD §4.1 |
| 1.4 | Customer portal: unauthenticated form + progressive registration + bot protection | Portal PRD §4.2 |
| 1.5 | Intake brief AI (post-verification only) | Portal PRD §4.3 |
| 1.6 | Weekly operating cadence begins | See §"Beta operating rhythm" below |

## Phase 2 — Mid Beta (weeks 6–10)

| # | Item | Notes |
|---|---|---|
| 2.1 | Portal home: timeline, quotes, invoices, chat + magic-link notifications | Portal PRD §4.2 |
| 2.2 | PWA install prompts | Baseline install rate |
| 2.3 | Embeddable widget + shareable link | Distribution surfaces live |
| 2.4 | Cohort wave 2 (10–20 tradies) | Only if wave-1 activation healthy |
| 2.5 | First calibration curve (ECE) + keep-rate by job type | Needs accumulated outcomes; informs routing levers |
| 2.6 | Cost-lever triage: prefix caching verified, output discipline, batch for nightly jobs | Pull levers whose data shows waste |

## Phase 3 — Late Beta / Pricing Evidence (weeks 10–14)

| # | Item | Notes |
|---|---|---|
| 3.1 | Van Westendorp interviews (15–25 beta users) | Founder-led; feeds final prices |
| 3.2 | p50/p95/p99 per-org AI cost, split staff/customer | The pricing arithmetic |
| 3.3 | Set final dials: tier prices, fair-use threshold, Pro feature gates | Replace `[DECIDE]` placeholders in Pricing PRD |
| 3.4 | Go/no-go review against launch gates | See below |
| 3.5 | Landing page pricing rewrite + fair-use threshold finalised | Pricing PRD §3.1–3.2 |
| 3.6 | Paddle catalog update (archive-not-delete) | Pricing PRD §3.3 |

## Launch gates (go/no-go, Phase 3.4)

| Gate | Threshold | If missed |
|---|---|---|
| Cost | p95 org AI cost ≤10% of tier price; IER ≥8:1 at p50 | Apply cost levers; move expensive features up a tier; re-review in 4 weeks |
| Quality | Line-item keep-rate ≥70% on top-3 job types; ECE measured | Market AI as "assist" not "automation"; delay Pro AI claims |
| Latency | p95 generation <30s | Routing/fast-path work before launch marketing |
| Adoption | ≥40% of trial users send an AI-drafted quote within 7 days | Fix activation funnel before spending on acquisition |
| Portal | ≥50% form-start→verified-submission | Fix form friction before QR asset rollout |
| Payments | ≥60% of beta tradies connected; online-paid invoices beating manual on days-to-paid | Fix Stripe onboarding friction before launch marketing claims |

## Beta operating rhythm (standing)

- **Daily (async):** budget/anomaly alerts triaged; nothing else — dashboards are T+1 by design.
- **Friday one-pager:** AI spend vs budget, keep-rate trend, p95 org cost, top-5 cost orgs, activation funnel, one Langfuse deep-dive into the week's worst drafts. Lightly edited → becomes the stakeholder update (see Stakeholder doc).
- **Fortnightly:** backlog triage (see Backlog doc); beta-user touchpoint (5 conversations minimum).
- **Monthly:** cost reconciliation (estimated vs provider invoice); pricing guardrail check; cohort retention review.
