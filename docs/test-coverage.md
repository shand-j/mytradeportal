# Test Coverage — Journey Map and Insights

Companion to `docs/features/*.feature`. Maps every user journey to its
automated tests, e2e specs, evidence videos and manual/UAT items, and flags
the gaps. Derived from the working tree on 2026-09-14 (test counts are static
`def test_` greps, not a pytest run).

RAG key: **covered** (automation or video evidence exists) · **partial**
(some paths covered, material paths not) · **manual-only** (no automation
possible or none written) · **gap** (specified, not built).

## 1. Journey → coverage matrix

| Feature file | Journey | API tests (file: count) | E2E / evidence | Manual / UAT | RAG |
|---|---|---|---|---|---|
| trade-onboarding.feature | Signup → setup → branding → plan → Paddle → trial | test_onboarding.py:8 · test_tenant_bootstrap.py:12 · test_tenant_guc_checkout.py:4 · test_trial.py:11 · test_billing.py:24 · test_auth.py:35 | — | Paddle sandbox checkout (device checklist #8) | partial (checkout manual) |
| trade-ai-quotes.feature | AI generate / edit / refine / send / PDF | test_quotes_generate.py:17 · test_rag.py:40 · test_rag_retrieval_resilience.py:9 · test_quotes_lifecycle.py:11 · test_quote_automation.py:8 · test_quote_rounding.py:9 · test_vat_registration.py:7 · test_quote_training_events.py:4 · test_quote_pdf.py:5 · test_ai_quality.py:16 · test_evals.py:11 | wave-a `00a` (send + trial extension), `01`, `07`; refine skeleton/banner asserted in regression.spec group H | live LLM quality via `python -m evals.run_evals --live` | covered |
| trade-jobs-scheduling.feature | Convert → schedule → start/complete, calendar | test_jobs_wave2.py:10 · test_jobs_lifecycle.py:7 · test_jobs_address_schedule.py:7 · test_calendar.py:8 · test_working_hours.py:4 · test_appointments.py:3 | mobile/e2e/jobs.spec.ts (5 tests) | ActionSheet convert, native pickers, Maps, calendar subscribe (device #2,3,6,7) | partial (native UX manual) |
| trade-invoices-payments.feature | Invoice → send → pay → refund | test_invoices.py:10 · test_invoices_lifecycle.py:6 · test_invoice_from_job.py:5 · test_payments.py:15 · test_payments_lifecycle.py:1 · test_stripe_webhooks.py:14 · test_invoice_payment_details.py:5 | wave-a `00b`,`00c`,`00d`,`03`,`05`,`06`; regression.spec group E (stale — needs invoice-create step) | Stripe Connect onboarding, live card payment | partial (live Stripe manual) |
| trade-crm-leads.feature | CRM detail, badges, blocking, leads | test_customers_crm.py:11 · test_customer_badges.py:12 · test_quote_requests.py:2 | mobile/e2e/crm.spec.ts (2), dashboard.spec.ts (4) | badge override tap behaviour (beta-backlog N26 partial fail) | covered |
| trade-messages-notifications.feature | Chat, ContactCustomerCard, push + bell | test_communications.py:24 · test_contact_preference.py:8 · test_notifications.py:11 · test_push.py:8 · test_public_threads.py:7 | mobile/e2e/messages.spec.ts (2), notifications.spec.ts (2), demo-customer-chat.spec.ts (3) | APNs push end-to-end, tel/mailto (device #1) | partial (push device-only) |
| trade-settings.feature | Branding, hours, review link, reminders, rounding, VAT, payments | test_settings.py:4 · test_reminders.py:10 · test_working_hours.py:4 · test_quote_rounding.py:9 · test_vat_registration.py:7 · test_invoice_payment_details.py:5 | mobile/e2e/settings.spec.ts (4) | chip readability issues (N16/N22 user notes) | covered |
| account-password-reset.feature | Branded reset for both audiences | test_auth.py:35 (5 reset tests) | landing builds verified | full email → page round-trip (device #9) | partial (delivery manual) |
| portal-arrival-intake.feature | QR/code → form → inline triage → auto-provision | test_public_quote_requests.py:5 · test_intake_triage.py:19 · test_public_threads.py:7 · test_customer_portal.py:21 · test_rate_limit.py:3 | — | QR scan on physical collateral | covered |
| portal-auth.feature | Magic consume / expiry / resend / claim | test_portal_auth.py:12 · test_account_claim.py:6 · test_contact_preference.py:8 · test_tenant_isolation.py:6 | — | App Store link is a placeholder pre-release | covered |
| portal-quotes-bookings.feature | Quote view/accept/decline/discuss → booking | test_customer_portal.py:21 · test_email_sequence.py:29 · test_appointments.py:3 | wave-a `01`,`02` (view-only token page; portal accept post-dates capture) | portal subdomain live check (S3 wildcard blocked on Railway Hobby) | covered (wildcards blocked) |
| portal-invoices-payments.feature | Invoice view → Stripe pay → receipt + review | test_customer_invoices.py:7 · test_public_docs.py:18 · test_stripe_webhooks.py:14 · test_email_sequence.py:29 | wave-a `03`,`04`,`05`,`00c` | real card against live Stripe (P-wave go-live gate) | partial (live Stripe manual) |
| customer-mobile-app.feature | Register/claim, login, intake, chat, calendar, invoices | test_customer_portal.py:21 · test_account_claim.py:6 · test_customer_invoices.py:7 · test_contact_preference.py:8 | regression.spec group B; demo-customer-chat.spec.ts | — | covered |
| platform-billing.feature | Bootstrap, trial, tiers, fair-use, Paddle sync | test_tenant_bootstrap.py:12 · test_trial.py:11 · test_tier_gates.py:10 · test_entitlements.py:13 · test_fair_use.py:17 · test_rate_limit.py:3 · test_webhooks.py:22 · test_paddle_client.py:5 · test_tenant_guc_checkout.py:4 | — | live Paddle webhook delivery | covered |
| platform-observability.feature | Attribution, rollups, alerts, keep-rate, export, reminders | test_ai_telemetry.py:11 · test_rollups.py:12 · test_alerting.py:4 · test_observability.py:4 · test_observability_hardening.py:25 · test_ai_quality.py:16 · test_data_export.py:4 · test_reminders.py:10 · test_reconcile_ai_costs.py:4 · test_backfill_ai_events.py:4 · test_analytics.py:8 · test_analytics_shim.py:6 | — | Slack/email alert delivery to real ops channels | covered |
| parked-gaps.feature | 9 specified-not-built capabilities | none (by definition) | certificates have a client-only mobile prototype | — | gap |

Shared API-test support not tied to one journey: test_tenancy.py:3, test_tenant_isolation.py:6, test_audit.py:5, test_calculations.py:3, test_fx.py:4, test_feature_flags.py:4, test_files.py:10, test_reviews.py:3, test_supabase.py:4, test_schema_reconciliation.py:4, test_email.py:7, test_email_triggers.py:14, test_demo_quotes.py:21, test_ocerp_client.py:4 (legacy), test_ai_pricing.py:8.

## 2. Insights

### Overall numbers

- **~792 test functions** across 85 files in `services/api/tests/` (static grep; pytest's collected count was 614 at the A1/A2 commit and 441 at beta start — the suite keeps growing). Largest suites: test_rag.py (40), test_auth.py (35), test_email_sequence.py (29), test_observability_hardening.py (25), test_communications.py + test_billing.py (24 each).
- **36 Playwright tests** in `mobile/e2e/` across 8 specs, driving the Expo web build against the real backend (each spec seeds its own tenant via helpers.ts).
- **11 evidence videos** in `docs/evidence/wave-a/` proving the full quote-to-cash lifecycle on the local stack (see README for the mocking surface).
- **15 golden jobs** in the offline eval harness (`services/api/evals/`); `--live` mode scores the real LLM.
- API tests need local Postgres (`docker compose up -d postgres`); evals run offline by default.

### What is mocked vs needs a live environment

| Dependency | Local / CI | Needs live env |
|---|---|---|
| LLM (Kimi) | evals replay fixtures; API tests stub | `--live` evals; generation quality on prod data (N21 reindex) |
| Stripe | stubbed at `app.stripe_client` seam (wave-a); webhook signature real HMAC | Connect onboarding, Payment Element, real card charges — needs `STRIPE_*` keys (P-wave gate) |
| Paddle | tests mock `paddle_client`; no-card trial is internal | sandbox checkout (device #8), live webhook delivery |
| Email (Resend) | SMTP fallback → Mailpit | first live sends — watch Resend dashboard (beta-test-plan N4) |
| Push (APNs) | test_push.py covers plumbing incl. ticket errors | on-device delivery with the EAS APNs key (device #1) |
| Supabase Auth | blanked → local bcrypt fallback | production Supabase projects |

### Riskiest manual-only journeys for beta

1. **Push notifications** (N1) — the most-reported beta defect; API plumbing is tested but the APNs→device leg is unverifiable without a device. Five beta reports rode on this.
2. **Paddle checkout round-trip** (C19/C23) — plan step previously 500'd; only the sandbox checkout proves email prefill/lock and webhook activation together.
3. **Stripe Connect + live card payment** — wave-a proves everything up to the Payment Element; the element itself and real destination charges are unproven.
4. **Password-reset email round-trip** (N28) — the branded page exists; delivery + token consumption together are manual.
5. **Convert-to… ActionSheet and job-from-quote flow on device** (N12/N18/N23) — beta user marked these "Fail" after API fixes; UI-level regression risk is highest here.
6. **Photo upload on device** (N13/N14) — twice regressed (NoSuchBucket 503); API test exists but the user still saw 503s.

### Parked @gap items and spec locations

| Item | Spec | Status note |
|---|---|---|
| Email bounce/send-failure → staff phone fallback | design docstring in uncommitted `services/api/app/email_alerts.py` + `routers/resend_webhooks.py` | implementation interrupted mid-flight: untracked, no tests |
| Portal PWA install | PRD-Customer-Portal.md §4; beta-backlog S4 | planned post-beta-start |
| Embeddable widget | PRD-Customer-Portal.md §4.1–4.2; S4 | planned |
| QR asset pack | PRD-Customer-Portal.md §4.1; S4 | in-app QR modal built (ae1f3a6); print assets not |
| Xero/QuickBooks sync | Delivery Plan Phase 1; PRD-Pricing-and-Billing.md §2 | planned, all tiers |
| Deposits / partial payments | PRD-Pricing-and-Billing.md §2 (Pro gate); backlog F6/F7 | planned |
| Certificates MVP | PRD-Pricing-and-Billing.md §2; backlog F8 | mobile client-only prototype exists; no backend |
| Offline mode | PRD-Pricing-and-Billing.md §2; backlog F9 | planned |
| Multi-user / roles | Team tier, plans.py / Pricing PRD §2 | assignee field exists; no invitations/roles |

Also blocked (not @gap, infra): portal wildcard domains S3 — Railway Hobby's
2-custom-domain limit; needs Pro upgrade or apex consolidation (beta-backlog).

## 3. How to extend

Conventions when adding a journey or scenario:

1. **Feature files** live in `docs/features/`, one per journey group. Tag the
   Feature with audience (`@tradie`, `@customer-app`, `@customer-portal`,
   `@platform`, `@admin`) and priority (`@p0`/`@p1`/`@p2`); tag each Scenario
   with exactly one automation status: `@automated-unit`, `@automated-integration`,
   `@automated-e2e`, `@evidence-video`, `@manual`, or `@gap`.
2. **Name the verification in a comment** under the scenario (test file +
   count, e2e spec, video, or device-checklist item). If you can't name one,
   the scenario is `@manual` or `@gap` — don't tag it automated aspirationally.
3. **Where matching tests live:** API behaviour → `services/api/tests/`
   (pytest, Postgres-backed, run `cd services/api && python -m pytest tests -q`);
   pure logic (calculations, keep-rate, pricing) → unit-style tests in the same
   directory; UI journeys → `mobile/e2e/*.spec.ts` (Playwright against the Expo
   web build; seed a tenant via `helpers.ts`, use testIDs, seed quotes/invoices
   via API to avoid live-LLM dependence); lifecycle proof → a wave evidence
   script under `docs/evidence/<wave>/` with a README row per video.
4. **"No new feature ships dark"** (research pack, `docs/mytradeportal-research/Dev-Test-Strategy.md`):
   any new AI call or user flow must emit observability event(s), carry tests
   for the touched layer, update docs, and get a release-note line — a scenario
   without a named verification layer blocks the release checklist.
5. Keep Gherkin idiomatic: Background for shared auth/tenancy, Scenario
   Outline for settings matrices, UK English, and reference real
   endpoints/screens in backticks-free prose as done in the existing files.
