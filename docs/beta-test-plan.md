# Beta Test Plan — My Trade Portal

Created: 2026-09-12 · Companion to `docs/beta-backlog.md` (56 items, all fixes shipped in `6929dd4` → `7c15cf9`).

Every backlog row mapped to its validation layer:

- **API** — pytest in `services/api/tests/` (441 tests, green in CI). No further action.
- **E2E** — Playwright driving the Expo **web** build (`mobile/e2e/`, config `playwright.config.regression.ts`). Runs the real FastAPI backend; each spec seeds its own tenant. Native-only behaviour (ActionSheetIOS, native pickers, push, APNs) is **not** web-testable.
- **Device** — manual on the TestFlight build (build `551a225c`). Listed in the device checklist at the bottom.

**Action column:** Extend = add assertions to an existing regression group · New = new spec file · Covered = existing automation suffices · Manual = device checklist only.

## Notifications & comms

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N1 | Push arrives app-closed with sound/badge; tap deep-links | Device | `test_push.py` (7): payload, ticket errors, triggers, cleanup | Manual (needs APNs key) |
| N2 | Bell-list rows navigate to the notified entity | E2E | API link values tested in wave-2 suites | New `notifications.spec.ts` |
| N3 | No-contact customer: warning logged, no silent drop | API | `test_email_triggers.py` | Covered |
| N4 | Quote-ready/reset/welcome/triage/accepted emails dispatch | API + live | `test_email_triggers.py` (14) | Covered; watch Resend dashboard on first live sends |
| N5 | Job-detail message button follows contact preference | E2E + Device | preference routing matrix in code | Extend jobs spec (chat route); mailto/tel manual |
| N6 | Quote reminders ×3 then stop; invoice reminders recur; cadence settings | API + E2E | `test_reminders.py` (10) | Settings UI in new `settings.spec.ts` |
| N7 | Feed-link returns webcal URL; native subscribe prompt | API + Device | `test_calendar.py` (5) | Covered (API); subscribe prompt manual |

## Branding

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N8 | No off-brand colours on dashboard/revenue; slate/yellow tokens | Device | token sweep verified by grep at commit | Manual visual pass |

## Jobs

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N9 | Inline new customer during job create | E2E | — | New `jobs.spec.ts` |
| N10 | Maps opens default app | Device | — | Manual |
| N11 | Assignee selectable; notes editable | E2E | `test_jobs_wave2.py` (API) | New `jobs.spec.ts` |
| N12 | AI assumptions land in job notes | API | `test_jobs_wave2.py` | Covered |
| N13 | Quote photos attach to job | API | `test_jobs_wave2.py` | Covered |
| N14 | Photo upload works (was 503) | API + Device | `test_files.py` (9) | Covered; device upload check |
| N15 | Duration prefilled from quoted hours; date/time set | E2E | — | New `jobs.spec.ts` |
| N16 | Working hours settings drive availability | API + E2E | `test_working_hours.py` (4) | Settings UI in `settings.spec.ts` |
| N17 | Keyboard-avoiding create pages | Device | — | Manual |
| N18 | Quote-selection prefill; no silent failure | E2E | wave-1 guard covered by fixed group E | Extend group E + `jobs.spec.ts` |
| N19 | Quote-less job → AI create-invoice → send page | E2E | — | Extend group E (stale — currently fails) |
| N20 | Calendar new-job is borderless + | E2E | — | Assert in dashboard/calendar spec |
| N23 | Convert-to → Job (prefilled) / Invoice | E2E (web buttons) + Device (ActionSheet) | — | New `jobs.spec.ts`; ActionSheet manual |

## Quotes / AI

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N21 | Consumer units/sockets/T&E ground from catalog | API + prod | `test_rag_retrieval_resilience.py` (9), evals 15/15 | Covered; prod reindex is the ops action |
| N22 | Rounding £5/£10 uplifts totals, visible in quote | API + E2E | `test_quote_rounding.py` (7) | Settings UI in `settings.spec.ts` |
| C1 | Non-VAT-registered tenant → 0% VAT everywhere | API | `test_vat_registration.py` (7) | Covered |
| C6 | Grounded lines take catalogue units (m/ea) | API | retrieval resilience tests | Covered |
| C9 | Quote edits captured + exportable | API | `test_quote_training_events.py` (4) | Covered |
| C10 | Refine shows skeleton + leave-page banner | E2E | testIDs exist (`refine-skeleton`, `refine-banner`) | Extend group H |

## Customers / CRM

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N24 | Legacy contact-linked threads open; no error banner | API + E2E | `test_communications.py` (9 new) | Covered; chat group F exercises threads |
| N25 | Customer edit round-trip; parking/access prefill quote intake | E2E | `test_customers_crm.py` (11) | New `crm.spec.ts` |
| N26 | Badges auto/overrides; block stops login/quote/chat | API + E2E | `test_customer_badges.py` (12) | Badge UI + block button in `crm.spec.ts` |
| C5 | Full address persists on contact + customer | API | `test_customers_crm.py` | Covered |
| C15 | Duplicate create → 409; merge-backfill | API | `test_customers_crm.py` | Covered |
| C4 | Account-less quote persists; unregistered flag on lead | API | `test_customer_portal.py` | Covered |
| C12 | Slug-less customer login resolves tenant | API + E2E | `test_customer_portal.py` | Extend group B (login without code entry) |
| C20 | 0-quote customer sees welcoming empty state / live-count banner | E2E | — | Extend group B |

## Invoices / payments

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N27 | Bank details settings → invoice email block | API + E2E | `test_invoice_payment_details.py` (5) | Settings UI in `settings.spec.ts` |
| C19 | Checkout email prefilled + locked | Device | verified in code (`billing.py:161`) | Manual (Paddle sandbox checkout) |
| C22 | Tenant-status gate: comped beta passes, lapsed paywalled | API | `test_auth.py` (5) | Covered |

## Auth

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N28 | Reset email → mytradeportal.co.uk page → new password works | API + Manual | `test_auth.py` (5 reset tests); landing builds | Manual full round-trip (email + landing page) |

## Messages

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N29 | + new message → search account-holding customers → thread | E2E | threads endpoint tested | New `messages.spec.ts` |
| C7 | Request-more-info opens customer chat | E2E | — | Extend quote spec / `messages.spec.ts` |
| C2 | Customer messages read back inbound | API | `test_communications.py` | Covered |
| C13 | Triage acknowledges provided detail, no loops | API | `test_quote_automation.py` (3) | Covered; `@demo` spec exercises live chat |
| C14 | Staff bell once per customer burst | API | `test_communications.py` | Covered |

## Dashboard & navigation

| Ref | What to validate | Layer | Existing coverage | Action |
|---|---|---|---|---|
| N30 | No "New lead" button; New Customer on CRM screen | E2E | — | New `dashboard.spec.ts` |
| N31 | Top section shows best 2 new quotes | E2E | ranking formula unit-reviewed | New `dashboard.spec.ts` |
| N32 | Revenue summary + time-saved on dashboard; jobs capped | E2E + API | `test_analytics.py` (KPI fields) | New `dashboard.spec.ts` |
| N33 | Stat cards navigate; outstanding → quotes ?filter=new&sort=fifo | E2E | — | New `dashboard.spec.ts` |
| C16 | Three-dots menu on all trade tab pages | E2E | — | New `dashboard.spec.ts` |
| C17 | Tab bar safe-area padding | Device | — | Manual |
| C18 | Chat tab both roles; active highlight works | E2E | — | New `dashboard.spec.ts` |
| C3 | Customer can't see pre-review quote | API | `test_customer_portal.py` allow-list | Covered |
| C8 | Keyboard doesn't trap inputs (profile, chat, intake, decline) | Device | — | Manual |
| C11 | Membership type persists | API | verified `onboarding.py:137` | Covered |
| C21 | Customer adds photos post-submission | E2E | upload endpoint covered | Extend group B (file input) |
| C23 | Plan selection completes without 500 | E2E + Device | `test_tenant_bootstrap.py` (502/503 mapping) | Extend group G to plan step; checkout manual |

## Refactor scope for the e2e suite

1. **Fix stale group E** (`regression.spec.ts`): quote-less job → `job-create-invoice` now lands on the AI invoice-create page → must tap `invoice-create-submit` before mark-paid.
2. **Extend existing groups:** B (C12 slug-less login, C20 empty state, C21 photo add), H (C10 skeleton/banner assertions), G (reach plan step).
3. **New spec files:** `jobs.spec.ts`, `crm.spec.ts`, `settings.spec.ts`, `dashboard.spec.ts`, `messages.spec.ts`, `notifications.spec.ts` — each seeds its own tenant via `helpers.ts`, uses testIDs, avoids live-LLM dependence (seed quotes/invoices via API).
4. **Config:** `playwright.config.regression.ts` testMatch broadened to include the new specs (excluding `demo-customer-chat.spec.ts`, which keeps `playwright.config.demo.ts`).

## Device checklist (TestFlight build `551a225c`, after APNs key)

1. Push: app-closed banner/sound/badge on quote-ready, message, reminder; tap deep-links (N1, N2)
2. Convert-to… ActionSheet offers Job/Invoice (N23)
3. Native date/time pickers on job create (N15)
4. Keyboard behaviour on intake, chat, profile, decline (N17, C8)
5. Tab bar home-indicator clearance (C17)
6. Maps opens default app from job detail (N10)
7. Calendar subscribe shows iOS native prompt (N7)
8. Paddle sandbox checkout: email prefilled + locked, no 500 at plan step (C19, C23)
9. Password reset round-trip via email → mytradeportal.co.uk (N28)
10. Photo upload from device camera/library (N14)
11. Visual brand pass: dashboard, revenue, quotes, jobs (N8)
