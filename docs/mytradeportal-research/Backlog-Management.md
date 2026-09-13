# Backlog Management — Beta Change Control

| | |
|---|---|
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · Sequencing context: [Delivery-Plan-Pre-Beta-to-Launch.md](Delivery-Plan-Pre-Beta-to-Launch.md) |
| **Audience** | Internal contributors (process) · stakeholders (how requests are handled) |

## 1. Principles

- **Beta generates requests faster than we can build.** The backlog exists to protect the plan, not to park ideas forever. Everything is captured; little is committed.
- **Evidence over opinion.** Beta-phase priority comes from telemetry and direct user evidence, not loudest voice (internal or external).
- **The plan is the default.** Anything not in the Delivery Plan must displace something that is, explicitly.

## 2. Where things live

Single tracker (Linear/GitHub Projects/Notion — pick one, do not split). Every item carries: `source` (founder / beta user / telemetry / support), `evidence` (link to event, dashboard, or user quote), `area` (observability / pricing / portal / core), `type` (bug / change / idea), `severity` (below), dates, and a `decision` log entry when closed.

## 3. Triage categories

| Category | Definition | SLA / handling |
|---|---|---|
| **P0 — Beta-critical defect** | Data loss, billing error, broken core flow (quote send, customer submission), security/privacy issue, AI spend runaway | Drop everything; fix within 24–48h; postmortem note if user-visible |
| **P1 — Plan item** | Already in Delivery Plan phases | Scheduled per phase; re-sequenced only at fortnightly triage |
| **P2 — Evidence-backed improvement** | Request backed by ≥3 beta users or clear telemetry signal | Candidate for next fortnight; may displace P1 items by explicit trade-off |
| **P3 — Idea / single request** | One user, no data, or speculative | Parking lot; reviewed monthly; auto-close after 90 days with note (re-openable) |
| **Won't (recorded)** | Conflicts with locked decisions (e.g. AI metering, seat quotas, app-install gating) | Closed with reason referencing the decision record |

## 4. Rules that keep us honest

1. **Locked-decision filter.** Requests that reintroduce rejected models (metered AI, seat pricing, mandatory app install) are closed against the decision record in [PRD-Pricing-and-Billing.md](PRD-Pricing-and-Billing.md) / [PRD-Customer-Portal.md](PRD-Customer-Portal.md) — unless accompanied by new evidence (e.g. conversion data challenging web-first).
2. **Trade-off rule.** Accepting a P2 into a phase means naming what slips. Stakeholders see the swap in the fortnightly note.
3. **Batching.** Portal polish, copy tweaks, and small UI changes batch into one release per week. P0s ship immediately. Nothing else interrupts mid-week focus.
4. **Beta-user promises.** Never promise dates to beta users. Language: "logged and prioritising" or "not planned — here's why". Closing the loop with the requester when their item ships is mandatory (retention gold).
5. **Founder requests go through the same funnel.** Same fields, same triage. The fortnightly review is the only priority-setting forum.

## 5. Fortnightly triage agenda (30 min)

1. P0 review — any patterns? (recurring P0s = missing test or missing guardrail)
2. Telemetry check — what does the data say users actually struggle with?
3. P2 candidates — evidence presented, trade-offs named, phase placement decided
4. P3 purge — monthly: close stale, promote emerging patterns
5. Stakeholder summary — 5-line note of what changed in priority and why

## 6. Post-launch transition

At launch, P3 parking-lot items with fresh evidence feed the post-launch roadmap; the fair-use/IER guardrail review becomes a standing monthly agenda item; the backlog process continues unchanged — it is deliberately the same at 10 and 10,000 users.
