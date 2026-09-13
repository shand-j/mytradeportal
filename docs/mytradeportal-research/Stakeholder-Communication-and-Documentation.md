# Stakeholder Communication & Documentation Standards

| | |
|---|---|
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · Cadence inputs: [Delivery-Plan-Pre-Beta-to-Launch.md](Delivery-Plan-Pre-Beta-to-Launch.md), [Backlog-Management.md](Backlog-Management.md) |
| **Audience** | Founder (how to run comms) · semi-technical stakeholders (what to expect and where to look) |

## 1. Audiences and what each gets

| Audience | Cadence | Artefact | Depth |
|---|---|---|---|
| Semi-technical stakeholders (investors, advisors, partners) | Weekly, Friday | One-page beta update (§2) | Numbers + narrative, no code |
| Internal contributors | Daily async / fortnightly triage | PR descriptions, triage notes, decision records | Full technical |
| Beta tradies | Fortnightly touchpoint + closed-loop on their requests | Plain-English email/call | Product language only |

## 2. The Friday one-pager (standing template)

Six lines, every week, same order — familiarity is the point:

1. **AI spend vs budget** — e.g. "£182 of £600 monthly budget; on track."
2. **Unit economics** — p50/p95 AI cost per org; IER trend arrow (▲▼►).
3. **Quality** — keep-rate trend; one sentence on what the worst drafts had in common.
4. **Adoption** — activation funnel (signup → first AI draft → sent quote); trial conversions.
5. **Shipped this week** — 3 bullets max, in user language ("customers can now…").
6. **Decisions needed / made** — what we need from stakeholders, or what was decided and why.

Rules: one page, no jargon without a gloss, every number links to its dashboard. The same artefact becomes the board update and the investor update — write once.

## 3. Surfacing technical outputs to semi-technical stakeholders

- **Dashboards over documents.** Metabase dashboards (money, quality, adoption views) with named, stable links. Stakeholders are trained on the three links once; after that the one-pager references, never re-explains.
- **Translate, don't dump.** Never paste logs, traces, or SQL into stakeholder comms. Langfuse traces stay internal; stakeholders get the *finding* ("consumer-unit drafts keep 82% of lines; boiler drafts 54% — we're improving the boiler prompts").
- **Cost in £, always.** Token counts are internal; stakeholders see £ per org per month and % of plan price.
- **Roadmap as phases and gates, not feature lists.** Show the Delivery Plan phase table and the launch gates. Stakeholders hold us to gates; they don't queue-jump features (that's the triage process's job).
- **Decision records for anything contested.** One paragraph: context, options, decision, evidence, reversibility. Filed in `/docs/decisions` (or the tracker), referenced in the one-pager.

## 4. Documentation standards for internal contributors

- **Location:** docs live next to code (`/docs` in repo) for technical content; PRDs and process docs live in this pack; the tracker holds task state. No fourth location.
- **PR standard:** what/why, link to tracker item, test evidence, migration notes, release-note line. Screenshots for any UI change.
- **Decision records:** short ADRs for architecture or product decisions (pricing model, web-first portal, fail-open logging). Immutable once accepted — superseded by new ADR, never edited.
- **Runbooks:** alert responses (budget 80%, anomaly, fair-use threshold, rollup job failure) each get a 5-line runbook: what it means, what to check, what to do, when to escalate.
- **API/schema docs:** the `ai_call_events` schema and event catalogue are documented in-repo and updated in the same PR as the change. Stale docs count as broken build in review.
- **Onboarding doc:** new contributor reads README → this pack's README → relevant PRD → runs staging smoke list. Target: productive in one day.

## 5. Document ownership

| Document | Owner | Reviewed |
|---|---|---|
| PRDs | Founder | At each phase boundary |
| Delivery Plan | Founder + lead dev | Fortnightly |
| Backlog process | Lead dev | Monthly |
| Dev-Test Strategy | Lead dev | Monthly |
| This document | Founder | Quarterly |
| Research report | — | Reference only; re-verify market figures at launch |
