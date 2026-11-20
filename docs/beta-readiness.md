# Beta readiness and release decision

Last reviewed: **2026-11-21 (full rebaseline, refreshed after #391/#382/#404)**. Review baseline: `99e532d` on `main`.

This is the current source of truth for beta scope and go/no-go decisions. The
[GitHub Beta project](https://github.com/users/shand-j/projects/4) and master
issue #12 own execution state. [Beta test plan](beta-test-plan.md) owns the
verification procedures; [go-live runbook](go-live-runbook.md) owns deployment
and recovery actions. ADRs, the Beta PRD, feature files, and older runbooks are
historical/design context where they conflict with this document.

## Current decision: NO-GO

Do not start a broad or paid beta. A small, free, concierge-led cohort may be
authorised only after every applicable gate below has current evidence. Until
then, all release blockers remain open even if their implementation code has a
green PR.

The current baseline has green main CI ([run
44879790143](https://github.com/shand-j/mytradeportal/actions/runs/44879790143)).
Production deployment `9c800527` and the recovered staging API deployment
`6105b67d` are successful, with `/health` and `/ready` passing in both
environments on 2026-11-21. Current-SHA staging E2E ([run
44879790207](https://github.com/shand-j/mytradeportal/actions/runs/44879790207))
is red because its fresh API deployment failed; a manual redeploy recovered
readiness but does not make that E2E run a pass. The preceding #391 run
([44879575868](https://github.com/shand-j/mytradeportal/actions/runs/44879575868))
exposed missing Mailpit networking, VAT fixture failures (#369), and AI provider
timeouts (#429). Staging Mailpit now has authenticated UI/API and SMTP evidence,
but the complete suite must still be rerun. The weekly security audit still fails
before pytest because required credentials are missing; that is a
harness/configuration failure, not an OWASP or tenancy pass and not by itself a
confirmed product vulnerability.

## Target beta scope

The initial cohort is 3–5 known businesses with hands-on onboarding and support.
In scope:

- tradesperson onboarding, branding, and basic team/seat behaviour;
- customer quote intake and human-reviewed AI-assisted quotes;
- quote acceptance, date preferences, jobs, scheduling, invoices, and manual
  bank-transfer reconciliation;
- customer portal/email/token journeys and Stripe Connect card payments only
  after their live gates pass;
- the notifications and calendar journeys explicitly verified in the beta test
  plan.

Out of scope for this beta:

- paid SaaS subscriptions and Paddle checkout; Paddle must be disabled by the
  server-controlled `paddle_billing` feature flag before release;
- digital certificate issuance and any claim of server-persisted certificates;
- real offline operation or claims that offline work has been synchronized;
- deposits/partial payments, accounting integrations, voice features, and BoQ;
- operational alert delivery and new operational-alert work (#62 is post-beta).

The presence of a screen, prototype, parked endpoint, or historical document is
not evidence that a capability is in beta scope.

## Evidence rules

- A passing check must identify the commit, environment, date, and command or
  workflow run. Code inspection alone cannot close a live-provider or device
  gate.
- Automated provider tests use mocks or locally signed payloads. They do not
  replace live Stripe, Telnyx, APNs, calendar, or restore evidence.
- Manual evidence records device/build or environment, steps, observed result,
  and a sanitized artifact. Secrets, tokens, customer PII, and real card data
  must not enter tickets or committed evidence.
- A failing or unexecuted check remains open. Do not weaken a test or redefine
  the scope silently to obtain a pass.
- Current-SHA main CI, deployment readiness, PR preview, and staging E2E must be
  refreshed after release changes; an old green run is not a current pass.

## Release gates

### G1 — Documentation and tracking

`docs/beta-readiness.md`, the Beta project, and master issue #12 agree on scope,
owners, dependencies, and decision criteria. Every blocker has a named owner.
Confirmed review defects are ticketed; unverified reports remain explicitly
unverified. Operational alerts are outside the critical path.

### G2 — Application and dependency security

Issue #52 has a completed production OWASP/tenancy run against dedicated test
tenants, with sanitized run evidence. There are no unresolved critical/high
findings. Lower-severity findings are fixed or have documented risk acceptance.
Dependency audit #53 has no unaddressed high/critical finding. A workflow that
fails configuration or test collection is not a pass.

### G3 — Free-beta billing behaviour

`paddle_billing=false` is verified in staging and production. Paddle checkout,
plan changes, portal sessions, price previews, and other provider calls are not
initiated. Delayed Paddle events cannot mutate beta access. Incomplete,
expired, canceled, and past-due subscription rows cannot lock a beta tenant out.
Plan/seat reads, authentication, active-tenant enforcement, and Stripe payments
continue to work.

### G4 — Restore capability

An isolated, non-destructive drill restores PostgreSQL and recovers or rebuilds
object storage and Qdrant. The recovered API passes `/ready`, schema/RLS and
tenant-isolation checks, representative quote→job→invoice reads, and media
retrieval. Evidence demonstrates **RPO ≤24 hours** and **RTO ≤60 minutes**.
Restored PII is protected and offboarding anonymisation is reapplied as required
by [data retention](data-retention.md). Production is never overwritten for the
drill.

### G5 — Stripe or an explicit bank-transfer-only release

The intended card-payment gate requires #115, #44, #45, #32, and webhook safety
#30: Connect enrollment, production configuration, physical-device onboarding,
a small real-card payment, automatic settlement, and a full refund with correct
final state.

If any of those remain open, card payments are **no-go**. A core beta may still
be considered only with an explicitly documented bank-transfer-only release and
no misleading card-payment claims for unconnected tenants. Bank transfer is not
evidence that Stripe works.

### G6 — Money and webhook correctness

VAT create/update behaviour is consistent for registered and non-registered
tenants, zero-rated documents, upper-limit rejection, rounding, persistence,
and quote→invoice inheritance. The mobile save-then-send path surfaces rejected
edits instead of creating an unsendable quote.

Stripe, Paddle, and Telnyx failure-injection tests prove transient handler
failures remain retryable, successful retries settle once, completed duplicates
are no-ops, and refund/dispute ordering remains safe. No event may be marked
permanently processed before handling succeeds.

### G7 — Device and live communications

One current TestFlight build has passing evidence for:

- push delivery in foreground/background/terminated states and exactly-once tap
  routing (#92);
- live customer/staff SMS, delivery receipts, STOP/START, and fallback;
- cold/warm, authenticated/logged-out deep links, notification/magic/reset/
  invite/Stripe/document routes;
- Apple Calendar branded webcal/HTTPS subscription, updates, cancellations,
  revocation, and tenant isolation (#36; close #181 only on evidence);
- the remaining device checklist #102, with Paddle checkout replaced by
  free-beta/no-paywall verification.

### G8 — Legal and compliance publication

Legal/compliance has approved the Terms of Service, Privacy Notice (#69),
Beta/Founding Member terms (#70), Fair Use (#83), payment/refund/dispute and
retention/AI/analytics disclosures. The
[beta comms pack](beta-comms-pack.md) assembles the onboarding guide,
expectations, and approved founding terms; send completion is logged in the
[cohort register](beta-cohort-register.md). Approved documents are publicly reachable
and linked from marketing, onboarding, portal, payment/document, and relevant
mobile surfaces. Copy matches free-beta, Paddle-disabled, Stripe/bank-transfer
behaviour. Engineering prose is not legal approval.

### G9 — Current release health

Current-SHA CI, deploy readiness, PR preview, and staging E2E pass. Existing
startup/auth refresh #313, storage #315, IaC #319, staging #78, scheduling #296,
and other issues labelled `beta-blocker` are closed or carry an explicit scope
exception in the final review. No blocker is omitted because it was discovered
before this reset.

## 2026-11-21 rebaseline scorecard

`PASS` means the gate has current evidence; `IN PROGRESS` means evidence is
partial or a run is pending; `BLOCKED` means a defect or required evidence is
missing. A green implementation PR alone never closes a live gate.

| Gate | Status | Current evidence and remaining work |
|---|---|---|
| G1 | IN PROGRESS | This rebaseline updates the tracker. Copilot and the owner are assigned to every action. CI/reproducibility additions are #76 and #377. |
| G2 | BLOCKED | #52 has no production OWASP/tenancy verdict and required dedicated test-tenant secrets are absent. #427 confirms raw LLM provider exceptions cross API/UI boundaries and must be sanitized. Node audit passes (30 findings, four high ignored); Python reports 174 advisories across 20 packages and the nested landing audit reports 11 fixable highs, requiring triage in #53. |
| G3 | PASS | Railway Signals has no entries, so `paddle_billing` defaults false. Production `/` and `/subscribe` show free-beta copy and make no `paddle.com` requests; delayed/cancelled events do not lock access out. #322 stays open only for the current staging-suite run URL before final sign-off. |
| G4 | BLOCKED | #323 has runbook/validation only. No isolated production restore, RPO/RTO measurement, media/Qdrant recovery or teardown evidence exists. Fresh-volume storage provisioning remains #315. |
| G5 | BLOCKED (card path) | #44, #45 and #32 are reopened because current configuration, device KYC and real-card evidence is absent. #355 needs owner/legal liability approval. #30 is a confirmed webhook-safety defect. Bank-transfer-only remains an alternative, not evidence for Stripe. |
| G6 | BLOCKED | #30: Stripe, Paddle and Telnyx all write their dedupe record before handler success, so a transient failure can become a permanent `duplicate`. #369 tracks non-VAT fixtures that currently block staging journeys; #387 requires write-side money/schedule invariants after reproduced invalid inputs; #388 covers duplicate invoice-from-job creation. VAT #324 has automated regression coverage; device VAT save/send evidence belongs to G7. |
| G7 | BLOCKED | No single current TestFlight build has the full matrix. #36, #92, #325 and #326 were reopened. #102 remains open; #181 needs Apple Calendar device proof; #313 refresh-loop is unverified and a hard fail if reproduced. |
| G8 | BLOCKED | `/terms` and `/privacy` are placeholders, not approved documents. #327, #69, #70 and #83 require legal/compliance approval and publication/link evidence. `/fair-use` content matches current ~500/month cheap-route/no-hard-block behavior but still needs approval. |
| G9 | IN PROGRESS | Main CI and production/staging readiness pass, but current-SHA staging E2E `44879790207` failed at API deployment. The preceding #391 run found missing Mailpit networking, VAT fixture failures (#369), and AI provider timeouts (#429). Mailpit is now restored and authenticated, but no complete rerun has passed. #373 tracks pricing scope drift; #405 blocks quote/invoice PDF downloads; #427 requires safe provider errors. #313 and #315 remain open; #382 landed bounded CI/stale-run handling and #377 still needs deterministic landing installs/builds. #378 is post-beta only because `web/app` is parked. |

### Additional confirmed findings

- `services/api/app/routers/stripe_webhooks.py:256`, `webhooks.py:257`, and
  `telnyx_webhooks.py:334` confirm the early-completion webhook defect (#30).
- PR #333 added legal routes and links only; production snapshots show explicit
  “approved wording is pending” placeholders (#327).
- `.railway/.railway/railway.ts` is a stale duplicate containing deleted
  web/OCERP resources and invalid MinIO startup configuration. Persistent
  RustFS environments are healthy, but fresh PR volumes required manual
  ownership repair; both belong to #315.
- Exploratory QA run `hunt-2026-11-20T22-42-01` at `485841e` recorded 31 raw
  findings (3 Critical, 1 High, 22 Medium, 5 Low), grouped into 18 non-overlapping
  Copilot assignments. In addition to the release blockers in the scorecard, it
  confirmed #370/#371 (test/lint harness), #388 (duplicate invoices),
  #406/#407/#409 (parked web back-office), #411/#413/#415/#417 (landing/portal),
  and #419/#421/#423 (mobile auth/onboarding). The production public AI demo
  passed in 6.1s and offline evals passed 15/15; neither offsets the staging and
  native-device gates. The run's sanitized evidence remains under
  `reports/qa/hunt-2026-11-20T22-42-01/` (gitignored).
- The local full suite recorded 1,311 passes plus two database-connection
  resets, and both failed tests passed on rerun. Main CI is the authoritative
  current-SHA green run. The QA run recorded 163 web unit tests and web
  lint/build passing; a separate local production build failed under Vite
  8.3.5/lightningcss (#378), so that result is environment-specific rather than
  a reproducible-build pass. Landing build/type checks and mobile TypeScript
  passed, while landing lint has 33 errors (#370). The parked `web/app` build
  work remains post-beta.
- `pip-audit` is report-only and does not provide severity metadata here. Its
  174 findings require triage, not an assumption that every item is critical or
  that the current tree is safe (#53).

### Release paths and required order

**Recommended shortest path — bank-transfer-only.** Complete G1–G4, G6–G9 and
manual bank-transfer/mark-paid verification. Keep card-payment claims disabled
for unconnected tenants and make the restriction explicit in onboarding,
invoice/payment surfaces and approved legal copy. This path does not require a
real card, but it still requires webhook failure-injection (#30), restore,
security, current-build device and legal evidence.

**Card-enabled path.** Complete every bank-transfer requirement plus #355 owner/
legal approval, #44 production configuration, #45 device onboarding, and #32
real-card payment/refund. No real-money test should occur before those approvals
and webhook safety are in place.

Execute in this order:

1. Rebaseline documentation/tracking and CI reproducibility (#315, #377; #382
   landed the stale-run/bounded-runtime work).
2. Production application security and dependency triage (#52, #53), provider-error
   sanitisation (#427), then webhook failure safety (#30), duplicate-invoice
   prevention (#388), and reproduced write invariants (#387).
3. Close free-beta billing evidence (#322) and align public pricing (#373) after
   the current staging suite; repair VAT fixtures (#369), PDF downloads (#405),
   and AI staging paths (#429) rather than excluding their failures.
4. Execute the isolated restore drill (#323).
5. Either approve bank-transfer-only or complete the Stripe chain
   (#355 → #44 → #45 → #32).
6. Complete VAT/device/webhook/push/SMS/deep-link/calendar verification (#102,
   #36, #92, #181, #313, #325, #326).
7. Obtain legal approval and publish/link the complete pack (#69, #70, #83,
   #327), then run the final #105 review with exact release SHA and TestFlight
   build.

## Final decision record

Issue #105 is the final review. It must link evidence for G1–G9 and record one
of:

- **GO — free concierge beta:** all applicable gates pass; cohort remains small
  and paid/broad launch stays closed.
- **GO WITH SCOPE RESTRICTION — bank transfer only:** every non-card gate passes
  and the card-payment restriction is explicit.
- **NO-GO:** any required gate lacks evidence, has an unresolved blocker, or is
  outside the documented scope exception.

A successful beta review does not authorise paid Paddle subscriptions, broad
availability, operational-alert completion, or any excluded feature.
