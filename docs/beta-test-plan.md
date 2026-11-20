# Beta Test Plan — My Trade Portal

*Current verification map for the free concierge beta. Release scope and the
go/no-go decision live in [beta-readiness.md](beta-readiness.md); execution
state lives in the GitHub "Beta" project and master issue #12.*

Scope: everything that must be verified before and during beta. Each area states
what is **automated** (runs without human action, and where) versus **manual**
(device/live verification, and why it stays manual for now). Paddle checkout and
paid subscriptions are not beta scope. Operational alert delivery is post-beta.

Environments: local (native postgres + Docker stack), CI (GitHub Actions),
PR previews (Railway forks of staging), staging, production, TestFlight device
builds.

---

## 1. Automated coverage

### 1.1 API test suite (pytest, ~1,160 tests)

Runs: locally on every change, in CI on every PR/push (`ci.yml` python job),
against native Postgres with RLS genuinely enforced (non-superuser role).

| Area | Coverage |
|---|---|
| Multi-tenancy | RLS isolation, `X-Tenant-ID` mismatch → 403, GUC checkout listener, cross-tenant push-token re-pointing |
| Auth & users | login, onboarding-created admins, case-insensitive email, invite tokens (single-use, TTL, revoke-on-reissue), seat limits per plan, blocked-customer enforcement (login, intake, chat, read surfaces, pre-block tokens) |
| Quotes | lifecycle (draft → sent → accepted/declined), AI generation (mocked LLM), refinement (120s budget + fast-model route), rounding integrity on every read endpoint, convert-to-job incl. draft adoption, date preferences (availability endpoint leaks no booking details) |
| Jobs & scheduling | create/start/complete, assignment auto-default on single-seat plans, dispatch guardrails (overlap 409, boundary touch allowed, 10h/day cap, in-progress/completed lockdown), multi-day work blocks |
| Invoices & payments | create/issue/send, quote-line prefill, Stripe destination-charge PaymentIntents, webhook settlement, refunds, portal pay endpoint (200 payment_url / 409 unavailable), payment-details fallback, Stripe bounce-URL substitution |
| Billing | plan catalog + seats, checkout transaction creation, cardless-trial flow, plan-change proration, dunning follow-ups, fair-use guard (burst 429, monthly threshold, deduped staff alert), offboarding (deactivation, token revocation, PII scrub, financials preserved) |
| Notifications | push send + receipt checking (DeviceNotRegistered cleanup, InvalidCredentials alerting), notification rows, reminder scheduler (cadence, max count, per-contact overrides, failure isolation) |
| Email | templates (tenant branding incl. reminder CTA colour), tenant Reply-To, failure alerting per (tenant, contact, day), Resend webhook (bounce/delivery), magic links |
| SMS (Telnyx) | E.164 normalisation, sender-ID normalisation, single-segment fitting, window firing + dedupe, fair-use degrade-to-email, inbound webhook (ed25519 verification, delivery receipts, STOP/START opt-out) |
| AI pipeline | retrieval/generation/validation, vision captioning (fail-open), observations on QuoteRead, intake triage timeout, eval-harness fixtures (offline) |
| Files/media | upload validation, photo carryover quote→job (both storage shapes), tenant logo (type/size validation, public serve, delete) |
| Public URL surface | every public link resolves on mytradeportal.co.uk (document tokens, portal magic links, Stripe bounce, triage/welcome emails) |

### 1.2 Static and schema gates (CI)

- `ruff check` + `ruff format --check` on all Python.
- `mypy` strict across `services/api` **including tests** (200+ files).
- Schema-sync idempotency job: `init_db.py` runs twice against fresh Postgres,
  asserts no missing columns on the second pass, and re-adds a dropped column
  (guards the no-Alembic schema model).
- Dependency audit: `pnpm audit --audit-level=high` hard gate (4 documented
  deferrals allow-listed); `pip-audit` report-only.
- `tsc --noEmit` for mobile and landing; `npm run build` for landing.

### 1.3 Browser automation (Playwright)

- **PR preview smoke** (`pr-verify.yml`, every PR): Railway preview env comes up,
  `/health` ready, landing quote-page bogus-token terminal state, tenant-brand
  accent, quote-request submit. Preview envs run schedulers disabled and call
  their own api.
- **Landing/portal e2e** (`web/landing .../e2e/`): auth/claim chains (incl. the
  booking-email claim CTA chain), intake attribution, gating.
- **Mobile e2e** (`mobile/e2e/*.spec.ts`, Playwright driving the web build):
  regression suite (signup wizard incl. bank-details + card-gate steps, G-series
  journeys), blocked-customer enforcement (G31), messages/notifications (incl.
  N24 empty inbox), jobs, invoices, CRM, onboarding. Runs against a live backend
  (local stack or staging).

### 1.4 Device automation (Appium, on-demand)

Real-device waves drive the iOS app end-to-end (quotes, jobs/calendar, CRM,
messages, notifications, settings, follow-ups, lifecycle → invoice send).
Run on demand against production. Not in CI (requires a physically attached
device).

### 1.5 Security & evals

- **Security suite** (`security/`, weekly cron Mon 06:17 UTC + manual dispatch):
  OWASP and tenancy tests against a live target (needs `SECURITY_*` credentials).
- **AI eval harness** (`services/api/evals/`): offline golden-set replay in CI;
  `--live` against the real LLM is a manual trigger (cost + flakiness by design).

---

## 2. Journey matrix — automated vs manual

| # | Journey | Automated | Manual residue |
|---|---|---|---|
| 1 | Electrician onboarding (account → business → bank details → card gate → plan) | e2e signup spec walks the full wizard; email-availability API tests; duplicate-email jump-back; linear single-pass | First-run UX on device; Stripe Connect in-app browser round-trip per tenant |
| 2 | Electrician payment setup (Stripe Connect) | account v2 payload prefill (incl. portal URL as website), bounce-URL substitution, status auto-sync | Hosted onboarding completion in Stripe's UI; sandbox verification of prefill fields |
| 3 | Free-beta access (Paddle disabled) | both flag states, no provider calls, delayed-webhook isolation, expired/canceled access | Fresh tenant and legacy inactive-subscription tenant reach dashboard without Paddle or paywall |
| 4 | App config / branding | colour settings round-trip, logo upload + public serve tests | Picker UX on device; logo rendering across portal/pay/quote pages |
| 5 | Sharing code / invites | invite API, seats, tokens, email send, accept flow | End-to-end invite on device (needs `TESTFLIGHT_URL` set) |
| 6 | Quote request (public intake) | public endpoint tests, entry_channel persistence, block enforcement, triage | Live form on the landing site |
| 7 | Quote review & refinement | lifecycle + refine tests (budget, fast model), rounding on every surface | Screen UX on device (keyboard, consolidated actions), refine latency on prod |
| 8 | Quote accept / decline (customer) | acceptance tests, date preferences, draft-job creation, notification content | Magic-link journey in a real browser/email client |
| 9 | Job scheduling & rescheduling | availability math, guardrails (overlap/cap/lockdown), suggestion endpoint | RN date/time wheel (automation-blind — no AX exposure) |
| 10 | Job start / close / invoice | lifecycle tests, guardrail lockdown, invoice prefill | Device walkthrough of the happy path |
| 11 | Invoice payment (customer) | pay endpoint contract, PaymentIntent mint, webhook settle, paid-state gating | Card entry in Stripe elements (sandbox 4242), real-card go-live gate |
| 12 | Quote & invoice follow-ups | reminder scheduler (cadence, caps, per-contact overrides), branded templates | Deliverability/spam watch on real mailboxes |
| 13 | Job reminders — customer (SMS/email) | reminder windows, fair-use degrade, STOP opt-out, failure alerts | Live SMS to a real handset (needs Telnyx keys) |
| 14 | Job reminders — electrician | staff SMS + push, dedupe | Background push delivery on device (APNs) |
| 15 | Calendar | assignee filter, feed endpoints, All/Me UI logic | iOS Calendar subscription round-trip (needs branded feed domain); wheel-driven reschedule |
| 16 | Multi-user (invites, assignment, seats) | seats enforcement, auto-assign, picker gating, All/Me | Second-user device pairing |
| 17 | Tenant offboarding | deactivation, revocation, scrub, financials preserved | — |
| 18 | Notifications | send/receipt tests, in-app dedupe logic | Background delivery + tap routing + no-double-fire on device |
| 19 | GPS navigation links | URL builder unit-level (tsc) | maps:// handoff on iOS, geo: on Android |
| 20 | Photo-conditioned AI quotes | captioning unit/integration tests (mocked) | Real photo → visible observations on prod (needs `LLM_VISION_MODEL`) |

---

## 3. Required beta regression additions

### 3.1 VAT matrix

Run API tests for registered and non-registered tenants against both quote and
invoice create/update paths. Cover omitted/default VAT, zero-rating, restoring
the tenant rate, a rate above the tenant limit (400 with no mutation), rounding,
re-fetch persistence, quote→job→invoice inheritance, scratch invoices, and no
retroactive change after quote edit. Explicit client VAT may lower/remove VAT
but never exceed the tenant's registered rate; for a non-registered tenant every
positive rate is invalid on create as well as update.

Run the mobile QuoteEditScreen save-then-send journey for standard and zero-rated
quotes. A rejected edit must be visible and recoverable; it must not leave a
silently saved quote that cannot be sent.

### 3.2 Webhook failure injection

Using only signed local fixtures/mocks, cover Stripe, Paddle, and Telnyx:

- failure before processing, during the handler, after an idempotent side effect,
  and around completion marking;
- transient failure returns retryable non-2xx and the identical provider retry
  subsequently processes once;
- completed duplicate and concurrent duplicate delivery cause no duplicate
  settlement, email, notification, opt-out, or other side effect;
- refund/dispute ordering cannot resurrect an incorrect paid state;
- while `paddle_billing=false`, a valid delayed Paddle event is acknowledged
  without mutating subscription/access state and without a Paddle API call.

A handler failure must never be converted into a permanent `duplicate` response.
No live provider calls or operational-alert assertion belong in CI.

### 3.3 Paddle-disabled free beta

Test both flag states plus registry timeout/failure. With the flag off, verify
no Paddle.js initialization or outbound Paddle call, stable disabled responses
from Paddle-initiating endpoints, free-beta onboarding/settings/landing copy,
and active access for incomplete/expired/canceled/past-due subscription rows.
Valid delayed webhooks cannot lock out a tenant. Plan/seat reads, tenant active
status, authentication, and Stripe payment tests remain green. With the flag
explicitly on, existing billing tests must retain their prior behaviour.

---

## 4. Stays manual for now (and why)

| Item | Why |
|---|---|
| Real-card payment (go-live gate, #32) | Requires live Stripe keys + a real card + refund; test-mode 4242 covers everything automatable |
| Background/terminated push on device (#92) | APNs delivery cannot be simulated; tap routing and exactly-once navigation need the installed app |
| RN date/time wheel reschedule | The wheel renders no XCUITest tree — automation cannot drive it; needs RN-side AX work |
| Customer CodeInput | No accessibility exposure in the current build; test via UI |
| `mtp://` deep links | Cold/warm scheme routing needs a real install, not a simulator-driven web build |
| Live SMS (Telnyx) | Needs provisioned number + keys, a real handset, delivery receipts, and STOP/START |
| Stripe hosted onboarding completion (#45) | Stripe-owned KYC UI; our prefill is verified at the payload level |
| Isolated restore drill | Requires real restore points and recovered infrastructure; never overwrite production |
| Weekly UAT smoke on staging | Human judgment pass over the checklist |
| Van Westendorp pricing interviews | Research, not verification |
| Legal approval + beta comms | Legal/compliance supplies and approves wording; engineering does not |

For every manual run record environment, date, device/iOS/TestFlight build where
applicable, steps, observed result, and sanitized evidence under
`reports/qa/<runId>/`. Put the dated result and evidence reference in the
relevant GitHub issue. An unexecuted check is `unverified`, never `passed`.

---

## 5. Release-gate checklist (per TestFlight build)

Automated before the build: current-SHA CI green on main (Python, mobile,
schema-sync), PR preview and staging E2E green, plus the VAT, webhook, and
Paddle-disabled matrices above. Confirm `paddle_billing=false` in staging and
production without making a Paddle call.

Manual on the build:
1. Onboarding: fresh tenant → bank details → card gate (skip and complete) → free-beta plan/access → dashboard (single pass, no Paddle or paywall bounce)
2. Push: foreground/background/terminated delivery; background AI quote completion → tap → correct quote, zero repeat navigation/banners
3. Deep links: cold/warm and logged-in/out coverage for notifications, magic/reset/invite, Stripe return, quote and invoice targets
4. SMS: customer + staff delivery to real handsets, delivery receipt, STOP/START, and configured fallback
5. Refine a quote (fast, no timeout), review screen UX with keyboard open; run the VAT save-then-send cases
6. Logo upload in branding settings; verify on a public quote page
7. Invoice lifecycle to sent. If Stripe gates pass, customer pays a small live amount via `/pay`, PAID state settles automatically, then a full refund reconciles. Otherwise record the release as bank-transfer-only and verify manual mark-paid.
8. Stripe Connect setup from Settings → Payments on a physical device (#45), including return to the app and "accepting cards" only after live status sync
9. GPS nav link on a job card opens maps
10. Calendar All/Me + guardrail rejection toast; subscribe through branded webcal/HTTPS in Apple Calendar and verify initial events, updates, cancellation, revocation, and tenant isolation
11. Complete the remaining reset/convert/photo checks in #102 and the isolated restore drill before the go/no-go review

The final decision and evidence index belong in #105, using the gates in
[beta-readiness.md](beta-readiness.md).
