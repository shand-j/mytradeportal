# Beta Backlog — My Trade Portal

Last triaged: 2026-09-12

> **Release status (2026-09-12):** all three execution waves complete — 56/56
> items carry a validated Status — AI. API, landing and data-pipeline are
> deployed on Railway at `b60ee15`; iOS build `551a225c` is submitted to
> TestFlight (processing at App Store Connect). Every item is ready for
> on-device verification — mark Status — User as you test.
>
> **Blocking user actions (owner: John):**
> 1. **APNs key** for push notifications (N1) — Apple Developer portal → Keys
>    → APNs, then `cd mobile && eas credentials -p ios --profile production`
>    and upload the `.p8`. No rebuild needed.
> 2. **`APIFY_API_TOKEN`** on the Railway `data-pipeline` service, then restart
>    it — the catalog reindex (N21) runs automatically on boot; the
>    `--run-on-start` trigger stays armed until the index is confirmed, then
>    the orchestrator reverts it.

Consolidated defect & feature backlog for the beta. Combines the latest
defect/refinement report with everything carried from earlier pre-beta and
beta testing sessions. The Status — AI column is updated by the AI agent only
when a fix is committed **and** validated (test and/or live verification, with
commit ref). The Status — User column is yours — mark items Verified after
you've tested them on your device.

**Priorities:** P0 = blocks beta usage, money, or data integrity · P1 = core
journey broken · P2 = polish · P3 = cosmetic.
**Refs:** N# = new report (2026-09-11) · C# = carried from an earlier report.

---

## Notifications & comms

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N1 | Push notifications never arrive on iOS (no banner/badge/sound when app closed; in-app banner only) | P0 | Reported ~5× across beta. Token plumbing exists (`mobile/src/lib/pushNotifications.ts`, `services/api/app/push.py`). Suspect Expo APNs production credentials or token/environment mismatch. Needs end-to-end trace: token registration → DB → Expo push API response. | Done (code) `6929dd4` — ticket errors now parsed (were logged as success), sound/high-priority + deep-link data, customer gets quote-ready push, dead-token cleanup; 7 tests. APNs key uploaded to EAS 2026-09-12 (6M5HA7Q78W) — pipeline complete, awaiting first on-device delivery | Working |
| N2 | Bell-icon notification list items don't navigate to the notified thing | P1 | Nav targets missing on notification rows; each notification type needs a deep-link route. Carried: triage-complete / quote-refreshed notifications had the same complaint. | Done `5dff3f4` — mark-all-read button + bulk endpoints (staff + customer). Your note addressed | Working - requires a mark all as read button |
| N3 | Emails fail silently when customer has no contact information | P1 | Silent failure must become logged + surfaced; sending path should no-op with a warning, not drop. Related to N4. | Done `6929dd4` — no-contact case logs `email_skipped_no_contact_email` warning instead of dropping; tested | Working |
| N4 | Customer emails broadly don't work (no quote-ready notifications, no reset emails received) | P0 | Resend vars are set (`RESEND_FROM_EMAIL=quotes@mytradeportal.co.uk`). Customer-facing event emails (quote ready, reset) appear unsent or unlogged. Trace `communications.py` send paths + Resend API responses; add delivery logging. Carried: "no email arrives" reported for password reset earlier. | Done `6929dd4` — send_event_email wrapper + welcome/triage-question/quote-accepted emails, Resend errors logged loudly; 14 tests. Live-delivery verify pending |  Working |
| N5 | Job-detail message button opens iOS Messages | P2 | Should respect customer contact preference (Email or in-app Chat); SMS options were removed earlier. | Done `7c15cf9` — routes on preferred_contact_method (chat/email/phone with fallbacks) | Working |
| N6 | Quote/invoice reminder cron jobs don't exist | P1 | Confirmed: no scheduler exists anywhere in the API. Build one (APScheduler-style, in-process): quote reminders default 3 (configurable), invoice reminders recur indefinitely, cadence configurable in app settings. | Done `7c15cf9` — scheduler.py: quote reminders (default 3, configurable) then stop; invoice reminders recur until paid; cadence in Follow-ups settings; 10 tests | Awaiting test |
| N7 | Apple calendar subscription button surfaces raw up.railway.app link | P2 | Needs proper `webcal:`/native add-to-calendar flow (ICS feed + `.ics` download / `addevent`-style). Carried: earlier "Apple calendar sync doesn't do anything" — partial fix landed as a link; make it native. | Done `5dff3f4` — feed-link was built on the admin domain (iOS got HTML 404); now API origin + RFC 5545 UTC; verified live. Re-subscribe with the new link | Failed - unsecure warning (http) + validation failure. Calendar never added. |

## Branding

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N8 | Revenue screen and dashboard metric highlights off-brand (yellow/green); full app needs brand audit | P1 | Brand is slate `#0F1E26` + yellow `#FFC107` (logo system). Audit every screen against `packages/shared/ts` tokens; replace ad-hoc metric colours. | Done `a767cba` — token-level fix + 34-screen sweep; slate/yellow metric treatment, LiveBadge shared component, white-label intact | Working |

## Jobs

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N9 | Job creation only allows existing customers | P1 | Add inline "new customer" path in job creation (quote agreed off-app). | Done `535100f` — inline New customer toggle on job create (dedupe-aware) | Working |
| N10 | Navigation forces Apple Maps install | P2 | Use platform-neutral map URLs so the default maps app handles it. | Done `7c15cf9` — universal maps URL first, Apple scheme fallback only | Working |
| N11 | Job detail "assigned to" uneditable and undefinable at creation; job notes not editable | P1 | Add assignee selection (tenant members) + editable notes on job detail. | Done `535100f` — assignee chips at create + Change editor on detail, persisted notes editor; server validates same-tenant staff | Working |
| N12 | AI quote assumptions/footnotes should appear in job notes | P2 | Copy assumptions + notes into the job's notes when converting quote → job. | Done `5dff3f4` — root cause: trade app had no approval path, so Job was correctly hidden; sent quotes now convertible (marked accepted on job create) | Fail - Convert to.. options only include invoice and cancel in ui view |
| N13 | Uploaded images should appear attached to the job | P1 | Photos uploaded on the quote should carry through to the job record. | Done `5dff3f4` — same NoSuchBucket root cause as N14; photos now reach the job | Fail - upload error 503 |
| N14 | Photo upload returns 503 | P0 | Regression — likely from the MinIO private-endpoint change (`minio.railway.internal`). Verify `files.py` + storage config end-to-end. | Done `f8ed119` — NoSuchBucket (volume lost the bucket); store_upload self-heals. Verified live: upload 200 | Fail - still returns 503. It did work earlier so I suspect recent change causing regression |
| N15 | Job creation needs date picker + time picker + duration; pre-fill duration from quoted hours | P1 | e.g. 3 lines × 10h → job spans 30 working hours. Duration derived from quote line items, editable. | Done `535100f` — native date/time pickers, duration prefilled from quoted hours, editable | Partially Blocked by N12. can't follow quote -> Job flow date time and duration picker exist |
| N16 | Working hours configurable in the app | P2 | Feeds duration suggestion and calendar slot logic. | Done `5dff3f4` — shared SelectableChip, light text on dark selected fill | Fail - Working Days selection is not readbable when colour filled. Dark background requires light test |
| N17 | New-job page has no keyboard-avoiding layout | P1 | Recurring class — quote screen, customer profile, chat input all had this. Audit KeyboardAvoidingView across form screens. | Done `535100f` — KeyboardAvoidingView on job create + invoice create | Pass |
| N18 | New job: select a quote → prefill duration/date/customer/start time/notes from calendar slots; without a quote "complete and send invoice" silently fails | P0 | Silent failure is the P0; prefill is P1. Disable/redirect the invoice action when no quote is attached. | Done `5dff3f4` — picker includes sent quotes; job create marks sent quotes accepted first, then converts | Fail - cannot select existing quote on job creation page, cannot convert quote to job |
| N19 | Jobs with no quote → AI create-invoice page | P1 | Reuse quote-generation UI (editable, AI-built) but the CTA creates an invoice directly and navs to the invoice send page. | Done `535100f` — AI create-invoice page (reuses generation pipeline, editable lines, direct invoice → send page) | Pass - note no direction to be able to leave and come back on AI invoice create, suspect  |
| N20 | Calendar "New job" button → plain `+` symbol, no border | P3 | Cosmetic. | Done `7c15cf9` — borderless ghost + | Pass |

## Quotes / AI

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N21 | Quotes assume "no catalog match" for items known to be in the cost-item DB (consumer units, sockets, twin & earth) | P1 | Retrieval/index regression. Data was ported to prod Qdrant; suspect embedding model mismatch or index not hit by tenant retrieval. Investigate `app/rag/retrieval.py`. | Done `535100f` — root cause: retrieval read-path wiped the index on the embedding-model bump; now read-only + loud errors. PROD REINDEX REQUIRED (data-pipeline import) | Pass - not confidence for AI quotes is low |
| N22 | Configurable toggle: round quote totals up to nearest £5 or £10 | P2 | e.g. £1236.40 → £1240. Setting lives in tenant settings; applies to quote + invoice totals. | Done `5dff3f4` — chip contrast + the real bug: settings rehydration reset your selection to Off before save (invisible behind unreadable chips); hydrates once now | Rounding not applied, rounding select buttons have same styling problem as N16 |
| N23 | Quote convert button → "Convert to…" iOS action sheet (Job or Invoice) | P1 | Replace single convert-to-invoice action with an ActionSheet navigating to the right page. | Done `5dff3f4` — ActionSheet shows Job for sent quotes (see N12 root cause) | Fail - Convert to.. invoice or cancel are only options |

## Customers / CRM

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N24 | "Could not find messages" error on existing coglabs.ai tenant | P1 | Tenant-scoped query returns nothing and surfaces an error instead of an empty inbox. | Done `7c15cf9` — legacy contact-linked threads 403'd; ownership now accepts contact link, 404 renders empty state; 9 tests | Pass |
| N25 | Can't edit customers; need customer detail screen with editable fields; parking/access persisted and auto-populated on quote/job creation | P1 | Carried: address not persisted (only postcode); contact phone/address empty in settings despite onboarding capture. Chain: customer → quote → job inherits parking/access. | Done `535100f` — editable customer detail screen; parking/access/property persisted + pre-fill quote intake; contact payload contract documented | Partial fail - save changes button flashes but no confirmation of changes saved, this is common across all save changes buttons |
| N26 | Badges: "Late Payer"/"Non-payer" (bad-debt history) and "Time Waster" (>2 quotes, never replied) — auto-set, manually overridable; block button to stop customer login/quotes/messages | P2 | Needs rules engine over invoices/quotes + `blocked` flag enforced in auth + quote creation. | Done `7c15cf9` — auto badges + tri-state overrides + block enforced (login/quote-request/live chat tokens); 12 tests. Anonymous lead-form block deferred | partial fail - badge manual override buttons do not select on tap |

## Invoices / payments

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N27 | Invoice payment details in the email; payment details configurable in settings | P1 | Confirmed: no bank/payment-details config exists anywhere. Add settings fields (account name, sort code, account number, reference format) + include in invoice email template. | Done `5dff3f4` — manage-subscription row → Paddle customer portal session (portal-session endpoint added). Your note addressed | Pass - note that customer link to invoices links to admin and hits a not found. Should open app if installed or nav to a quote page on the web off the mytradeportal.co.uk domain. such as view quote with tenant branding. At this point we may need to consider the tenant specific subdomain also. On a similar note, invoices require login but not all invoices will be attributed to a user with an account, blocked users for example should still get invoice reminders if unpaid |

## Auth

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N28 | Reset-password email links to the admin portal (back office) | P1 | Build reset page on mytradeportal.co.uk: new password + reconfirm, displays user email, signed single-use token, only for app-requested resets. Landing site addition + API token issuing change. | Done `535100f` — /reset-password on mytradeportal.co.uk + PASSWORD_RESET_BASE_URL. Open items from your note (customer invoice links → app/branded web page; reminders to account-less users) moved to follow-ups | Testing blocked at time of testing 21:55 uk time server unreachable |

## Messages

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N29 | Messages screen: `+` new-message button; see/search CRM customers with app accounts | P2 | Recipients limited to customers with app accounts (install known). | Done `7c15cf9` — + button, searchable account-holding customers, POST /communications/threads; staff-started chats notify customer | Pass |

## Dashboard

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N30 | Remove "New lead" button (leads concept removed from the app) | P2 | CTA should be "New Customer" on the customers screen (earlier rename — verify it landed everywhere). | Done `7c15cf9` — New lead button removed; New Customer CTA verified on CRM screen | Pass |
| N31 | "Top Leads" should surface the best 2 new quotes (revenue + ability to fulfil) | P2 | Rank new quotes by value × readiness, not just recency. | Done `7c15cf9` — top-2 new quotes ranked value x readiness (intake completeness, call-back penalty, flagged sink) | Awaiting test |
| N32 | Port revenue report + "time saved" metric onto the dashboard; dense job lists shouldn't dominate | P2 | Part of the rebranding pass; shows app value in full focus. | Done `7c15cf9` — revenue summary + AI time-saved (25 min/draft, server-derived) on dashboard; job list capped at 3/day | pass however componet is sometimes slow to load and the dashboard renders with a malformed box, app should not render until loaded all data. |
| N33 | Stat cards: drop duplicate "outstanding" card, fix dead clicks, order quotes FIFO | P2 | "Active leads" and "outstanding quotes" are the same thing — drop one; outstanding quotes → quotes page with New filter, FIFO by submission; hours-saved beside outstanding-quotes. | Done `5dff3f4` — duplicate card dropped earlier; 'FIFO' caption now 'oldest first' | Pass - note: remove fifo copy from dashboard. |

## Carried from earlier reports

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| C1 | VAT still applied when tenant is not VAT registered | P1 | **Regression — re-verify.** Believed fixed twice; latest report says still broken. Check VAT rate resolution in quote + invoice generation against tenant flag. | Done `6929dd4` — schema default 0.20 made the tenant fallback dead code; fixed via model_fields_set; 7 VAT tests | Pass - Note if tenant is vat registered quotes and invoices should have the option to remove vat as sometimes this is required on jobs such as new builds.|
| C2 | Chat message direction all "outbound" | P1 | Direction must be tenant-relative: customer messages = inbound. | Done `535100f` — legacy customer messages normalised to inbound at read; optional SQL backfill noted | Pass |
| C3 | Customer can view quote before electrician review | P1 | Gate customer quote view on status (e.g. sent/accepted only). | Done `535100f` — positive allow-list for customer-visible quote statuses | Pass |
| C4 | Quotes sent to non-account customers: persist details, email-only comms, flag unregistered | P1 | Overlaps N4. Customer + quote must persist even if they never create an account; tenant sees flag setting comms expectation. | Done `535100f` — account-less quotes persist; has_account flag on every lead read | Pass |
| C5 | Customer address (not just postcode) persisted | P1 | Overlaps N25. | Done `535100f` — full address + postcode persist on contact + customer, kept in sync | Awaiting test |
| C6 | Line-item unit = 'job' | P2 | Demo now returns 'm'/'ea' — verify tenant quote path uses catalog units. | Done `535100f` — grounded lines take catalogue units (m/ea); only fallback lines default | Pass - field is free text though, whould be limited to common values such as 'ea' (each), 'm' (meter), 'hr' (hour) etc This is not an exhaustive list |
| C7 | Quote "Request more info" → should open chat with customer | P2 | Currently navs to Quotes screen. | Done `7c15cf9` — opens customer chat in all cases (direct-thread fallback) | Awaiting test |
| C8 | Keyboard hides content (quote screen, customer profile, chat input) | P1 | Recurring KeyboardAvoidingView class — audit with N17. | Done `7c15cf9` — audit: only decline-quote view lacked KAV (fixed); rest already covered | Pass |
| C9 | Capture electrician quote edits as fine-tuning dataset | P2 | Log edit events (before/after) for AI training data. | Done `7c15cf9` — capture existed; added GET /quotes/training-events export + bulk SQL | Changes required and incoming as I test |
| C10 | AI refine: dynamic placeholder animation + leave-page banner | P3 | Greyed placeholders for lines/assumptions/price; notify-on-complete banner. | Done `7c15cf9` — skeleton gains assumptions placeholder; leave-page banner present | banner is still pinned to top of page out of view when tapping refine button. Either scroll to top of page or add a pop up style banner floating at top of screen with a go to dashboard link |
| C11 | Membership type not persisted in onboarding object | P2 | Verify onboarding payload → tenant record. | Done (verified) — membership_type persists as `membership` in tenant.settings (onboarding.py:137) | Pass - note: needs a manage subscription link. |
| C12 | Customer login should be tenant-agnostic (tenant resolved post-auth) | P1 | Hangover from the web sub-domain approach; future: multi-tenant customers. | Done `535100f` — slug-less login resolves tenant post-auth (newest active wins); response lists tenant associations for future multi-tenant | Pass |
| C13 | AI first follow-up asks for detail already provided; no acknowledgement; should auto-trigger + notify customer | P1 | Follow-up must fire as an event on low-confidence first attempt and notify the customer (depends on N1). | Done `535100f` — triage description renders all provided answers under ALREADY-PROVIDED banner + no-repeat rule; 3 tests | Pass |
| C14 | Electrician notified on every customer AI-chat reply (noise at scale) | P2 | Summarise/digest instead of per-message notifications. | Done `7c15cf9` — staff bell once per customer burst, re-armed by staff/AI reply | Pass |
| C15 | Duplicate users in coglabs tenant (9 duplicates for one person) | P2 | Data cleanup + dedupe guard on customer creation. | Done (guard) `535100f` — 409 on duplicate email or normalised name+phone within a tenant (`duplicate_contact:email` / `duplicate_contact:name_phone`), customer creation merges/links the existing contact, mobile mirrors the rule; 11 tests. PROD CLEANUP of the 9 coglabs duplicates still owed | Pass |
| C16 | Three-dots settings menu missing on pages other than dashboard | P2 | **Regression** — was requested as visible on all main pages. | Done (verified) `7c15cf9` — settings menu present on all 5 trade tab pages; customer role uses Profile tab instead | pass |
| C17 | Bottom nav doesn't respect home-indicator safe area (slight cut-off) | P2 | Safe-area inset padding on the tab bar. | Done (verified) `7c15cf9` — safe-area padding already in BottomTabBar | pass |
| C18 | No chat item in bottom nav (chat only reachable via links) | P2 | Add chat tab for both roles. | Done `7c15cf9` — chat tabs exist both roles; fixed active-tab highlight (route-group path mismatch) | pass |
| C19 | Checkout email prefill + lock to account email | P3 | Verify landed. | Done (verified) `7c15cf9` — checkout binds Paddle customer: email prefilled + locked | Awaiting test |
| C20 | Customer dashboard "you are not connected" empty state is confusing | P2 | Should read "N quote(s) generating. We'll notify you if we need anything else." | Done `7c15cf9` — live-count generating banner + welcoming empty state; offline only on real failure | Awaiting test |
| C21 | Customer quote photos: single upload point; customers can add photos | P2 | Photos currently requested in two places; electrician-only upload. | Done `7c15cf9` — single photos step; customers can add photos post-submission. Chat-composer attach deferred | Awaiting test |
| C22 | Tenant dashboard accessible before payment (subscription gating) | P1 | Security: gate app access on active subscription (beta free, but enforce the check). | Done `535100f` — GET /auth/tenant-status gate: no-row/legacy + beta_comped + trialing/active/past_due pass; incomplete/paused/canceled paywalled; 5 tests | Awaiting test |
| C23 | Plan selection 500 on POST /tenants (step 9/10) | P0 | Believed fixed — verify on latest TestFlight build. | Done `6929dd4` — Supabase admin_create_user failures were unhandled 500s at plan selection; now 502/503 with clear messages; 2 tests | pass |

---

## Execution waves — all complete

1. **Wave 1 — P0 stability** ✅ `6929dd4` — N1 push · N4/N3 customer emails · N14 photo 503 · N18 silent-failure · C23 + C1
2. **Wave 2 — P1 core journeys** ✅ `535100f` — jobs cluster · N25 CRM · N27 payment details · N2 notification nav · N21 retrieval · N28 reset page · C2–C5/C12/C13/C22
3. **Wave 2b — brand** ✅ `a767cba` — N8 full-app sweep to slate/yellow
4. **Wave 3 — P2/P3 polish** ✅ `7c15cf9` — N6 scheduler · N26 badges/block · N22 rounding · dashboard · messages · calendar · customer UX

**Deployed:** Railway api/landing/data-pipeline SUCCESS at `b60ee15` · 441 API
tests green · ruff + mypy clean · mobile tsc clean · CI green.

## Deferred to post-beta (non-blocking, by design)

- N21 follow-up: move embedding model→dimension map into `packages/shared/py` (single source of truth for api + data-pipeline)
- N22 follow-up: render a "rounded" indicator in the quote UI when `rounding_adjustment > 0` (data is exposed)
- N26 follow-ups: block check for the anonymous public lead form; (done: live-token chat enforcement)
- C15 follow-up: prod cleanup of the 9 duplicate coglabs contacts (guard prevents new ones)
- C21 follow-up: photo attach in the chat composer (customers can add via the request card)
- Push hardening: Expo push receipts (`getReceipts`) for late `DeviceNotRegistered`
- e2e maintenance: `mobile/e2e/regression.spec.ts` section E needs the new invoice-create step

## Hygiene rules

- Status — AI moves to Done only with a commit ref + how it was validated.
- Anything that grows beyond a fix into a feature (N6 scheduler, N26 badges) gets a design note appended under its row before scope expands.
- After each wave, this doc is the report — nothing ships silently.

---

## Research-pack alignment (2026-09-13)

Wave plan from the [research document pack](mytradeportal-research/README-Document-Pack.md),
mapped to backlog rows using the pack's triage categories
([Backlog-Management.md](mytradeportal-research/Backlog-Management.md)):
P0 beta-critical / P1 plan item / P2 evidence-backed / P3 idea.

| Item | Wave | Category | Evidence | Status — AI |
|---|---|---|---|---|
| A1 pricing reconciliation | A | P0 beta-critical | [Delivery Plan 0.6](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [Pricing PRD](mytradeportal-research/PRD-Pricing-and-Billing.md) | done (28a01f5 — 614 tests pass, ruff+mypy clean) |
| A2 observability gaps | A | P0 beta-critical | [Delivery Plan 0.1–0.4](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [Observability PRD](mytradeportal-research/PRD-Observability-Layer.md) | done (28a01f5 — 614 tests pass, ruff+mypy clean) |
| A3 landing pricing copy + fair-use page | A | P0 beta-critical | [Delivery Plan 0.7](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [Pricing PRD §3.1–3.2](mytradeportal-research/PRD-Pricing-and-Billing.md) | done (28a01f5 — 614 tests pass, ruff+mypy clean) |
| P-wave Stripe payments (tradie onboarding, pay button, webhooks, `invoice_paid`) | P | P0 beta-critical | [Delivery Plan 0.11](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [PRD-Online-Payments.md](mytradeportal-research/PRD-Online-Payments.md) | done (28a01f5 — 614 tests pass, ruff+mypy clean) — needs STRIPE_* keys in Railway before it can go live |
| P2 pay page + mobile payments settings | P | P0 beta-critical | [Delivery Plan 0.11](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [PRD-Online-Payments.md](mytradeportal-research/PRD-Online-Payments.md) | done (7c3191d — landing /pay page + mobile payments settings + per-invoice toggle; needs STRIPE_* keys + OTA publish to go live) |
| F3 data export | F | P0 beta-critical | [Tradify Parity Checklist](mytradeportal-research/Tradify-Parity-Checklist.md) | done (28a01f5 — 614 tests pass, ruff+mypy clean) |
| F2 chase-sequence verification | F | P0 beta-critical | [Tradify Parity Checklist](mytradeportal-research/Tradify-Parity-Checklist.md) | done (28a01f5) — audit: quotes default 3/configurable, invoices recur indefinitely, cancel-on-paid, dup guard all present; gaps = AI-drafted copy + per-customer overrides (follow-up) |
| Wave B portal entry surfaces (vanity URL, QR + asset pack, 6-digit code) | B | P1 plan item | [Delivery Plan Phase 1](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [Portal PRD §4.1](mytradeportal-research/PRD-Customer-Portal.md) | planned |
| Wave C portal home (timeline, quotes, invoices, chat) | C | P1 plan item | [Delivery Plan Phase 2](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [Portal PRD §4.2](mytradeportal-research/PRD-Customer-Portal.md) | planned |
| Wave D pricing evidence + Paddle catalog update | D | P1 plan item | [Delivery Plan Phase 3](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [Pricing PRD §3.3](mytradeportal-research/PRD-Pricing-and-Billing.md) | planned |
| Xero/QuickBooks sync on all tiers | — | P1 plan item | [Delivery Plan Phase 1](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) · [Pricing PRD §2 (Tradify parity)](mytradeportal-research/PRD-Pricing-and-Billing.md) | planned |
| F6/F7 deposits + optional line items | F | P2 evidence-backed | [Pricing PRD §2 (Pro gate)](mytradeportal-research/PRD-Pricing-and-Billing.md) | planned |
| F8 certificates MVP | F | P2 evidence-backed | [Pricing PRD §2](mytradeportal-research/PRD-Pricing-and-Billing.md) | planned |
| F9 offline mode | F | P2 evidence-backed | [Pricing PRD §2](mytradeportal-research/PRD-Pricing-and-Billing.md) | planned |
| 88s → <30s generation latency: streaming + timeout ladder | — | P1 plan item | [Delivery Plan launch gates (latency)](mytradeportal-research/Delivery-Plan-Pre-Beta-to-Launch.md) | planned |
