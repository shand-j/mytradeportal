# PRD 2 — Customer Quote Capture (C1–C10)

> UI-only scope for the Milestone 1 interactive mock. No backend wiring, no persistence beyond local Expo/React Native state. All AI and verification states are mocked.

## 1. Goal

Let a homeowner or landlord request a quote from a white-label electrical business in under 3 minutes, while capturing enough structured data for a realistic AI draft quote. The mock must demonstrate the white-label entry, dynamic branched questionnaires, emergency triage, and honest expectation-setting.

## 2. Principles

1. **White-label first.** The same app binary becomes the branded customer portal for any business signed up in PRD 1. Logo, primary colour, and enabled categories are resolved from the business mock config.
2. **Triage before quote.** Red-flag symptoms (burning smell, shocks, water on electrics) bypass the form and route to an emergency callback screen.
3. **Structured first, media second, free text last.** Every job branch has a targeted questionnaire; free text is only a fallback.
4. **Property age is the master variable.** Capture it early and show how it influences the quote.
5. **AI drafts, humans send.** The confirmation screen never promises an instant quote; it says the business will review and send.
6. **Save and resume.** Abandoned forms can be resumed by email (mock only).

## 3. Entry points

| Route | Source | Behaviour |
|---|---|---|
| QR code | Printed card / van sticker / flyer | Deep link `mtp://quote?code={6-digit}` → C1 with business pre-loaded |
| Universal link | Website “Get a quote” | `https://mytradeportal.app/quote?code={6-digit}` → C1 |
| Web form | Embedded iframe | Same flow rendered in web; out of scope for iOS mock |
| App Store organic | Open app, enter code | Entry screen → C1 after code lookup |

## 4. Screen specifications

### C1 — Entry & Postcode

- **Headline:** “Get a quote from {Business Name}”
- **Logo + primary colour** applied from business config.
- **Fields:**
  | Field | Type | Validation | Notes |
  |---|---|---|---|
  | Postcode | text | UK postcode regex | Pre-filled if deep link or EPC lookup |
- **Instant checks (mock):**
  - Inside service area → continue to C2.
  - Outside service area → polite decline + “Leave your details for a referral”.
  - EPC found → “We’ve found your property details — just confirm a few things”.
- **CTAs:** Primary “Continue”, secondary “Already have a quote? Sign in”.
- **Analytics mock:** `quote_request_started`.

### C2 — Contact

- **Fields:**
  | Field | Type | Validation | Notes |
  |---|---|---|---|
  | Name | text | required | |
  | Mobile | tel | UK mobile | Used for SMS/WhatsApp updates |
  | Email | email | required | Quote PDF delivery |
  | Preferred contact | select | required | `phone`, `sms`, `whatsapp`, `email` |
  | Best time to call | multi-checkbox | optional | morning/afternoon/evening (only if phone) |
- **CTAs:** “Continue”.
- **Mock data:** pre-fill `Jane Homeowner`, `jane@example.com`, `07700 123 456` for demo.

### C3 — Property Profile

- **Fields:**
  | Field | Type | Validation | Notes |
  |---|---|---|---|
  | Property type | card select | required | detached, semi, terrace, bungalow, flat |
  | Property age | banded select | required | pre_1930, 1930-1960, 1960-1980, 1980-2000, post_2000, not_sure |
  | Bedrooms / reception | steppers | required | point-count estimation |
  | Floors | stepper | required | 1–5 |
  | Tenure | select | required | owner, tenant, landlord, housing_assoc |
  | Flat access | conditional | — | lift yes/no if flat |
  | Van parking | yes/no | required | labour factor |
  | Consumer unit photo | upload | skippable with warning | guided overlay |
  | Fuse board style | visual select | optional | modern RCBO / RCD split-load / rewireable / not sure |
  | Known issues | multi-checkbox | optional | tripping, flickering, smell, buzzing, dead sockets |
- **UX:** Show a “Why we need this” tooltip on property age.
- **Mock data:** pre-select `semi`, `1960-1980`, 3 beds, 2 receptions, 2 floors, owner, parking yes.

### C4 — Job Category Picker

- **Tiles** limited to the categories the business enabled in A8 (PRD 1). Common default: EV charger, Consumer unit, EICR, Additional sockets, Outdoor power, Fault finding, Emergency callout, Other.
- Each tile shows an icon and label.
- **CTA:** “Continue” (disabled until one selected).
- **Mock data:** pre-select `Consumer unit upgrade`.

### C5 — Dynamic Job Questionnaire

Common pattern for every branch:
- Header shows the selected category icon + title.
- Branch-specific fields (see below).
- Optional “Anything else we should know?” free text at the end.
- AI confidence meter mock updates as the user answers.

For the demo, implement at least these branches:

#### C5.2 — Consumer Unit Upgrade
| Field | Type | Notes |
|---|---|---|
| Number of circuits | count-assist | “Count the switches in your photo” |
| Reason for upgrade | select | old fuse wire, no RCD, adding circuits, survey recommendation, other |
| Known faults | checkbox | feeds triage |
| Property occupied during work? | yes/no | power-down messaging |

#### C5.1 — EV Charger
| Field | Type | Notes |
|---|---|---|
| Vehicle make/model | autocomplete mock | |
| Charger preference | select | no preference / brand chips |
| Parking location | select | driveway, garage, street — street routes to advice screen |
| Distance from consumer unit | banded | `<5m`, `5–10m`, `10–20m`, `>20m` |
| Mounting surface | select | brick, render, timber, garage interior |
| Main fuse rating | photo + select | 60/80/100A / not sure; 60A → DNO upgrade flag |
| Wi-Fi at location? | yes/no | |
| Three-phase supply? | yes/no/not sure | |

#### C5.4 — EICR
| Field | Type | Notes |
|---|---|---|
| Who is asking? | select | landlord, homeowner, buyer, seller |
| Last EICR date | date | optional |
| Property vacant / tenanted | select | access planning |
| Number of circuits | count / not sure | price driver |
| Remedial works in quote? | yes/no/price separately | |

#### C5.9 — Other
Free text (min 30 chars prompt) + required photos. Always `requires_human_review = true`.

### C6 — Media Capture (consolidated)

- **Required:** consumer unit photo (if skipped in C3, re-prompted).
- **Branch-required:** photos defined in the C5 branch.
- **Optional:** video walkthrough (≤60s) and document upload (previous EICR, plans).
- **UX:** camera placeholder with guide overlay and example “good photo” thumbnails.
- **Mock:** tapping upload immediately shows a fixed thumbnail.

### C7 — Timing, Urgency & Triage

- **Fields:**
  | Field | Type | Notes |
  |---|---|---|
  | When needed? | select | emergency_today, this_week, this_month, flexible, just_researching |
  | Preferred dates | multi-pick | optional; show 14-day calendar |

- **Triage routing rules:**
  | Trigger | Route |
  |---|---|
  | Burning smell / smoke / scorch / shocks / water on electrics | Emergency screen: tap-to-call + safety guidance |
  | `emergency_today` selected | Emergency screen with SLA disclosure |
  | Repeated tripping / partial power loss | Priority callback + AI draft flagged `safety_review` |
  | Everything else | Standard AI quote pipeline |

- **Emergency screen:** red header, “Call {Business Name} now”, tap-to-call button, “If you can do so safely, switch off at the main switch.”, SMS/WhatsApp fallback button. No quote form.

### C8 — Budget & Context

- **Fields:**
  | Field | Type | Notes |
  |---|---|---|
  | Budget band | select | optional; under_250, 250_500, 500_1k, 1k_2.5k, 2.5k_plus, no_idea |
  | How did you hear? | select | optional; attribution |
  | Insurance claim? | yes/no | optional; different quote format |

### C9 — Consents & Submit

- **Fields:**
  | Field | Type | Notes |
  |---|---|---|
  | T&Cs / privacy acknowledgement | checkbox | required, versioned mock |
  | Contact permission | checkbox | required; service comms only |
  | Marketing opt-in | checkbox | optional, unticked by default, granular |
  | Landlord permission | checkbox | conditional if tenant |
- **CTA:** “Submit quote request”.
- **Submit mock:** creates a local quote request, navigates to C10.

### C10 — Confirmation

- **Headline:** “{Business Name} has your request”
- **Subcopy:** “{Business} will review your details and send your quote — usually within {X hours}.” X = business setting (mock default 24).
- **Summary card:** postcode, category, urgency, photos received count.
- **High confidence state:** “Good news — your quote is already being prepared.”
- **CTAs:** “Done” → returns to entry; “Create an account to track this quote” → customer registration.
- **Analytics mock:** `quote_request_submitted`.

## 5. Navigation & state

- The flow is a linear stepper inside `CustomerQuoteRequestFlow`.
- State is held in a local `useState` object; no persistence in Milestone 1.
- Branching is driven by the selected category and triage rules.
- The business config (logo, colour, categories) is read from the business Zustand store.

## 6. Mock data defaults

For the demo video and screenshots, use the demo business:
- Business name: “Demo Electrical Ltd”
- Primary colour: `#2563EB`
- Enabled categories: Consumer unit, EV charger, EICR, Additional sockets, Outdoor power, Fault finding, Other
- Default quote SLA: 24 hours
- Service area: 15-mile radius around `SK8 3NJ`
- Demo customer: `Jane Homeowner`, `jane@example.com`, `07700 123 456`
- Demo job: Consumer unit upgrade at `SK8 3NJ`, semi-detached, 1960–1980, 3 bed, parking yes

## 7. UI components needed

- `CustomerQuoteRequestFlow` (stepper shell)
- `PostcodeInput` with inline validation
- `CategoryTileGrid`
- `QuestionnaireStep` (branch-specific sub-screens)
- `MediaUploadMock` with guide overlay
- `UrgencySelector`
- `EmergencyCallbackScreen`
- `ConsentCheckbox` with explicit unticked-by-default marketing opt-in
- `ConfirmationSummaryCard`

## 8. Success criteria

- A new customer can complete the demo consumer-unit flow in under 2 minutes.
- Emergency triage visibly interrupts the quote flow and routes to a call-back screen.
- The flow is clearly white-labelled by the demo business (logo + colour).
- The confirmation screen sets honest expectations and never promises an instant AI-sent quote.

## 9. Out of scope for Milestone 1

- Real postcode / EPC lookup APIs.
- Real camera capture or HEIC processing (use placeholder thumbnails).
- Real SMS/WhatsApp sending or push notifications.
- Backend quote request persistence.
- Real AI model inference.
- Save-and-resume email backend.
