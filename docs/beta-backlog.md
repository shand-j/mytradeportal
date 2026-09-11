# Beta Backlog — My Trade Portal

Last triaged: 2026-09-11

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
| N1 | Push notifications never arrive on iOS (no banner/badge/sound when app closed; in-app banner only) | P0 | Reported ~5× across beta. Token plumbing exists (`mobile/src/lib/pushNotifications.ts`, `services/api/app/push.py`). Suspect Expo APNs production credentials or token/environment mismatch. Needs end-to-end trace: token registration → DB → Expo push API response. | Pending | |
| N2 | Bell-icon notification list items don't navigate to the notified thing | P1 | Nav targets missing on notification rows; each notification type needs a deep-link route. Carried: triage-complete / quote-refreshed notifications had the same complaint. | Pending | |
| N3 | Emails fail silently when customer has no contact information | P1 | Silent failure must become logged + surfaced; sending path should no-op with a warning, not drop. Related to N4. | Pending | |
| N4 | Customer emails broadly don't work (no quote-ready notifications, no reset emails received) | P0 | Resend vars are set (`RESEND_FROM_EMAIL=quotes@mytradeportal.co.uk`). Customer-facing event emails (quote ready, reset) appear unsent or unlogged. Trace `communications.py` send paths + Resend API responses; add delivery logging. Carried: "no email arrives" reported for password reset earlier. | Pending | |
| N5 | Job-detail message button opens iOS Messages | P2 | Should respect customer contact preference (Email or in-app Chat); SMS options were removed earlier. | Pending | |
| N6 | Quote/invoice reminder cron jobs don't exist | P1 | Confirmed: no scheduler exists anywhere in the API. Build one (APScheduler-style, in-process): quote reminders default 3 (configurable), invoice reminders recur indefinitely, cadence configurable in app settings. | Pending | |
| N7 | Apple calendar subscription button surfaces raw up.railway.app link | P2 | Needs proper `webcal:`/native add-to-calendar flow (ICS feed + `.ics` download / `addevent`-style). Carried: earlier "Apple calendar sync doesn't do anything" — partial fix landed as a link; make it native. | Pending | |

## Branding

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N8 | Revenue screen and dashboard metric highlights off-brand (yellow/green); full app needs brand audit | P1 | Brand is slate `#0F1E26` + yellow `#FFC107` (logo system). Audit every screen against `packages/shared/ts` tokens; replace ad-hoc metric colours. | Pending | |

## Jobs

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N9 | Job creation only allows existing customers | P1 | Add inline "new customer" path in job creation (quote agreed off-app). | Pending | |
| N10 | Navigation forces Apple Maps install | P2 | Use platform-neutral map URLs so the default maps app handles it. | Pending | |
| N11 | Job detail "assigned to" uneditable and undefinable at creation; job notes not editable | P1 | Add assignee selection (tenant members) + editable notes on job detail. | Pending | |
| N12 | AI quote assumptions/footnotes should appear in job notes | P2 | Copy assumptions + notes into the job's notes when converting quote → job. | Pending | |
| N13 | Uploaded images should appear attached to the job | P1 | Photos uploaded on the quote should carry through to the job record. | Pending | |
| N14 | Photo upload returns 503 | P0 | Regression — likely from the MinIO private-endpoint change (`minio.railway.internal`). Verify `files.py` + storage config end-to-end. | Pending | |
| N15 | Job creation needs date picker + time picker + duration; pre-fill duration from quoted hours | P1 | e.g. 3 lines × 10h → job spans 30 working hours. Duration derived from quote line items, editable. | Pending | |
| N16 | Working hours configurable in the app | P2 | Feeds duration suggestion and calendar slot logic. | Pending | |
| N17 | New-job page has no keyboard-avoiding layout | P1 | Recurring class — quote screen, customer profile, chat input all had this. Audit KeyboardAvoidingView across form screens. | Pending | |
| N18 | New job: select a quote → prefill duration/date/customer/start time/notes from calendar slots; without a quote "complete and send invoice" silently fails | P0 | Silent failure is the P0; prefill is P1. Disable/redirect the invoice action when no quote is attached. | Pending | |
| N19 | Jobs with no quote → AI create-invoice page | P1 | Reuse quote-generation UI (editable, AI-built) but the CTA creates an invoice directly and navs to the invoice send page. | Pending | |
| N20 | Calendar "New job" button → plain `+` symbol, no border | P3 | Cosmetic. | Pending | |

## Quotes / AI

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N21 | Quotes assume "no catalog match" for items known to be in the cost-item DB (consumer units, sockets, twin & earth) | P1 | Retrieval/index regression. Data was ported to prod Qdrant; suspect embedding model mismatch or index not hit by tenant retrieval. Investigate `app/rag/retrieval.py`. | Pending | |
| N22 | Configurable toggle: round quote totals up to nearest £5 or £10 | P2 | e.g. £1236.40 → £1240. Setting lives in tenant settings; applies to quote + invoice totals. | Pending | |
| N23 | Quote convert button → "Convert to…" iOS action sheet (Job or Invoice) | P1 | Replace single convert-to-invoice action with an ActionSheet navigating to the right page. | Pending | |

## Customers / CRM

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N24 | "Could not find messages" error on existing coglabs.ai tenant | P1 | Tenant-scoped query returns nothing and surfaces an error instead of an empty inbox. | Pending | |
| N25 | Can't edit customers; need customer detail screen with editable fields; parking/access persisted and auto-populated on quote/job creation | P1 | Carried: address not persisted (only postcode); contact phone/address empty in settings despite onboarding capture. Chain: customer → quote → job inherits parking/access. | Pending | |
| N26 | Badges: "Late Payer"/"Non-payer" (bad-debt history) and "Time Waster" (>2 quotes, never replied) — auto-set, manually overridable; block button to stop customer login/quotes/messages | P2 | Needs rules engine over invoices/quotes + `blocked` flag enforced in auth + quote creation. | Pending | |

## Invoices / payments

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N27 | Invoice payment details in the email; payment details configurable in settings | P1 | Confirmed: no bank/payment-details config exists anywhere. Add settings fields (account name, sort code, account number, reference format) + include in invoice email template. | Pending | |

## Auth

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N28 | Reset-password email links to the admin portal (back office) | P1 | Build reset page on mytradeportal.co.uk: new password + reconfirm, displays user email, signed single-use token, only for app-requested resets. Landing site addition + API token issuing change. | Pending | |

## Messages

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N29 | Messages screen: `+` new-message button; see/search CRM customers with app accounts | P2 | Recipients limited to customers with app accounts (install known). | Pending | |

## Dashboard

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| N30 | Remove "New lead" button (leads concept removed from the app) | P2 | CTA should be "New Customer" on the customers screen (earlier rename — verify it landed everywhere). | Pending | |
| N31 | "Top Leads" should surface the best 2 new quotes (revenue + ability to fulfil) | P2 | Rank new quotes by value × readiness, not just recency. | Pending | |
| N32 | Port revenue report + "time saved" metric onto the dashboard; dense job lists shouldn't dominate | P2 | Part of the rebranding pass; shows app value in full focus. | Pending | |
| N33 | Stat cards: drop duplicate "outstanding" card, fix dead clicks, order quotes FIFO | P2 | "Active leads" and "outstanding quotes" are the same thing — drop one; outstanding quotes → quotes page with New filter, FIFO by submission; hours-saved beside outstanding-quotes. | Pending | |

## Carried from earlier reports

| Ref | Item | Priority | Notes / root-cause hypothesis | Status — AI | Status — User |
|---|---|---|---|---|---|
| C1 | VAT still applied when tenant is not VAT registered | P1 | **Regression — re-verify.** Believed fixed twice; latest report says still broken. Check VAT rate resolution in quote + invoice generation against tenant flag. | Pending | |
| C2 | Chat message direction all "outbound" | P1 | Direction must be tenant-relative: customer messages = inbound. | Pending | |
| C3 | Customer can view quote before electrician review | P1 | Gate customer quote view on status (e.g. sent/accepted only). | Pending | |
| C4 | Quotes sent to non-account customers: persist details, email-only comms, flag unregistered | P1 | Overlaps N4. Customer + quote must persist even if they never create an account; tenant sees flag setting comms expectation. | Pending | |
| C5 | Customer address (not just postcode) persisted | P1 | Overlaps N25. | Pending | |
| C6 | Line-item unit = 'job' | P2 | Demo now returns 'm'/'ea' — verify tenant quote path uses catalog units. | Pending | |
| C7 | Quote "Request more info" → should open chat with customer | P2 | Currently navs to Quotes screen. | Pending | |
| C8 | Keyboard hides content (quote screen, customer profile, chat input) | P1 | Recurring KeyboardAvoidingView class — audit with N17. | Pending | |
| C9 | Capture electrician quote edits as fine-tuning dataset | P2 | Log edit events (before/after) for AI training data. | Pending | |
| C10 | AI refine: dynamic placeholder animation + leave-page banner | P3 | Greyed placeholders for lines/assumptions/price; notify-on-complete banner. | Pending | |
| C11 | Membership type not persisted in onboarding object | P2 | Verify onboarding payload → tenant record. | Pending | |
| C12 | Customer login should be tenant-agnostic (tenant resolved post-auth) | P1 | Hangover from the web sub-domain approach; future: multi-tenant customers. | Pending | |
| C13 | AI first follow-up asks for detail already provided; no acknowledgement; should auto-trigger + notify customer | P1 | Follow-up must fire as an event on low-confidence first attempt and notify the customer (depends on N1). | Pending | |
| C14 | Electrician notified on every customer AI-chat reply (noise at scale) | P2 | Summarise/digest instead of per-message notifications. | Pending | |
| C15 | Duplicate users in coglabs tenant (9 duplicates for one person) | P2 | Data cleanup + dedupe guard on customer creation. | Pending | |
| C16 | Three-dots settings menu missing on pages other than dashboard | P2 | **Regression** — was requested as visible on all main pages. | Pending | |
| C17 | Bottom nav doesn't respect home-indicator safe area (slight cut-off) | P2 | Safe-area inset padding on the tab bar. | Pending | |
| C18 | No chat item in bottom nav (chat only reachable via links) | P2 | Add chat tab for both roles. | Pending | |
| C19 | Checkout email prefill + lock to account email | P3 | Verify landed. | Pending | |
| C20 | Customer dashboard "you are not connected" empty state is confusing | P2 | Should read "N quote(s) generating. We'll notify you if we need anything else." | Pending | |
| C21 | Customer quote photos: single upload point; customers can add photos | P2 | Photos currently requested in two places; electrician-only upload. | Pending | |
| C22 | Tenant dashboard accessible before payment (subscription gating) | P1 | Security: gate app access on active subscription (beta free, but enforce the check). | Pending | |
| C23 | Plan selection 500 on POST /tenants (step 9/10) | P0 | Believed fixed — verify on latest TestFlight build. | Pending | |

---

## Execution waves

1. **Wave 1 — P0 stability:** N1 push · N4/N3 customer emails · N14 photo 503 · N18 silent-failure · C23 + C1 verification
2. **Wave 2 — P1 core journeys:** jobs cluster (N9, N11, N13, N15, N17, N19, N23) · N25 CRM · N27 payment details · N2 notification nav · N21 catalog retrieval · N8 brand audit · N28 password-reset page · C2/C3/C4/C5/C8/C12/C13/C22
3. **Wave 3 — P2/P3 polish:** N6 reminders (scheduler build) · N26 badges/block · N22 rounding · dashboard set (N30–33) · remaining carried items

## Hygiene rules

- Status — AI moves to Done only with a commit ref + how it was validated.
- Anything that grows beyond a fix into a feature (N6 scheduler, N26 badges) gets a design note appended under its row before scope expands.
- After each wave, this doc is the report — nothing ships silently.
