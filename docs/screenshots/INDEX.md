# Screenshot index — go-live visual record

Captured 2026-09-01 against the local seeded demo estate (tenant `sparks`,
Sparks & Sons Electrical) with `scripts/capture-screenshots.mjs`:

- **Web back-office** — Vite dev server (captured via `demo.localhost:3000`,
  the dev server redirects `localhost:3000` there), 1440×900 @2x, full-page PNG.
  Logged in as `sam@sparksandsons.co.uk` (owner).
- **Mobile app** — Expo web build on `:8090` (`EXPO_PUBLIC_API_BASE_URL=http://localhost:8000`),
  402×874 @2x. Trade session: `sam@sparksandsons.co.uk`; customer session:
  `margaret.holloway@example.co.uk`. Note: the API's CORS whitelist only allows
  the `:3000` origin, so the mobile web capture ran Chromium with
  `--disable-web-security` (capture harness only — the shipped app is native and
  unaffected; see defect M1).

`capture-report.json`, `web-console-errors.json` and `mobile-console-errors.json`
hold the machine-readable capture log and per-page console errors.

## Web (`web/`)

| File | Page | What it shows | Defects |
|---|---|---|---|
| `login.png` | `/login` | Slug + email + password sign-in card | TanStack Query devtools bubble (palm-tree icon) bottom-right appears on web captures — dev-only widget; **FIXED**: now gated behind `import.meta.env.DEV` in `main.tsx` and verified absent from the `pnpm build` bundle (still visible in dev-server captures, expected) |
| `dashboard.png` | `/` | KPI cards, revenue chart, service mix | Revenue Overview Y-axis ticks repeat "£0k" (broken tick formatting); Service Mix buckets by first word of line-item description ("Led", "Ev", "Eicr", "Double"…) instead of service category |
| `calendar-month.png` | `/calendar` | Month grid, September 2026 | **FIXED**: all 6 seeded appointments render as chips on the correct days, today highlighted, prev/next month navigation works (root cause: appointments hook returned raw API objects, so `startTime` was undefined) |
| `calendar-week.png` | `/calendar/week` | Week grid 07:00–19:00, day columns Mon 31 – Sun 6 | **FIXED**: `/calendar/:view` param now drives the view; week view renders a time grid with blocks positioned by start time, plus an "Outside 7:00–19:00" footer for off-hours appointments. `calendar-day.png` (new) shows the single-column day view |
| `quotes-list.png` | `/quotes` | 5 seeded quotes, status chips, AI sparkle column | Page title "Quotes" duplicated ("Quotes" header + "Quotes 5" subheader); money formatting inconsistent (£450 vs £976.8 vs £1,120.8 — no 2dp) |
| `quotes-generate-ai-dialog.png` | `/quotes` | "Generate Quote with AI" modal (existing customer / new lead, property type, job description) | — |
| `quote-detail-ai.png` | `/quotes/79571042…` | AI draft "Consumer unit replacement" £684, line items with AI sparkle, AI panel (confidence 87%) | Description repeated verbatim under the customer block (title duplicated as body text) |
| `quote-detail-ai-refine.png` | same, scrolled | Warnings, assumptions, catalogue note, "Refine with AI" textarea + button | — |
| `quote-detail-ai-sent.png` | `/quotes/a8b3ebe7…` | AI-generated + manually edited sent quote (£942, conf 74%), quote history | Same duplicate-description nit |
| `jobs-board.png` | `/jobs` | Kanban: scheduled / in progress / completed / cancelled | **FIXED**: job cards show the linked quote's total (£1,120.80 / £450.00) — the API has no job value field, so `useJobs` now merges quote totals via `quote_id` |
| `job-detail.png` | `/jobs/af2e729d…` | In-progress EV charger site visit | Value fixed (£1,120.80, from the linked quote); remaining nits: empty location row (pin icon, no address), job title duplicated (mono heading + plain text repeat) |
| `customers-list.png` | `/customers` | 6 contacts as cards | "£0.0k Lifetime" formatting oddity |
| `customer-detail.png` | `/customers/451a971f…` | Margaret Holloway: contact info, quotes (1), jobs (0), invoices (0), stats | Quote row shows title twice (mono + grey text); "Total Spent £0" for a customer with a £684 draft (stats likely only count paid — acceptable, but reads wrong) |
| `invoices-list.png` | `/invoices` | INV-001/002/003, paid/outstanding/overdue cards | **FIXED**: 2dp formatting throughout (£1,120.80) |
| `invoice-detail-paid.png` | `/invoices/9b0d5d56…` | INV-003 paid, payment row | **FIXED**: line totals use the API per-line total (1×£180 → £180.00, no more £32,400); VAT label shows "VAT (20%)"; all amounts 2dp |
| `invoice-detail-draft.png` | `/invoices/eef6c2d6…` | INV-001 draft | Line totals and VAT label fixed as above; "Send Reminder" offered on an unsent draft |
| `reviews.png` | `/reviews` | 3 seeded reviews with rating/date/status, stats cards | **FIXED**: no longer crashes — reviews map from the API shape (no embedded customer) and the row falls back to reviewer-name/initials or a "Customer" placeholder avatar |
| `ai-insights.png` | `/ai-insights` | AI quote performance KPIs + monthly bar chart | Sep bar pair unlabeled (grey bar has no legend) — minor |
| `settings-business.png` | `/settings` (Business tab) | Business details + pricing form, prefilled | — |
| `settings-branding.png` | Branding tab | Logo upload, logo URL, brand colours | — |
| `settings-services.png` | Services tab | Services editor | **Empty with no empty-state message** — just "SERVICES" header and Add/Save buttons |
| (not captured) | Integrations tab | — | Tab hidden: `external_integrations` feature flag is OFF locally (fail-closed default, expected) |

## Mobile (`mobile/`)

| File | Route | What it shows | Defects |
|---|---|---|---|
| `entry.png` | `/` | Welcome + 6-digit business code gate + register/login links | — |
| `trade-login.png` | `/trade-login` | Electrician login form (default blue theme — tenant theme loads only after auth) | **M1:** with a stock browser the page cannot log in at all against the local API — CORS blocks `:8090` and the error is misreported as "Invalid email or password." (any failure maps to that message in `LoginScreen.handleSubmit`) |
| `customer-login.png` | `/customer-login` (deep-linked) | Customer login + "Choose a business on the previous screen first" warning | Warning is correct for a cold deep-link; note the form silently no-ops on submit in this state (no error shown) because the business slug lives only in in-memory Zustand state |
| `trade-dashboard.png` | `/(trade)/dashboard` | New-lead banner, New EICR CTA, active leads / outstanding quotes, top leads | **M2:** this shot required a manual navigation — successful trade login never leaves `/trade-login` (no `onSuccess` navigation in `LoginScreen`). Raw urgency enums visible: "this_week", "this_month", "flexible"; two leads titled "New request" (AI summary not shown) |
| `trade-quotes.png` | `/(trade)/quotes` | Combined leads + quotes list ("Quotes / Leads", LIVE badge) | Mixed badge casing (NEW vs Draft/Sent); raw urgency enums |
| `trade-leads.png` | `/(trade)/leads` | Same data, "Leads" header | Same notes; "EICR … Sent" badge while web shows the quote as invoiced — status mapping diverges between apps |
| `trade-lead-detail-triage.png` | `/(trade)/lead/827ad7e8…` | Processed lead (Emma Whitfield), notes, Generate AI quote / Open chat / Request more info / Mark as dead | Title shows "New request" + NEW badge despite status `processed`; AI-extracted summary and confidence not surfaced; US date format "9/1/2026" in a UK product |
| `trade-request-info-chat.png` | `/(trade)/request-info?leadId=…` | Seeded 4-message customer ↔ AI triage thread | — |
| `trade-messages-thread.png` | `/(trade)/messages?quoteRequestId=…` | Same thread in the Messages chrome (AI badge top-right) | — |
| `trade-quote-review-ai.png` | `/(trade)/quote/13911b5f…` | AI quote review/edit: confidence 87% badge, warnings + assumptions, Time & materials / Per point toggle, totals | Line-item editor card is clipped — the Qty/Unit/Price labels render but the input row is cut off / overlapped by the Subtotal block |
| `trade-quote-intake.png` | `/(trade)/quote-intake?leadId=…` | Intake form (property type, bedrooms, CU location…) | Sticky "Generate AI quote" button overlaps the bottom of the "Consumer unit location" card; lead summary shows raw "this_month" |
| `trade-customers.png` | `/(trade)/customers` | — | **"Customer CRM coming soon" placeholder** although the backend has 6 seeded contacts — mobile CRM not wired to the API |
| `trade-calendar-week.png` | `/(trade)/calendar` (Week tab) | Week grid, EV charger booking | Today's booking shows **05:56** (seed was 10:56 UTC) — timezone shifted; at 402px only ~2 day columns are visible with no horizontal-scroll affordance |
| `trade-invoices.png` | `/(trade)/invoices` | Outstanding £1121 / Paid £450, 3 invoice cards | Invoice cards titled by first line item ("LED downlight — fire-rated, dimmabl…") instead of invoice number; US dates ("Due 9/15/2026"); totals formatting inconsistent (£1121 vs £1120.80) |
| `trade-invoice-detail-paid.png` | `/(trade)/invoice/41396fb2…` | INV-003 paid, payment received card | US dates; otherwise correct (mobile shows correct line-level maths — the total bug is web-only) |
| `trade-certificates.png` | `/(trade)/certificates` | Digital EICR intro + "No certificates yet" | Genuine empty state (nothing seeded) |
| `trade-certificate-new.png` | `/(trade)/certificate/new` → Add circuit | Circuit entry form with live BS 7671 validation panel | Placeholder values (0.62, 1.44, 28, >200) look like entered data — risk of submitting placeholders; "INCOMPLETE" state correct |
| `trade-settings.png` | `/(trade)/settings` | Signed-in-as, shareable customer code 602154, settings links | — |
| `trade-analytics.png` | `/(trade)/analytics` | Revenue & costs cards, estimated profit | "Costs £0" — no cost data seeded (jobs carry no value, see web jobs defect) |
| `trade-branding.png` | `/(trade)/branding` | Branding form + colour preview | **"Save branding" button overlaps the "Quote PDF template" card** (sticky button covers content); form not prefilled with current business details; "Upload logo — Upload not implemented" (honest, but visible at go-live) |
| `trade-follow-ups.png` | `/(trade)/follow-ups` | Reminder toggles, channel, delay inputs | — |
| `trade-manual-lead.png` | `/(trade)/manual-lead` | Paste-message lead capture form | — |
| `customer-requests.png` | `/(customer)/requests` | Margaret's request: "Consumer unit replacement — AWAITING REVIEW" | Converted lead (quote already drafted) still shows "Awaiting review"; "Your electrician Assistant" capitalization odd |
| `customer-request-chat.png` | `/(customer)/messages?quoteRequestId=…` | AI assistant thread for her lead | **Stuck "Your electrician Assistant is typing…"** with no messages — the seeded AI triage thread belongs to Emma Whitfield's lead, which has no portal account, so no customer login can view it (seed gap); typing indicator should not show for an empty thread |
| `customer-calendar.png` | `/(customer)/calendar` | Upcoming appointment card | Appointment "9/9/2026 · 04:56 PM – 08:56 PM" — US format + implausible evening slot (UTC times rendered oddly); electrician shown as "your electrician" instead of business name |
| `customer-profile.png` | `/(customer)/profile` | Profile form | **Form is empty for a logged-in customer** — name/email/phone/address not prefilled from the account |

## Defect summary (fix-pass candidates)

**Critical**

1. ~~Web `/reviews` crashes~~ **FIXED 2026-09-01** (`toReview` mapper + defensive render; regression tests in `Reviews.test.tsx` / `reviews.test.ts`).
2. ~~Web invoice detail line totals multiplied twice~~ **FIXED 2026-09-01** (uses API per-line `total`, falls back to qty × unit price; tests in `invoices.test.ts`).
3. ~~Web calendar renders zero appointments; `/calendar/week` ignores the view param~~ **FIXED 2026-09-01** (`toAppointment` mapper; URL-driven Month/Week/Day views; tests in `Calendar.test.tsx` / `appointments.test.ts`).
4. Mobile trade login never navigates after successful sign-in (`LoginScreen.handleSubmit` does nothing on `ok`).
5. Mobile web build can't authenticate against the local/staging API from a browser: CORS allows only the web origin, and the failure surfaces as "Invalid email or password."

**High**

6. Mobile quote editor line-item row clipped/overlapped by totals (`trade-quote-review-ai.png`).
7. Mobile branding: Save button overlaps PDF-template card; form not prefilled.
8. Customer profile empty despite login; customer chat shows permanent "typing…" on empty threads.
9. Mobile customers screen is an un-wired placeholder ("CRM coming soon") while data exists.
10. Lead titles fall back to "New request" and show raw enum urgency (`this_week`).

**Medium / cosmetic**

11. ~~"VAT (0.2%)" label on web invoice detail~~ **FIXED 2026-09-01** (rate ×100 → "VAT (20%)").
12. ~~Jobs show £0 value on web board/detail~~ **FIXED 2026-09-01** (value derived from linked quote total).
13. US date formats (9/1/2026) across mobile; inconsistent money formatting both apps (£976.8, £1,120.8). **Web invoices/jobs pages fixed 2026-09-01** (shared `formatGBP` 2dp helper); mobile + web quotes pages still open.
14. Web dashboard revenue Y-axis repeats £0k; Service Mix buckets by first word of description.
15. Sticky CTA buttons overlap content on mobile quote-intake; week calendar columns cramped at 402px.
16. Settings → Services has no empty state; ~~TanStack Query devtools bubble visible in web captures~~ **FIXED 2026-09-01** (gated behind `import.meta.env.DEV`; verified absent from the production bundle — dev-server captures still show it by design).
17. Seed gap: the seeded AI triage thread is attached to a contact (Emma Whitfield) with no customer portal account, so the showcase thread is only visible to staff.
