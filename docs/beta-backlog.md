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
| N1 | Push notifications never arrive on iOS (no banner/badge/sound when app closed; in-app banner only) | P0 | Reported ~5× across beta. Token plumbing exists (`mobile/src/lib/pushNotifications.ts`, `services/api/app/push.py`). Suspect Expo APNs production credentials or token/environment mismatch. Needs end-to-end trace: token registration → DB → Expo push API response. | Done (code) `6929dd4` — ticket errors now parsed (were logged as success), sound/high-priority + deep-link data, customer gets quote-ready push, dead-token cleanup; 7 tests. Needs APNs creds on EAS + on-device verify | Awaiting test |
| N2 | Bell-icon notification list items don't navigate to the notified thing | P1 | Nav targets missing on notification rows; each notification type needs a deep-link route. Carried: triage-complete / quote-refreshed notifications had the same complaint. | Done `535100f` — shared type→route map for in-app rows + push taps; broken stored links fixed (`/quote/` → `/quotes/`); graceful no-op on dead ends; 38 tests | Awaiting test |
| N3 | Emails fail silently when customer has no contact information | P1 | Silent failure must become logged + surfaced; sending path should no-op with a warning, not drop. Related to N4. | Done `6929dd4` — no-contact case logs `email_skipped_no_contact_email` warning instead of dropping; tested | Awaiting test |
| N4 | Customer emails broadly don't work (no quote-ready notifications, no reset emails received) | P0 | Resend vars are set (`RESEND_FROM_EMAIL=quotes@mytradeportal.co.uk`). Customer-facing event emails (quote ready, reset) appear unsent or unlogged. Trace `communications.py` send paths + Resend API responses; add delivery logging. Carried: "no email arrives" reported for password reset earlier. | Done `6929dd4` — send_event_email wrapper + welcome/triage-question/quote-accepted emails, Resend errors logged loudly; 14 tests. Live-delivery verify pending | Awaiting test |
| N5 | Job-detail message button opens iOS Messages | P2 | Should respect customer contact preference (Email or in-app Chat); SMS options were removed earlier. | Done `7c15cf9` — routes on preferred_contact_method (chat/email/phone with fallbacks) | Awaiting test |
| N6 | Quote/invoice reminder cron jobs don't exist | P1 | Confirmed: no scheduler exists anywhere in the API. Build one (APScheduler-style, in-process): quote reminders default 3 (configurable), invoice reminders recur indefinitely, cadence configurable in app settings. | Done `7c15cf9` — scheduler.py: quote reminders (default 3, configurable) then stop; invoice reminders recur until paid; cadence in Follow-ups settings; 10 tests | Awaiting test |
| N7 | Apple calendar subscription button surfaces raw up.railway.app link | P2 | Needs proper `webcal:`/native add-to-calendar flow (ICS feed + `.ics` download / `addevent`-style). Carried: earlier "Apple calendar sync doesn't do anything" — partial fix landed as a link; make it native. | Done `7c15cf9` — webcal feed-link + native subscribe wired in settings; iOS-recognised ICS headers; CALENDAR_FEED_BASE_URL override available | Awaiting test |

## Branding

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N8 | Revenue screen and dashboard metric highlights off-brand (yellow/green); full app needs brand audit | P1 | Brand is slate `#0F1E26` + yellow `#FFC107` (logo system). Audit every screen against `packages/shared/ts` tokens; replace ad-hoc metric colours. | Done `a767cba` — token-level fix + 34-screen sweep; slate/yellow metric treatment, LiveBadge shared component, white-label intact | Awaiting test |

## Jobs

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N9 | Job creation only allows existing customers | P1 | Add inline "new customer" path in job creation (quote agreed off-app). | Done `535100f` — inline New customer toggle on job create (dedupe-aware) | Awaiting test |
| N10 | Navigation forces Apple Maps install | P2 | Use platform-neutral map URLs so the default maps app handles it. | Done `7c15cf9` — universal maps URL first, Apple scheme fallback only | Awaiting test |
| N11 | Job detail "assigned to" uneditable and undefinable at creation; job notes not editable | P1 | Add assignee selection (tenant members) + editable notes on job detail. | Done `535100f` — assignee chips at create + Change editor on detail, persisted notes editor; server validates same-tenant staff | Awaiting test |
| N12 | AI quote assumptions/footnotes should appear in job notes | P2 | Copy assumptions + notes into the job's notes when converting quote → job. | Done `535100f` — convert-to-job appends AI assumptions + notes to job notes | Awaiting test |
| N13 | Uploaded images should appear attached to the job | P1 | Photos uploaded on the quote should carry through to the job record. | Done `535100f` — quote photos linked to job on convert; thumbnail row on job detail | Awaiting test |
| N14 | Photo upload returns 503 | P0 | Regression — likely from the MinIO private-endpoint change (`minio.railway.internal`). Verify `files.py` + storage config end-to-end. | Done `6929dd4` — MinIO bare host dialed :80; endpoint normalizer adds :9000, IaC pinned to private domain:9000; 9 tests. Live upload verify pending | Awaiting test |
| N15 | Job creation needs date picker + time picker + duration; pre-fill duration from quoted hours | P1 | e.g. 3 lines × 10h → job spans 30 working hours. Duration derived from quote line items, editable. | Done `535100f` — native date/time pickers, duration prefilled from quoted hours, editable | Awaiting test |
| N16 | Working hours configurable in the app | P2 | Feeds duration suggestion and calendar slot logic. | Done `7c15cf9` — working hours settings screen; drives /appointments/availability; 4 tests | Awaiting test |
| N17 | New-job page has no keyboard-avoiding layout | P1 | Recurring class — quote screen, customer profile, chat input all had this. Audit KeyboardAvoidingView across form screens. | Done `535100f` — KeyboardAvoidingView on job create + invoice create | Awaiting test |
| N18 | New job: select a quote → prefill duration/date/customer/start time/notes from calendar slots; without a quote "complete and send invoice" silently fails | P0 | Silent failure is the P0; prefill is P1. Disable/redirect the invoice action when no quote is attached. | Done `535100f` — quote selection prefills title/customer/duration + first-free-slot suggestion; silent-failure half shipped in `6929dd4` | Awaiting test |
| N19 | Jobs with no quote → AI create-invoice page | P1 | Reuse quote-generation UI (editable, AI-built) but the CTA creates an invoice directly and navs to the invoice send page. | Done `535100f` — AI create-invoice page (reuses generation pipeline, editable lines, direct invoice → send page) | Awaiting test |
| N20 | Calendar "New job" button → plain `+` symbol, no border | P3 | Cosmetic. | Done `7c15cf9` — borderless ghost + | Awaiting test |

## Quotes / AI

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N21 | Quotes assume "no catalog match" for items known to be in the cost-item DB (consumer units, sockets, twin & earth) | P1 | Retrieval/index regression. Data was ported to prod Qdrant; suspect embedding model mismatch or index not hit by tenant retrieval. Investigate `app/rag/retrieval.py`. | Done `535100f` — root cause: retrieval read-path wiped the index on the embedding-model bump; now read-only + loud errors. PROD REINDEX REQUIRED (data-pipeline import) | Awaiting test |
| N22 | Configurable toggle: round quote totals up to nearest £5 or £10 | P2 | e.g. £1236.40 → £1240. Setting lives in tenant settings; applies to quote + invoice totals. | Done `7c15cf9` — quote_rounding 0/5/10, rounding_adjustment on quotes+invoices; 7 tests. UI indicator for rounded totals deferred | Awaiting test |
| N23 | Quote convert button → "Convert to…" iOS action sheet (Job or Invoice) | P1 | Replace single convert-to-invoice action with an ActionSheet navigating to the right page. | Done `535100f` — Convert to… ActionSheet (Job / Invoice) on iOS | Awaiting test |

## Customers / CRM

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N24 | "Could not find messages" error on existing coglabs.ai tenant | P1 | Tenant-scoped query returns nothing and surfaces an error instead of an empty inbox. | Done `7c15cf9` — legacy contact-linked threads 403'd; ownership now accepts contact link, 404 renders empty state; 9 tests | Awaiting test |
| N25 | Can't edit customers; need customer detail screen with editable fields; parking/access persisted and auto-populated on quote/job creation | P1 | Carried: address not persisted (only postcode); contact phone/address empty in settings despite onboarding capture. Chain: customer → quote → job inherits parking/access. | Done `535100f` — editable customer detail screen; parking/access/property persisted + pre-fill quote intake; contact payload contract documented | Awaiting test |
| N26 | Badges: "Late Payer"/"Non-payer" (bad-debt history) and "Time Waster" (>2 quotes, never replied) — auto-set, manually overridable; block button to stop customer login/quotes/messages | P2 | Needs rules engine over invoices/quotes + `blocked` flag enforced in auth + quote creation. | Done `7c15cf9` — auto badges + tri-state overrides + block enforced (login/quote-request/live chat tokens); 12 tests. Anonymous lead-form block deferred | Awaiting test |

## Invoices / payments

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N27 | Invoice payment details in the email; payment details configurable in settings | P1 | Confirmed: no bank/payment-details config exists anywhere. Add settings fields (account name, sort code, account number, reference format) + include in invoice email template. | Done `535100f` — bank details settings UI + invoice email block (reference = invoice number); 5 tests | Awaiting test |

## Auth

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N28 | Reset-password email links to the admin portal (back office) | P1 | Build reset page on mytradeportal.co.uk: new password + reconfirm, displays user email, signed single-use token, only for app-requested resets. Landing site addition + API token issuing change. | Done `535100f` — /reset-password on mytradeportal.co.uk (email shown, new+confirm, single-use token, newest-link-only); PASSWORD_RESET_BASE_URL set in prod | Awaiting test |

## Messages

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N29 | Messages screen: `+` new-message button; see/search CRM customers with app accounts | P2 | Recipients limited to customers with app accounts (install known). | Done `7c15cf9` — + button, searchable account-holding customers, POST /communications/threads; staff-started chats notify customer | Awaiting test |

## Dashboard

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N30 | Remove "New lead" button (leads concept removed from the app) | P2 | CTA should be "New Customer" on the customers screen (earlier rename — verify it landed everywhere). | Done `7c15cf9` — New lead button removed; New Customer CTA verified on CRM screen | Awaiting test |
| N31 | "Top Leads" should surface the best 2 new quotes (revenue + ability to fulfil) | P2 | Rank new quotes by value × readiness, not just recency. | Done `7c15cf9` — top-2 new quotes ranked value x readiness (intake completeness, call-back penalty, flagged sink) | Awaiting test |
| N32 | Port revenue report + "time saved" metric onto the dashboard; dense job lists shouldn't dominate | P2 | Part of the rebranding pass; shows app value in full focus. | Done `7c15cf9` — revenue summary + AI time-saved (25 min/draft, server-derived) on dashboard; job list capped at 3/day | Awaiting test |
| N33 | Stat cards: drop duplicate "outstanding" card, fix dead clicks, order quotes FIFO | P2 | "Active leads" and "outstanding quotes" are the same thing — drop one; outstanding quotes → quotes page with New filter, FIFO by submission; hours-saved beside outstanding-quotes. | Done `7c15cf9` — duplicate card dropped, side-by-side hours-saved/outstanding, ?filter=new&sort=fifo consumed by quotes screen | Awaiting test |

## Carried from earlier reports

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| C1 | VAT still applied when tenant is not VAT registered | P1 | **Regression — re-verify.** Believed fixed twice; latest report says still broken. Check VAT rate resolution in quote + invoice generation against tenant flag. | Done `6929dd4` — schema default 0.20 made the tenant fallback dead code; fixed via model_fields_set; 7 VAT tests | Awaiting test |
| C2 | Chat message direction all "outbound" | P1 | Direction must be tenant-relative: customer messages = inbound. | Done `535100f` — legacy customer messages normalised to inbound at read; optional SQL backfill noted | Awaiting test |
| C3 | Customer can view quote before electrician review | P1 | Gate customer quote view on status (e.g. sent/accepted only). | Done `535100f` — positive allow-list for customer-visible quote statuses | Awaiting test |
| C4 | Quotes sent to non-account customers: persist details, email-only comms, flag unregistered | P1 | Overlaps N4. Customer + quote must persist even if they never create an account; tenant sees flag setting comms expectation. | Done `535100f` — account-less quotes persist; has_account flag on every lead read | Awaiting test |
| C5 | Customer address (not just postcode) persisted | P1 | Overlaps N25. | Done `535100f` — full address + postcode persist on contact + customer, kept in sync | Awaiting test |
| C6 | Line-item unit = 'job' | P2 | Demo now returns 'm'/'ea' — verify tenant quote path uses catalog units. | Done `535100f` — grounded lines take catalogue units (m/ea); only fallback lines default | Awaiting test |
| C7 | Quote "Request more info" → should open chat with customer | P2 | Currently navs to Quotes screen. | Done `7c15cf9` — opens customer chat in all cases (direct-thread fallback) | Awaiting test |
| C8 | Keyboard hides content (quote screen, customer profile, chat input) | P1 | Recurring KeyboardAvoidingView class — audit with N17. | Done `7c15cf9` — audit: only decline-quote view lacked KAV (fixed); rest already covered | Awaiting test |
| C9 | Capture electrician quote edits as fine-tuning dataset | P2 | Log edit events (before/after) for AI training data. | Done `7c15cf9` — capture existed; added GET /quotes/training-events export + bulk SQL | Awaiting test |
| C10 | AI refine: dynamic placeholder animation + leave-page banner | P3 | Greyed placeholders for lines/assumptions/price; notify-on-complete banner. | Done `7c15cf9` — skeleton gains assumptions placeholder; leave-page banner present | Awaiting test |
| C11 | Membership type not persisted in onboarding object | P2 | Verify onboarding payload → tenant record. | Done (verified) — membership_type persists as `membership` in tenant.settings (onboarding.py:137) | Awaiting test |
| C12 | Customer login should be tenant-agnostic (tenant resolved post-auth) | P1 | Hangover from the web sub-domain approach; future: multi-tenant customers. | Done `535100f` — slug-less login resolves tenant post-auth (newest active wins); response lists tenant associations for future multi-tenant | Awaiting test |
| C13 | AI first follow-up asks for detail already provided; no acknowledgement; should auto-trigger + notify customer | P1 | Follow-up must fire as an event on low-confidence first attempt and notify the customer (depends on N1). | Done `535100f` — triage description renders all provided answers under ALREADY-PROVIDED banner + no-repeat rule; 3 tests | Awaiting test |
| C14 | Electrician notified on every customer AI-chat reply (noise at scale) | P2 | Summarise/digest instead of per-message notifications. | Done `7c15cf9` — staff bell once per customer burst, re-armed by staff/AI reply | Awaiting test |
| C15 | Duplicate users in coglabs tenant (9 duplicates for one person) | P2 | Data cleanup + dedupe guard on customer creation. | Done (guard) `535100f` — 409 on duplicate email or normalised name+phone within a tenant (`duplicate_contact:email` / `duplicate_contact:name_phone`), customer creation merges/links the existing contact, mobile mirrors the rule; 11 tests. PROD CLEANUP of the 9 coglabs duplicates still owed | Awaiting test |
| C16 | Three-dots settings menu missing on pages other than dashboard | P2 | **Regression** — was requested as visible on all main pages. | Done (verified) `7c15cf9` — settings menu present on all 5 trade tab pages; customer role uses Profile tab instead | Awaiting test |
| C17 | Bottom nav doesn't respect home-indicator safe area (slight cut-off) | P2 | Safe-area inset padding on the tab bar. | Done (verified) `7c15cf9` — safe-area padding already in BottomTabBar | Awaiting test |
| C18 | No chat item in bottom nav (chat only reachable via links) | P2 | Add chat tab for both roles. | Done `7c15cf9` — chat tabs exist both roles; fixed active-tab highlight (route-group path mismatch) | Awaiting test |
| C19 | Checkout email prefill + lock to account email | P3 | Verify landed. | Done (verified) `7c15cf9` — checkout binds Paddle customer: email prefilled + locked | Awaiting test |
| C20 | Customer dashboard "you are not connected" empty state is confusing | P2 | Should read "N quote(s) generating. We'll notify you if we need anything else." | Done `7c15cf9` — live-count generating banner + welcoming empty state; offline only on real failure | Awaiting test |
| C21 | Customer quote photos: single upload point; customers can add photos | P2 | Photos currently requested in two places; electrician-only upload. | Done `7c15cf9` — single photos step; customers can add photos post-submission. Chat-composer attach deferred | Awaiting test |
| C22 | Tenant dashboard accessible before payment (subscription gating) | P1 | Security: gate app access on active subscription (beta free, but enforce the check). | Done `535100f` — GET /auth/tenant-status gate: no-row/legacy + beta_comped + trialing/active/past_due pass; incomplete/paused/canceled paywalled; 5 tests | Awaiting test |
| C23 | Plan selection 500 on POST /tenants (step 9/10) | P0 | Believed fixed — verify on latest TestFlight build. | Done `6929dd4` — Supabase admin_create_user failures were unhandled 500s at plan selection; now 502/503 with clear messages; 2 tests | Awaiting test |

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
