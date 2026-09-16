# E2E coverage gaps & proposed test plan (beta)

**Date:** 2026-09-16 · **Status:** analysis complete, tests not yet written
**Sources:** `docs/features/*.feature` (17 journey specs), `docs/mytradeportal-research/`
(PRDs + Delivery Plan), `docs/beta-backlog.md`, git diff 2026-09-07→09-16, full
read of `mobile/e2e/`, `web/app/e2e/`, `services/api/tests_deployed/`.

The mobile regression suite (34 tests) landed 2026-09-12; the `web/app` suite is
stale since 2026-07-25 (old back-office flow); the landing/portal app has **zero**
e2e specs. Most beta-critical functionality landed *after* the tests were written.

## How to read this

- **Priority** follows the Delivery Plan: **P0** = beta blocker (Phase 0),
  **P1** = beta-phase, **P2** = post-beta. Feature-file tags (`@p0/@p1`, `@manual`)
  are cited per row.
- **Suite** = where the test should live:
  - `mobile-staging` — `mobile/e2e/*.spec.ts` via `playwright.config.staging.ts`
    (Expo web build vs live staging API; has per-test tenant seeding + Mailpit).
  - `portal` — new Playwright suite over the landing/portal bundle (extend the
    `web/app/e2e/pr-env/` pattern / `TEST_LANDING_URL`); zero specs exist today.
  - `deployed-smoke` — `services/api/tests_deployed/` (pytest vs PR/staging API).
- Every email assertion uses the shared **Mailpit** helper (`mobile/e2e/mailpit.ts`
  pattern) — zero Resend cost on lower envs (see `docs/ci-pr-environments.md`).

## Blockers / preconditions — STATUS UPDATE 2026-09-16 (evening)

| # | Blocker | Status |
|---|---|---|
| B1 | **D1 — Gmail bouncing all mail** (DKIM/SPF/DMARC suspect) | Still open (P0, production). Irrelevant to staging email asserts — Mailpit captures everything. |
| B2 | **D4 — Stripe Connect platform enrollment** | **RESOLVED.** Verified live on staging 2026-09-16: `POST /payments/connect` → 200 with a real test-mode account-link (`connect.stripe.com/setup/e/acct_…`). The raw-500-on-error contract cleanup remains open but no longer blocks. |
| B3 | **Stripe sandbox keys** | **Already present on staging api**, byte-identical to production (`sk_test_…`, webhook secret, connect client). No action needed. |
| B4 | **Paddle sandbox on lower envs** | **Already present on staging api + landing** (`PADDLE_SANDBOX=true`, full catalog, `VITE_PADDLE_ENV=sandbox`). No action needed. |
| B5 | **Portal origin in tests** | **Strategy decided** — see "Portal test strategy" below. Zero-infra option exists (`?slug=` override, already in `host.ts`). Also fixed staging landing `VITE_API_URL` which incorrectly pointed at the **production** api. |
| B6 | `ENTITLEMENTS_ENABLED` kill switch | **OBSOLETE** — the 402 allowance gate was removed in the flat-unmetered pricing pivot (`28a01f5`). `require_ai_allowance` is now a shim that only applies the *invisible* fair-use guardrail. See "Entitlements — what actually exists" below. |

### Portal test strategy (B5)

`web/landing/.../src/portal/host.ts` resolves the tenant slug with these
overrides, in priority order:

1. **`?slug=<slug>` query param** — forces portal mode for any host.
2. `VITE_PORTAL_SLUG` env — forces portal mode for a whole dev/build.
3. Hostname: `{slug}.mytradeportal.co.uk` (prod), `{slug}.localhost` (local
   dev), else marketing site.

**Chosen strategy for staging/CI: option 1.** Every portal test runs against
`https://landing-staging-192c.up.railway.app/?slug=<test-tenant>` — no DNS, no
certificates, no hosts files. This exercises the entire portal (intake,
magic links, quote/invoice pages, pay shell, claim) against the staging api.

The only thing it does **not** exercise is hostname resolution itself
(slugFromHostname). Cover that with: (a) one local Playwright run using
`{slug}.localhost` with a hosts entry (already how local dev works), and
(b) after the production wildcard cert for `*.mytradeportal.co.uk` issues, a
single smoke test on www pointing at one real subdomain. Do NOT build staging
wildcard DNS — the query param gives the same coverage for ~zero cost.

### Stripe webhooks on staging — one user action left

Stripe (test mode) can only deliver webhooks to endpoints registered in the
dashboard. The registered endpoint points at **production**
(`api-production-…/webhooks/stripe`). For staging E2E of `payment_intent.succeeded`
/ `charge.refunded` there are two options:

- **Recommended:** in the Stripe dashboard (test mode) add a second webhook
  endpoint `https://api-staging-cced.up.railway.app/webhooks/stripe` subscribing
  to `payment_intent.*`, `charge.*`, `account.*`, then set the returned signing
  secret as `STRIPE_WEBHOOK_SECRET` on the **staging** api (production keeps its
  own). Real delivery, real signatures, tests the full path.
- **Fallback (no dashboard visit):** tests forge `Stripe-Signature` headers
  locally with the known secret to exercise our handler + idempotency. This
  validates our code but not Stripe→Railway delivery.

### Entitlements — what actually exists (B5/Q5)

The pricing pivot to flat unmetered tiers (`28a01f5`, 09-13) **deleted** the
hybrid quota model: no `ENTITLEMENTS_ENABLED` flag exists in code, and
`require_ai_allowance` (dependencies.py:368) is a back-compat shim whose
docstring says exactly that — it applies only the invisible fair-use
guardrail (cheap-route fallback + one staff alert at the monthly threshold,
fail-open) and returns None. **AI is never metered or blocked
customer-visible on any plan — that is a tested promise**
(`services/api/tests/test_fair_use.py`).

What DOES gate access today:

- **The paywall** (`GET /auth/tenant-status`, auth.py:284): tenants whose
  subscription is `incomplete` / `paused` / `canceled` get
  `access="payment_required"` and the app shows the paywall;
  `trialing` / `active` / `past_due` / `beta_comped` pass. This is the
  "paying subscribers only" gate — and it is what E2E should assert (G8).
- **The 14-day no-card trial + engagement extension** (`app/trial.py`):
  signup creates a `trialing` subscription; sending ≥3 AI-drafted quotes
  extends once to ~30 days from now (`trial_extended_at`). E2E: G6/G7.
- **Tier-feature gates (Sole Trader vs Pro vs Team)** — **not implemented
  anywhere in code** (`require_plan`/tier-grep: zero hits). They are
  Delivery-Plan Phase 0.6 work. Tests for tier gating are blocked on
  implementation, not on test-writing; when built, assert server-side
  (402-style or 403 with upgrade message) not just UI.

Consequence for the gap table: G8 = paywall + trial only; G10 (AI overage) is
**dead** — remove it (flat unmetered model has no overage; the Paddle overage
price IDs still in vars are inert catalog leftovers).

### Paddle webhook on staging

Same delivery question as Stripe: the Paddle sandbox webhook destination
registered in the Paddle sandbox dashboard points at production. Check where
`PADDLE_WEBHOOK_SECRET` events land; if needed add a second destination for
`https://api-staging-cced.up.railway.app/webhooks/paddle`. Signature-forged
fallback applies here too.

---

## Original blocker list (historical)

| # | Blocker | Status |
|---|---|---|
| B1 | **D1 — Gmail bouncing all mail** (DKIM/SPF/DMARC suspect) | P0, per `docs/validation/2026-09-15-production-portal-smoke.md`. Does not affect staging (Mailpit), but production email journeys stay unverifiable until fixed. |
| B2 | **D4 — Stripe Connect platform enrollment** (onboarding 500s, raw-500 contract) | P0 per Payments PRD §Phase 0.0.11. Blocks Connect onboarding E2E everywhere. |
| B3 | **Stripe sandbox keys on staging/PR** (`STRIPE_SECRET_KEY`, webhook secret, publishable) — user said "set up production with test credentials/sandboxes for now" | Needs wiring into staging + PR envs (forked from staging, so set once on staging). |
| B4 | **Paddle sandbox catalog + keys on lower envs** — sandbox catalog exists (`ba4e52c`); keys must point at sandbox on staging/PR | Same fork-from-staging inheritance. |
| B5 | **Portal subdomain resolution in tests** — prod uses `{slug}.mytradeportal.co.uk` (wildcard cert `VALIDATING`); for staging/CI either a `*.up.railway.app` portal origin with a Host-header/subdomain emulation, or hosts-file entries | Decide test strategy before writing portal specs. |
| B6 | `ENTITLEMENTS_ENABLED` kill switch is **default off** | Entitlement-gate tests must set it on (or accept skip) until the pricing decision lands. |

## Gap table — payments & billing (beta blockers)

| # | Gap | Journey to test | Docs ref | Pri | Suite | Notes |
|---|---|---|---|---|---|---|
| G1 | **Stripe card payment end-to-end** | Invoice sent (Stripe-connected tenant, card enabled) → customer opens `/pay/:token` (or portal pay) → Stripe Payment Element with **sandbox test card 4242…** → `payment_intent.succeeded` webhook → invoice `paid` automatically (no manual mark-paid) → **receipt email** in Mailpit → tradie notified → `invoice_paid` outcome event w/ trace_id | `portal-invoices-payments.feature`, PRD-Online-Payments §5 | **P0** | portal + deployed-smoke (webhook) | Assert webhook idempotency by replay; assert no account required to pay. Needs B3. |
| G2 | **Failed payment + retry** | Decline card (4000 0000 0000 0002) → failure surfaced with reason → customer can retry with good card → succeeds | PRD-Online-Payments | **P0** | portal | |
| G3 | **Stripe Connect onboarding (tradie)** | Payments settings → Connect button → onboarding URL (mock/short-circuit KYC in sandbox) → status flips to connected → per-invoice + default-on card toggle visible | PRD-Online-Payments §Phase 0.0.11 | **P0** | mobile-staging | Needs B2+B3. Accounts v2 (`77991f6`) is the code under test. |
| G4 | **Full refund** | Paid invoice → refund → `charge.refunded` webhook → invoice `refunded`, audit row, staff notification; **replayed webhook is idempotent no-op** | `trade-invoices-payments.feature` | **P0** | deployed-smoke + mobile-staging | Partial refund is P1. |
| G5 | **Paddle subscription at onboarding** | Wizard plan step → Paddle hosted checkout (**sandbox**, email prefilled + locked) → complete → webhook `subscription.activated` → tenant `active`, plan key correct; reopening wizard shows current plan | `trade-onboarding.feature` @manual, `platform-billing.feature` | **P0** | mobile-staging (checkout return) + deployed-smoke (webhook signature/idempotency) | Needs B4. Assert plan re-derived from price ID on every event (`ba4e52c`). |
| G6 | **14-day no-card trial** | Signup without purchase → `trial_ends_at` ≈ +14d → `GET /auth/tenant-status` = `trialing` → full feature access during trial | `platform-billing.feature`, trade-onboarding @p0 | **P0** | deployed-smoke | |
| G7 | **Trial extension on engagement** | Send 3 AI-drafted quotes → trial extends once to ~30d, `trial_extended_at` stamped; 4th quote does not extend again | Pricing PRD | **P0** | mobile-staging (uses real LLM turns — budget ~10 min) or API-driven with seeded `ai_generated` quotes | |
| G8 | **Paywall / paying-subscriber access** | Lapsed/`incomplete`/`paused`/`canceled` tenant → **402/payment_required gate** at app launch with recovery CTA; `trialing`/`active`/`past_due`/`beta_comped` pass. (Tier-feature gates Pro-vs-Sole-Trader are NOT implemented yet — Phase 0.6; blocked on implementation, see entitlements note above) | `trade-onboarding.feature`, `platform-billing.feature` (C22) | **P0** | deployed-smoke (state transitions via seeded subscriptions) + mobile-staging (gate UX) | Server-side `tenant-status` assertion is the critical one; UI is secondary. |
| G9 | **Paddle manage-subscription portal** | Settings → manage subscription → Paddle customer-portal session URL opens; cancellation there → webhook → `canceled` + paywall on next launch | `trade-settings.feature` | P1 | mobile-staging | |
| G10 | ~~AI overage billing~~ **DELETED** | Flat unmetered pivot removed the overage model; the leftover Paddle overage price IDs in vars are inert catalog remnants | — | — | — | Removed 2026-09-16 after code verification (`dependencies.py:368` shim, no `ENTITLEMENTS_ENABLED` anywhere). |

## Gap table — communications & reviews

| # | Gap | Journey to test | Docs ref | Pri | Suite | Notes |
|---|---|---|---|---|---|---|
| G11 | **Quote reminder chasing** | Sent quote unanswered → reminder emails at configured cadence (default 3, then stop) → each send ledgered in `reminders` + staff notified → dup guard (no double-send on scheduler retry) → replying/accepting cancels the sequence | platform-observability N6, scheduler.py | **P0** | deployed-smoke (force-fire scheduler) + Mailpit content assert | Currently N6 only *reads* cadence fields — nothing fires or asserts content. Drive by setting `quote_reminder_interval_days` low (or invoking the scheduler fn directly). |
| G12 | **Invoice reminder chasing** | Sent invoice unpaid → reminders **recur until paid** (configurable interval) → manual mark-paid cancels → Stripe settlement cancels | N6, scheduler.py | **P0** | same as G11 | |
| G13 | **Payment-received email + review CTA** | Both settlement paths: (a) Stripe webhook paid, (b) **manual mark-paid (D3 fixed in `0029376`)** → customer email "Payment received — INV-xxx" containing **review CTA pointing at tenant `review_url`** when configured; absent when not configured | ADR-004 §4, `trade-invoices-payments.feature` A13 | **P0** | mobile-staging + Mailpit | Assert both paths — D3 was a real defect. |
| G14 | **Google review URL capture** | Onboarding Branding step + Settings branding: enter `review_url` → persists on tenant → **Share QR / share-link** on Quotes screen encodes it | `trade-settings.feature`, `ae1f3a6` | P1 | mobile-staging | Small: one settings round-trip + QR render assert. |
| G15 | **Bounce / email-failure staff alert** | Send to a bouncing address (or Resend webhook sim of `email.bounced`) → **one** staff alert per tenant+contact+day naming the failed email + directing to customer's phone → alert cannot loop (staff mail skips hook) | platform-observability, `23cf10c` | P1 | deployed-smoke (webhook signature + alert row) | Signature path already negatively tested (`test_resend_webhook_rejects_bad_signature`) — add positive. |
| G16 | **Email sequence completeness via Mailpit** | For one full lifecycle assert every email arrives with correct magic-link CTA: quote-ready → acceptance/pending-booking → **booking-confirmed on first scheduling (D5 fixed in `0029376` — assert create AND convert-to-job paths)** → invoice → payment-received. Assert no-reply sender for transactional vs quotes@ branded for quote/invoice | ADR-004 §4 | **P0** | mobile-staging + Mailpit | D5 was a real defect — encode both scheduling paths. |
| G17 | **Magic links actually work** | N2 currently asserts the invoice email contains *an* https link but never follows it. Follow `view_url` → lands on real invoice page (portal) with correct total/status; document tokens rotate on re-send; expired token → resend flow (202, no account leak) | `portal-auth.feature` | **P0** | portal | Follow-the-link turns email tests into true journey tests. |

## Gap table — portal (customer web) — all-new suite

| # | Gap | Journey to test | Docs ref | Pri | Suite | Notes |
|---|---|---|---|---|---|---|
| G18 | **Arrival & intake** | 6-digit code / QR → tenant-branded portal → quote form (name, email, phone, **address + property profile**, photos, preferred dates, contact-preference chips) → Customer row auto-provisioned (no password) → magic-link email in Mailpit → `entry_channel` recorded | `portal-arrival-intake.feature` @p0 | **P0** | portal | Chat option must NOT appear for passwordless customers (chat-reachability gating `5ac841a`). |
| G19 | **Inline AI triage** | `sync_check=true` intake → ≤12s follow-up question via guest thread token (2h TTL) → **does not re-ask already-provided answers (C13)** → fail-open on timeout (form succeeds, tradie notified) | portal-arrival-intake @p0 | P1 | portal | D2 (guest AI ~20s timeout) is P2 — assert bounded, not exact. |
| G20 | **Magic-link auth & account claim** | Magic link → customer JWT (30-day TTL) → portal home shows only own quotes/invoices → booking-confirmation email's claim link → one-shot `/claim` sets password → app register against the passwordless account claims it (no 409) → comms preference flips to app+email | `portal-auth.feature` @p0, `65f696c` | **P0** | portal + mobile-staging | Object-level isolation: customer A's token can't see customer B's docs. |
| G21 | **Quote accept / decline / discuss** | Portal quote detail (ex-VAT subtotal, VAT, total, awaiting-response) → **accept + preferred dates** → `quote_accepted` → tradie notified in-app AND email; decline with reason persisted; discuss reply lands in shared thread | `portal-quotes-bookings.feature` @p0 | **P0** | portal | Never expose pre-review drafts (C3). |
| G22 | **Booking flow** | Preferred dates → `POST /customer/appointments` → electrician schedules → **booking-confirmed email with magic link + claim CTA** | portal-quotes-bookings | **P0** | portal + Mailpit | |
| G23 | **Portal invoices & pay** | Invoice list (status/total/due) → "Pay this invoice" only when Stripe-connected → pay shell → Stripe sandbox card → paid; without Stripe: graceful "Card payments aren't available right now"; view-only `/invoice/:token` fallback | portal-invoices-payments @p0 | **P0** | portal | Overlaps G1 — same Stripe sandbox harness. |
| G24 | **Password reset (both roles)** | Branded reset pages on mytradeportal.co.uk, single-use signed token, tenant-branded portal variant, no account-existence leak | `account-password-reset.feature` @p1 | P1 | portal | |
| G25 | **Guest chat gating** | Passwordless customer's portal shows phone/email contact instead of chat composer; ContactCustomerCard replaces composer in-app for unreachable customers | `5ac841a`, customer-mobile-app.feature | P1 | portal + mobile-staging | |

## Gap table — app journeys (mobile-staging additions)

| # | Gap | Journey to test | Docs ref | Pri | Suite | Notes |
|---|---|---|---|---|---|---|
| G26 | **Customer invoices in the app** | Customer invoice list + detail screens (landed `ab0cf59`, untested) → total/status/line items render; pay entry point when Stripe connected | customer-mobile-app.feature | P1 | mobile-staging | |
| G27 | **Multi-day jobs** | Quote with >1 day of hours → convert → work blocks split across consecutive working days ≤ daily hours; reschedule shifts all blocks by same delta; `is_multi_day` flagged | `7a5a928`, work_blocks.py | P1 | mobile-staging | |
| G28 | **Quote acceptance reconfirmation** | Customer accepts → preferred dates reconfirmed → surfaced on quote when converting to job | `7a5a928` | P1 | mobile-staging | |
| G29 | **Rounding & VAT chain** | Rounding chip (5/10) → quote total rounded up with `rounding_adjustment` → job → invoice **mirrors exactly** (never re-rounded); non-VAT-registered tenant → 0% VAT on all lines/totals (C1 repeat-regression) | trade-ai-quotes C1/N22 | **P0** | mobile-staging | N22 was marked Fail in backlog — encode both directions. |
| G30 | **Mark-all-read + notification deep-links** | `POST /notifications/read-all` clears badge; bell rows navigate for quote-sent / booking / chat kinds (only job_scheduled + invoice_sent covered today) | trade-messages-notifications | P1 | mobile-staging | |
| G31 | **Blocked-customer enforcement** | Blocked customer cannot log in / submit quote request / chat (N26 only renders the banner today) | trade-crm-leads | P1 | mobile-staging | API-level negative asserts. |
| G32 | **Customer decline / discuss** | Only Accept is tested today | portal-quotes-bookings | P1 | portal (G21 covers) | — |
| G33 | **`GET /export/my-data`** | Tenant owner exports → streamed JSON contains their tenants/quotes/invoices; RLS-scoped (no other tenant's data); secrets excluded | `data_export.py`, PRD-Observability | P1 | deployed-smoke | |
| G34 | **AI metadata contract** | Generated quote exposes `ai_confidence`, `ai_warnings`, `ai_assumptions`, `retrieval_status`; grounded lines use catalogue units (ea/m/hr) — **never `unit="job"`** (repeat regression) | trade-ai-quotes @p0 | **P0** | mobile-staging (extend C/H) | Cheap assert on existing flows. |

## Proposed execution order

**Wave 1 — harness + beta blockers (payments spine):** staging Stripe webhook
endpoint (user dashboard action, see above); G1/G2
(portal Stripe sandbox card + decline/retry), G4 refund idempotency, G6 trial,
G8 paywall gate (server-side first), G5 Paddle sandbox checkout +
webhook. These need new seeding helpers (Stripe-connected tenant, subscription
states) in `mobile/e2e/seed-e2e.mjs`.

**Wave 2 — email spine:** G11/G12 chasing (scheduler drive + Mailpit), G16 email
sequence (all lifecycle mails incl. D3/D5 regression guards), G13 review CTA,
G17 follow-the-magic-link, G15 bounce alert. Mostly extends existing specs +
`mailpit.ts`.

**Wave 3 — portal suite (new):** G18–G25 as a new `web/landing` Playwright suite
against staging (subdomain strategy B5), reusing Mailpit + setup-token seeding.

**Wave 4 — app depth:** G26–G31, G34 rounding/VAT/AI-metadata hardening.
G33 export, G9/G10 billing self-serve when decisions land.

## What stays manual / out of CI

- Live-card payment (`@manual` go-live gate), real Connect KYC, Apple Pay.
- Push/badge on physical device (Appium suite exists separately for that).
- `@gap` parked items (PWA install, widget, certificates, deposits, Xero) —
  explicitly excluded per `parked-gaps.feature`.
- Real-LLM quality tests stay minimal in CI (cost): G7 trial-extension is the
  only new LLM-dependent test; everything else is API/UI-assertable.

## Coverage log

| Date | PR | Gaps covered | Notes |
|---|---|---|---|
| 2026-09-16 | (this PR) | G4 (Stripe refund + replay idempotency), G5 (Paddle webhook signature/idempotency/plan re-derivation), G6 (14-day no-card trial), G7 (trial extension, API-driven with seeded `ai_generated` quotes + once-only guard), G8 (paywall tenant-status + 402 middleware), G13 (payment-received email + review CTA, Stripe path), G15 (bounce → staff alert, in-app `type=email_failed` + staff email), G17 (magic-link exchange/claim/single-use), G33 (`/export/my-data` shape) | New `deployed_write` pytest suite (`services/api/tests_deployed/test_deployed_write_suite.py`) run by a dedicated `deployed-write-suite` job in `staging-e2e.yml`. Stripe/Paddle chains validated against a Railway PR environment before merge (production-copied secrets); suite skips cleanly without `TEST_SETUP_TOKEN`/webhook secrets so `pr-verify` stays read-only. Also fixed two product bugs found while writing tests: Bearer auth on endpoints without `TenantDep` (`get_current_user` now sets RLS tenant context from token claims, mirroring `get_current_customer`) and tenant resolution for portal magic-link endpoints (`X-Tenant-Slug` header, sent by the landing portal client when served from the marketing origin). |
| 2026-09-17 | `test/mobile-batch-1` | G16 (full email spine in Mailpit: quote-ready magic-link CTA → acceptance → booking-confirmed on BOTH scheduling paths → invoice → manual payment-received without card-receipt copy → transactional no-reply sender), G29 (rounding chip → quote_rounding=5/10 → VAT-registered 20% vs non-registered 0% fallback → quote→job→invoice mirrors subtotal/VAT/total/`rounding_adjustment` exactly), G14 (branding screen persists `review_url` → tenant settings → public config; Quotes share sheet encodes the tenant portal link), G30 (staff + customer read-all clears the badge; bell deep-links for staff quote_accepted/chat_reply + customer chat_message/quote_sent), G31 (blocked customer: 403 login, chat, staff-side quote-request; two gaps fixme'd), G34 (AI-metadata contract on generated quotes: catalogue units, confidence/warnings, retrieval status; 503→skip without LLM), G26 (customer invoice list + dead Pay-now graceful 410) | New mobile-staging specs `emails/rounding/branding/blocked/ai-metadata/customer-invoices.spec.ts` + O2 describe in `notifications.spec.ts`; `testMatch` extended in both playwright configs (necessary infra change). Local full suite vs api :8003: 50 passed — the only failures are pre-existing specs needing an LLM (3× 503) or MinIO (C21) plus one N32 flake that passes in isolation. Three product bugs encoded: **(1)** public quote-request intake accepts a blocked customer (`test.fixme`, 201 today); **(2)** pre-block customer bearer tokens stay valid on `CurrentCustomerDep`-only read surfaces (`/customer/quotes` 200, `test.fixme`); **(3)** `POST /customer/invoices/{id}/pay` always 410 while the app still shows Pay now (interim test asserts the graceful error). Noted: Quotes share QR encodes the portal URL, not `review_url`; customer `quote_sent` bell only fires for AI-generated quotes (linked at creation) — deep-link test self-skips for manual quotes; staff `chat_reply` bell requires closed AI triage (no-LLM envs assert the quiet rule instead). |
