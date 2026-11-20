# Beta readiness and release decision

Last reviewed: **2026-11-20**. Review baseline: `485841e34fad383d5c3c4a3bc7b31cbc299da0` on `main`.

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

The baseline had green main CI ([run
44712067008](https://github.com/shand-j/mytradeportal/actions/runs/44712067008)),
but this is not release evidence for later commits. The weekly security audit
was failing before pytest because required credentials were missing; that is a
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
retention/AI/analytics disclosures. Approved documents are publicly reachable
and linked from marketing, onboarding, portal, payment/document, and relevant
mobile surfaces. Copy matches free-beta, Paddle-disabled, Stripe/bank-transfer
behaviour. Engineering prose is not legal approval.

### G9 — Current release health

Current-SHA CI, deploy readiness, PR preview, and staging E2E pass. Existing
startup/auth refresh #313, storage #315, IaC #319, staging #78, scheduling #296,
and other issues labelled `beta-blocker` are closed or carry an explicit scope
exception in the final review. No blocker is omitted because it was discovered
before this reset.

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

### Rebaseline decision — 2026-11-20

**Decision: NO-GO.** The evidence collected at the current main-SHA rebaseline
does not satisfy every applicable gate. This is not an authorisation for a
card-enabled or paid launch.

- **Release baseline:** `485841e34fad383d5c3c4a3bc7b31cbc299da0`
- **TestFlight build:** unverified — no current-build identifier or completed
  device evidence is recorded.
- **Scope:** no release restriction may be claimed yet. A later bank-transfer-
  only decision requires every non-card gate to pass.

| Gate | Status | Evidence / residue |
|---|---|---|
| G1 | UNVERIFIED | Issue #105 is the decision record, but the docs/project/master-issue alignment and blocker/dependency linkage were not reverified as complete. |
| G2 | OPEN | #52 has no production security verdict and is reopened. #53 is reopened for dependency-advisory triage; the Node audit passed. |
| G3 | PASS | #322 is implemented under Paddle off mode. No Railway Paddle Signals entries are configured, staging/production default off, and live `/` and `/subscribe` render free-beta copy without `paddle.com` requests. |
| G4 | OPEN | #323 isolated restore drill is unexecuted; RPO and RTO remain unverified. |
| G5 | OPEN | Stripe live-chain issues #115, #44, #45, and #32 remain open. Card payments are not authorised. |
| G6 | OPEN | VAT #324 and webhook-failure injection #30 remain open or unverified; #30 also remains a confirmed cross-provider dedupe defect. |
| G7 | OPEN | Push #92, SMS #325, deep links #326, calendar #36/#181, and device #102 lack the required current-build evidence. |
| G8 | OPEN | Legal/compliance #327 and linked approval/publication issues #69, #70, and #83 remain open. |
| G9 | OPEN | Main CI [44830578492](https://github.com/shand-j/mytradeportal/actions/runs/44830578492) passed at `485841e`. Staging E2E [44830578607](https://github.com/shand-j/mytradeportal/actions/runs/44830578607) failed on Mailpit drift. #391 addresses that root cause; #315, #313, #319, #296, #78 and all remaining beta blockers require resolution or explicit scope exceptions. |

Additional current evidence:

- [Main CI 44826651558](https://github.com/shand-j/mytradeportal/actions/runs/44826651558)
  passed deploy/session fixes at `5309bb4`.
- [PR #392](https://github.com/shand-j/mytradeportal/pull/392) contains the
  full rebaseline.
- [PR #391](https://github.com/shand-j/mytradeportal/pull/391) contains the
  staging IaC follow-up.

Unexecuted or failing checks remain unverified and must not be recorded as
passes. The [restore drill runbook](runbooks/restore-drill.md) and
[beta test plan](beta-test-plan.md) remain the procedures for G4 and G7–G9
manual residue.
