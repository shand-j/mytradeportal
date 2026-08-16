# PRD 4 — Customer Portal

> UI-only scope for the Milestone 1 interactive mock. No backend wiring, no persistence beyond local Expo/React Native state. All data is mocked.

## 1. Goal

Let a homeowner create an account, view quotes, accept or reject them, book a date, message the electrician, and manage their profile — all inside the same white-label app that the electrician uses. The customer experience must feel like a branded electrician app, not a generic marketplace.

## 2. Principles

1. **Account creation is required for tracking.** A customer can request a quote without an account, but to view quotes, accept/reject, and book dates they must create an account. No read-only magic-link dashboard in the MVP.
2. **White-label by business.** Logo, colour, and business name are resolved from the business config.
3. **Quotes are transparent.** Line items, assumptions, validity, and total are visible before the customer accepts.
4. **Booking is one-tap after acceptance.** Once a quote is accepted, the customer picks a date and time slot.
5. **Self-service profile.** The customer can edit their name, phone, email, addresses, and communication preferences.

## 3. Entry points

| Route | Source | Behaviour |
|---|---|---|
| Open app, enter code | Guest | Business landing page → request quote or login |
| Deep link from quote email | `mtp://quote/{id}` | Opens quote detail directly if logged in, or prompts login |
| Universal link | `https://mytradeportal.app/quote/{id}` | Same as above |
| App Store organic | Open app | Shows business landing page or entry screen |

## 4. Navigation model

| Bottom tab | Notes |
|---|---|
| **Quotes** | List of quote requests and received quotes |
| **Calendar** | Upcoming appointments (booked dates) |
| **Messages** | In-app chat with the business |
| **Profile** | Account details, preferences, logout |

Icons: `Ionicons` document-text, calendar, chatbubble, person.

## 5. Screen specifications

### 5.1 Customer landing / login

- When the customer enters a 6-digit business code, show the branded landing page:
  - Business logo/name
  - “Request a quote” primary CTA
  - “Customer login” secondary CTA
- No electrician options on this page.
- Login screen: email + password, back button top-left, demo credentials pre-filled.
- Customer registration screen: name, phone, email, password, address, preferred contact method.

### 5.2 Quotes list

- **Top bar:** “My quotes” + business name.
- **Cards:**
  - Quote request: title, submitted date, status “Awaiting review”.
  - Quote received: title, total, validity, status “Open”.
- **Empty state:** CTA to request a new quote.
- **CTA:** “Request a new quote” → opens the customer quote capture flow (PRD 2).

### 5.3 Quote detail (full quote view)

- **Header:** Quote title, back button.
- **Summary card:** business name, postcode, validity date.
- **Line items:** description + total for each line.
- **Assumptions:** bulleted list of assumptions.
- **Totals:** subtotal, VAT, total.
- **Status badge:** Open / Accepted / Rejected / Expired.
- **Actions:**
  - Accept quote → routes to booking.
  - Reject quote → shows a short rejection reason (optional) and updates status.
  - Request changes → opens Messages with the quote context.

### 5.4 Accept quote + book a date

- After accepting, show a success card: “Quote accepted — choose a date.”
- **Pick a day:** 7-day horizontal strip, day letter + date.
- **Pick a time:** chips for morning/afternoon slots, e.g. 08:00–10:00, 10:00–12:00, etc.
- **CTA:** “Confirm booking”.
- **Confirmation:** shows the booked date/time and routes to Calendar.

### 5.5 Calendar (customer)

- **Top bar:** “Appointments”.
- **List:** upcoming booked dates, past appointments.
- Each card: date, time, job title, business name, address.
- **Actions:** Add to Apple Calendar (placeholder), navigate to address, message business.

### 5.6 Messages

- **Top bar:** “Messages” with business name.
- **Chat UI:** message bubbles, date separators.
- **Input:** text + send button.
- **Mock messages:** pre-load a short thread about the consumer unit upgrade.
- **Context:** when opening from a quote detail, pre-fill the composer with the quote reference.

### 5.7 Profile

- **Top bar:** “Profile”, back button.
- **Editable fields:** name, phone, email, preferred contact method (phone/sms/whatsapp/email), addresses.
- **Security:** change password placeholder.
- **Notifications:** toggle for quote updates and appointment reminders.
- **CTA:** “Save changes” (mock saves locally), “Log out”.

## 6. Navigation & state

- Customer routes live under `app/(customer)/` in the Expo Router migration.
- Auth state is read from the Zustand auth store; customer role is `customer`.
- Business theme is read from the Zustand business store.
- Quote/job data is read from existing `src/data/mock*.ts` files.

## 7. Mock data defaults

- Demo customer: `Jane Homeowner`, `jane@example.com`, `07700 123 456`, postcode `SK8 3NJ`.
- Demo business: “Demo Electrical Ltd”, primary colour `#2563EB`.
- Demo quote: Consumer unit upgrade, total £894.00, valid 30 days, status Open.
- Demo booking: none initially; created after the customer accepts and books in the demo flow.
- Demo chat: 2–3 messages from the business about the quote.

## 8. UI components needed

- `CustomerTabBar` (Quotes / Calendar / Messages / Profile)
- `QuoteStatusBadge`
- `QuoteLineSummary` (read-only line items)
- `BookDateStrip` (day/time selection)
- `CustomerAppointmentCard`
- `ChatThread` / `ChatComposer`
- `CustomerProfileForm`

## 9. Success criteria

- A customer can log in, view a full quote, accept it, and book a date in under 1 minute.
- The customer profile is editable.
- Messages are reachable from the bottom nav and from quote detail.
- The portal is visually white-labelled by the demo business.

## 10. Out of scope for Milestone 1

- Real account creation backend.
- Real push/email notifications.
- Real payment capture at acceptance.
- Real calendar integration.
- Service history / certificate vault (can be a placeholder card in Profile).
