# My Trade Portal V2 – Demo & milestone plan (iOS mock)

> This plan reflects the current interactive prototype in `services/pwa`. It is intentionally frontend-only for milestone 1; backend wiring is listed separately for Beta and MVP.

## Milestones

1. **Marketable prototype** (now) – interactive iOS demo that can be recorded and shown to electricians and their customers. No backend required.
2. **Beta test version** – real auth, tenant resolution, quote AI parsing, and push notifications with a small group of UK electricians.
3. **MVP go-live** – production backend, payments, calendar sync, App Store release, and onboarding for trade businesses.

---

## Milestone 1: marketable prototype demo flow

### 1. Entry / white-label discovery
- **Screen:** `01-entry.png`
- **Action:** A customer opens the app and enters the electrician’s 6-digit business code.
- **Value:** One app on the App Store, branded per business. No separate app build per electrician.
- **Backend touchpoint (Beta):** `GET /tenants/lookup?code=123456` resolves the tenant, primary colour, and logo.

### 2. Business selected
- **Screen:** `02-business-selected.png`
- **Action:** Code resolves to the branded business card. The customer can request a quote or log in; an electrician can register or log in from the same screen.
- **Value:** The app is the portal to the business, not a generic trades directory.
- **Backend touchpoint (Beta):** Tenants seeded with a unique 6-digit code and business profile.

### 3. Trade login
- **Screen:** `03-trade-login.png`
- **Action:** Existing electrician logs in and lands straight on the dashboard.
- **Value:** Fast daily workflow; no onboarding detour for existing users.
- **Backend touchpoint (MVP):** JWT session cookie + tenant scoping + RLS enforcement.

### 4. Trade dashboard
- **Screen:** `04-dashboard.png`
- **Action:** See top leads, calendar today view, outstanding quotes, and one-tap shortcuts to Invoices and Revenue.
- **Value:** Everything that needs action is visible in one place.
- **Backend touchpoint (Beta):** Dashboard KPI endpoint aggregating leads, quotes, and jobs per tenant.

### 5. Invoices and revenue
- **Screens:** `04b-invoices.png`, `04c-analytics.png`
- **Action:** Tap Invoices to see sent/paid invoices and mark paid; tap Revenue to see paid revenue, outstanding, quoted, costs, and estimated profit.
- **Value:** The electrician can run a simple P&L from the app without exporting to spreadsheets.
- **Backend touchpoint (MVP):** Invoice lifecycle, material/labour cost tracking, and reporting endpoints.

### 6. Lead detail and AI quote
- **Screens:** `05-lead-detail.png`, `06-quote-intake.png`, `07-quote-edit.png`, `08-quote-edit-per-point.png`
- **Action:** Tap a lead to see customer, notes, and photos. Generate an AI quote, switch between Time & materials and Per point pricing, and edit line items on one screen.
- **Value:** Quote requests become structured quotes in seconds, with the tradesperson keeping full control of price and assumptions.
- **Backend touchpoint (Beta):** AI parser endpoint turns free-text request into JSON line items; no OCERP/BoQ engine for MVP.

### 7. Request more information
- **Screens:** `07b-request-info-chat.png`, `16-request-info-external.png`
- **Action:** For app-registered customers, request more info in in-app chat; for external contacts (SMS/WhatsApp), hand off to the native messaging app with a pre-filled request.
- **Value:** Every lead can be qualified without losing context.
- **Backend touchpoint (Beta):** In-app messaging stored per tenant; deep-link/SMS handoff tracked as lead activity.

### 8. Quotes, customers, and CRM
- **Screens:** `09-quotes.png`, `10-customers.png`, `10b-customer-detail.png`, `10c-customer-quotes.png`
- **Action:** Browse quotes, search customers, and view a customer’s full history with links to quotes, jobs, and invoices.
- **Value:** A lightweight CRM replaces post-it notes and spreadsheets.
- **Backend touchpoint (Beta):** Contacts, quotes, jobs, and invoices are tenant-scoped with RLS.

### 9. Calendar and job assignment
- **Screen:** `11-calendar.png`
- **Action:** Toggle Day/Week view, tap a job to see address, navigate with Apple Maps, call/message the customer, and assign the job to a team member.
- **Value:** Scheduling and dispatching in one place.
- **Backend touchpoint (MVP):** Calendar sync via EventKit/Apple Calendar; job assignment persisted in `jobs` table.

### 10. Settings and follow-ups
- **Screens:** `12-settings.png`, `13-follow-up-settings.png`, `14-branding.png`
- **Action:** Edit follow-up timing, channel (email/SMS), and branding (name, phone, address, colour) from the three-dot menu on the dashboard.
- **Value:** The business owner controls their white-label presence and customer communication cadence.
- **Backend touchpoint (MVP):** Settings persisted per tenant; scheduled follow-up worker sends reminders.

### 11. Manual lead entry from a direct message
- **Screen:** `15-ai-lead-entry.png`
- **Action:** A tradesperson creates a lead from a customer who contacted them outside the app (SMS, WhatsApp, social media), and the AI drafts a quote.
- **Value:** The app becomes the single inbox for every quote request, regardless of channel.
- **Backend touchpoint (Beta):** Share-extension/deep-link to accept forwarded text/images and create a draft lead.

### 12. Customer journey
- **Screens:** `17-customer-login.png`, `18-customer-quotes.png`, `19-customer-quote-detail.png`, `20-customer-quote-accepted.png`, `21-customer-book-date.png`, `22-customer-profile.png`
- **Action:** Customer logs in, sees their quote, views full line items, accepts/rejects, books a date, and edits their profile.
- **Value:** Customers self-serve the most time-consuming parts of the sales process.
- **Backend touchpoint (Beta):** Customer accounts, quote status updates, booking slots, and profile updates.

---

## Backend work by milestone

### Beta
- Tenant lookup by 6-digit code and white-label config.
- JWT cookie auth with `trade` and `customer` roles.
- Lead, quote, job, invoice, and contact CRUD with RLS.
- AI parser endpoint: convert free-text request + images into JSON line items with confidence score.
- Dashboard aggregation endpoints.
- In-app messaging for registered customers.
- Push notifications for new leads and accepted quotes.

### MVP
- Paddle/stripe payment collection and invoice paid status.
- Apple Calendar / EventKit integration for job sync.
- SMS/WhatsApp deep-link handoff and share-extension for quote drafts.
- Follow-up scheduler worker (email + SMS).
- App Store build, code signing, and release pipeline.
- Production hardened secrets, RLS review, and onboarding wizard for new trade sign-ups.

---

## Suggested demo video script

1. **Open the app.** Show the single entry screen and explain one app, many electricians.
2. **Enter a 6-digit code.** The branded business appears instantly.
3. **Log in as the electrician.** Dashboard shows leads, calendar, and shortcuts.
4. **Tap a lead, generate an AI quote.** Switch pricing model and edit line items in one screen.
5. **Request more info.** Show the in-app chat and SMS/WhatsApp fallback.
6. **Send the quote.** Switch to the customer view and accept it.
7. **Book a date.** Customer picks a day and time slot.
8. **Back in the trade app.** Calendar now shows the booking; tap it to navigate or reassign.
9. **Create and mark invoices paid.** Show the revenue and profit view.
10. **Close with the settings screen.** Reinforce white-label branding and automatic follow-ups.

---

## Screenshot inventory

All screenshots are generated by `services/pwa/scripts/capture-demo-screenshots.js` and saved to `services/pwa/demo-screenshots/`.

| # | File | What it shows |
|---|------|---------------|
| 1 | `01-entry.png` | Entry / business code lookup |
| 2 | `02-business-selected.png` | Branded business card selected |
| 3 | `03-trade-login.png` | Existing electrician login |
| 4 | `04-dashboard.png` | Trade dashboard with leads, calendar, shortcuts |
| 5 | `04b-invoices.png` | Invoice list with mark-paid / send reminder |
| 6 | `04c-analytics.png` | Revenue & costs / P&L |
| 7 | `05-lead-detail.png` | Lead detail with customer, notes, photos |
| 8 | `06-quote-intake.png` | AI quote intake form |
| 9 | `07-quote-edit.png` | Line-by-line quote edit (Time & materials) |
| 10 | `08-quote-edit-per-point.png` | Per-point pricing toggle |
| 11 | `07b-request-info-chat.png` | In-app request for more info |
| 12 | `09-quotes.png` | Quotes list |
| 13 | `10-customers.png` | Customer directory |
| 14 | `10b-customer-detail.png` | Customer profile with links |
| 15 | `10c-customer-quotes.png` | Customer quote history |
| 16 | `11-calendar.png` | Day/week calendar with bookings |
| 17 | `12-settings.png` | Settings via three-dot menu |
| 18 | `13-follow-up-settings.png` | Automatic follow-up config |
| 19 | `14-branding.png` | White-label branding & pricing |
| 20 | `15-ai-lead-entry.png` | Manual lead entry from external contact |
| 21 | `16-request-info-external.png` | SMS/WhatsApp handoff for unregistered customers |
| 22 | `17-customer-login.png` | Customer login |
| 23 | `18-customer-quotes.png` | Customer quote list |
| 24 | `19-customer-quote-detail.png` | Full quote view for customer |
| 25 | `20-customer-quote-accepted.png` | Quote accepted |
| 26 | `21-customer-book-date.png` | Book a date |
| 27 | `22-customer-profile.png` | Editable customer profile |
