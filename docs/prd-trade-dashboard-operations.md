# PRD 3 — Trade Dashboard & Operations

> UI-only scope for the Milestone 1 interactive mock. No backend wiring, no persistence beyond local Expo/React Native state. All data is mocked.

## 1. Goal

Give the electrician (or business owner) a mobile back-office that surfaces the most important actions first: quote leads, calendar, customer CRM, and quick quote editing. The dashboard must be a one-tap path to action, not a static report.

## 2. Principles

1. **Default to action.** The dashboard opens with the most valuable open leads and today’s calendar so the tradesperson can act in seconds.
2. **Leads vs. quotes are distinct.** A lead is an unreviewed opportunity; a quote is a drafted or sent proposal. The handoff from lead → quote is explicit.
3. **AI drafts, humans send.** Every AI-generated quote lands in a review screen where the electrician can edit lines, switch pricing models, and approve.
4. **Calendar is a work board.** Day view shows the schedule; week view shows the full 7-day grid. Tapping a job opens job details with navigate, call, message, and assign actions.
5. **Settings are reachable, not in the way.** Settings live in the top-right three-dot menu, not in the bottom navigation.

## 3. Navigation model

| Bottom tab | Primary role | Notes |
|---|---|---|
| **Dashboard** | Trade | Quote leads, calendar today view, attention items |
| **Quotes** | Trade | All leads/quotes list |
| **Customers** | Trade | CRM directory |
| **Calendar** | Trade | Day + week schedule |

Settings is accessed via the top-right three-dot menu on Dashboard and Calendar. Logout is inside Settings.

Icons: use `Ionicons` (home, document-text, people, calendar). No emoji.

## 4. Screen specifications

### 4.1 Dashboard

- **Top bar:** Business name, greeting, three-dot menu → Settings/Logout.
- **Summary cards (2):**
  - Active leads count (blue)
  - Outstanding quotes value (amber)
- **Top leads section:**
  - Title: “Top leads” (max 3)
  - Each lead card: title, source, postcode, urgency, estimate, badge.
  - Tapping a lead card navigates directly to the **lead detail** for that exact lead (one click to action).
  - Secondary actions: “View all” → Quotes tab, “+ New lead” → manual AI lead entry.
- **Calendar today section:**
  - Today’s date + booking count.
  - Horizontal strip of the next 7 days with day letter + date; tap swaps the day.
  - List of today’s bookings (time, title, customer, postcode).
  - “View full” → Calendar tab.
- **Removed:** The old Dashboard “Quotes” and “Customers” buttons are removed; navigation is via the bottom tab bar.

### 4.2 Quotes (Leads) list

- **Top bar:** Title “Quotes / Leads”, filter chips: All / New / Flagged / Sent / Accepted.
- **List:** same lead card as Dashboard, sorted by urgency.
- **FAB / top action:** “+ New lead” (manual AI entry).
- **Empty state:** If there are no leads, show a friendly empty card and a CTA to share the QR code / link.
- **Default state:** When there are no leads, the default tab should still be Quotes (user explicitly asked: “Quotes when no leads”).

### 4.3 Lead detail

- **Header:** Lead title, back button.
- **Cards:**
  - Lead summary (source, postcode, urgency, received date, badge).
  - Customer card (name, phone, email).
  - Notes card.
  - Photos / videos thumbnails.
- **Actions:**
  - **Generate AI quote** → Quote intake screen (if enough info) or quote edit screen.
  - **Request more info** → If the lead came via the app, open the in-app chat to ask the customer for details. If the lead came from an unregistered external channel (SMS/WhatsApp), open the device’s SMS or WhatsApp composer via deep link (`sms:` / `whatsapp:`).
  - **Mark as dead** → returns to list with the lead hidden.

### 4.4 Quote intake (AI scoping)

- Triggered from lead detail or manual lead entry.
- Collects: property type, bedrooms, consumer unit location, access notes, parking, photos.
- Pre-fills data from the lead where available.
- CTA: “Generate AI quote” → animates a progress bar, then routes to Quote edit.

### 4.5 Quote edit (single-screen line-by-line)

- **Header:** “Review AI quote” + back.
- **Summary card:** job title, customer, postcode, AI confidence badge.
- **Pricing toggle:**
  - **Time & materials:** labour cost + materials cost + call-out. Total = sum of line items.
  - **Per point:** fixed price per task. Example: “Install double socket £100, qty 4, total £400”.
  - Switching the toggle must immediately update the displayed line items and total (mock two line-item sets).
- **Line items:** editable rows inside a single screen:
  - Description (full width)
  - Qty / Unit / Price (£) row that wraps on small screens and stays inside the card.
  - Delete line icon.
- **Footer:** Subtotal, VAT, Total, “Approve & send” / “Save changes”, “Request more info”.
- **UX:** compact, no nested scrolling; use a ScrollView for the whole screen.

### 4.6 Calendar

- **Top bar:** Title “Calendar”, view toggle Day / Week, three-dot menu.
- **Day view:**
  - 7-day horizontal strip.
  - Selected day highlighted.
  - List of bookings with time, title, customer, postcode.
  - Tap booking → Job detail.
- **Week view:**
  - Full 7-day grid (one row of 7 equal columns, or 7 day cards in a horizontal scroll if screen height is tight).
  - Each cell shows the day name, date, and stacked bookings with start time.
  - Tap any booking → Job detail.
- **Job detail from calendar:**
  - Customer, address, date/time, status.
  - Actions: Navigate to address (Apple Maps / Google Maps deep link), Call, Message, Assign to engineer, Mark completed.
  - “Create invoice” (mock) once job is completed.

### 4.7 Customers (CRM)

- **Top bar:** Title “Customers”.
- **List:** customer cards with name, postcode, lifetime value, quote/job counts, last contact.
- **Search bar:** filter by name or postcode (client-side filter on mock data).
- **Customer detail:**
  - Contact info, address, notes.
  - Tabs/links: Quotes, Jobs, Invoices (mock lists).
  - “Add note” / “Edit details” (mock edits allowed in Milestone 1).

### 4.8 Revenue / P&L (basic)

- **Top bar:** Title “Revenue”.
- **Cards:**
  - This month revenue (mock sum of paid invoices)
  - This month profit (revenue - material/labour costs from jobs)
  - Outstanding invoices value
- **Mini chart:** simple line chart of revenue by week (mock 8 data points). Use a lightweight SVG or Recharts if already available; otherwise a simple bar chart is fine for the mock.
- **Out of scope:** Real accounting integrations, export.

### 4.9 Settings

- **Top bar:** Title “Settings”, back button.
- **Sections:**
  - Business profile (name, contact, service area)
  - Follow-up settings (quote reminders, invoice reminders, channel)
  - Branding (logo, colour, quote PDF template)
  - Team (engineers list, assignment)
  - Integrations (placeholder cards)
  - Log out
- **Logout:** clears auth state and returns to the entry screen.

## 5. Navigation & state

- Trade routes live under `app/(trade)/` in the Expo Router migration.
- Auth state is read from the Zustand auth store.
- Business theme is read from the Zustand business store.
- Lead/quote/job/customer data is read from existing `src/data/mock*.ts` files.

## 6. Mock data defaults

Re-use the existing mocks plus a few demo leads:
- Lead 1: “Consumer unit upgrade” — app source, urgency `this_week`, estimate £745, badge New.
- Lead 2: “EV charger install” — WhatsApp source, urgency `this_month`, estimate £450, badge Flagged.
- Lead 3: “EICR for rental” — manual source, urgency `flexible`, estimate £280, badge New.
- Jobs: 5–7 bookings across the next 7 days, status confirmed.
- Customers: 6–8 customers from `mockCustomers.ts`.
- Invoices: 3–5 invoices with paid/sent statuses.

## 7. UI components needed

- `TradeTabBar` (Dashboard / Quotes / Customers / Calendar)
- `DashboardLeadCard` (one-tap to lead detail)
- `DayStrip` (reused on Dashboard and Calendar)
- `WeekGrid` (7-day calendar grid)
- `JobCard` / `JobDetailActions`
- `QuoteLineItemRow` (compact, responsive)
- `PricingModelToggle`
- `CustomerCard` / `CustomerDetailTabs`
- `RevenueChart` (simple SVG or bar)
- `SettingsMenu` / `TopBarMenu` (three-dot)

## 8. Success criteria

- A tradesperson can open the dashboard, tap a lead, generate a quote, switch pricing models, and approve — all within 30 seconds of simulated interaction.
- Calendar day and week views are both usable at 390×844.
- Customer detail links to quotes, jobs, and invoices.
- Navigation is consistent: back button is always top-left, bottom tab has exactly 4 items with icons.
- Edge padding is fixed: no content touches the screen edges.

## 9. Out of scope for Milestone 1

- Real job dispatch, GPS tracking, or route optimisation.
- Real calendar sync (Apple/Google Calendar).
- Real phone/SMS/WhatsApp deep links (mock the composer opening where possible).
- Real payments or invoice generation.
- Real revenue analytics (P&L is mocked).
