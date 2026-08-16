# PRD 1 — Business Onboarding (A1–A14)

> UI-only scope for the Milestone 1 interactive mock. No backend wiring, no persistence beyond local Expo/React Native state. All verification states are mocked.

## 1. Goal

Let an electrical business owner sign up, prove trust signals, and launch a white-label customer quote experience in under 8 minutes. The mock must feel like a real product: structured forms, verification badges, a visible launch gate, and a preview of the customer-facing quote form.

## 2. Principles

1. **Progressive profiling.** A1–A6 + A8 are required to launch. A7, A9–A13 are deferred to a post-launch checklist that persists on the dashboard until complete.
2. **Verify, don’t just collect.** Every credential has a badge: `verified`, `pending`, `manual_review`, or `self_declared`.
3. **No dead ends.** If a verification is missing (e.g. no CPS yet), the owner can still onboard as `provisional` and see exactly what is locked until they complete it.
4. **One binary, runtime brandable.** The same app signs up many businesses; branding and categories are applied locally from mock data.

## 3. Entry points

| Route | Source | Behaviour |
|---|---|---|
| Register my business | Entry screen | Starts onboarding at A1 |
| Onboarding resume | Dashboard checklist | Jumps to the first incomplete launch-gate step |
| Deep link | `mytradeportal://onboard?business=...` | Skips A1 if a partial profile exists (mock only) |

## 4. Screen specifications

### A1 — Welcome / Value Proposition

- **Headline:** “Run your electrical business from your phone.”
- **Sub-bullets:**
  - Get leads from QR codes, WhatsApp, and your website.
  - AI drafts quotes; you review and send in seconds.
  - Certificates, invoices, and accounts in one place.
- **Progress preview:** 6-step launch bar (Account → Business → Compliance → Services → Launch).
- **Primary CTA:** “Create my account” → A2.
- **Secondary CTA:** “I already have an account” → trade login.
- **Analytics mock event:** `onboarding_started`.

### A2 — Account Creation

| Field | Type | Validation | Notes |
|---|---|---|---|
| Full name | text | 2–80 chars | Split into first/last display only |
| Work email | email | RFC-like regex; block `test@` | Used as login |
| Mobile | tel | UK mobile format | `07700 123 456` or `+447700...` |
| Password | password | ≥10 chars, show strength bar | Mock strength only |
| Role | select | `owner`, `office_manager`, `engineer` | Default `owner`; non-owner sees hint about inviting owner later |
| Terms & privacy | checkbox | required | Unticked by default |

- **CTAs:** Primary “Continue”, secondary “Already have an account? Log in”.
- **Error states:** inline per field, red border + caption.
- **Mock data:** pre-fill `owner@demo.trade` for demo convenience with a banner “Demo pre-fill — tap to clear”.

### A3 — Business Identity

| Field | Type | Validation | Notes |
|---|---|---|---|
| Trading name | text | 2–100 chars | Shown on customer quotes |
| Business structure | select | `sole_trader`, `ltd`, `llp`, `partnership` | Drives CH field visibility |
| Legal entity name | text | conditional | Required if not sole trader |
| Companies House number | text | conditional; 8-char alphanumeric | Mock verify button → `verified` after 1.2s |
| Year established | number | 1900–current year | Trust badge |
| Website / Facebook | url | optional | Used to suggest logo later |

- **Verification badge:** `CH verified` chip appears after mock verification.
- **Branching:** `sole_trader` hides CH fields; shows MTD hint: “From April 2026, sole traders over £50k must use MTD-compatible software — we sync with Xero/QuickBooks/FreeAgent.”

### A4 — Address & Service Area *(new screen)*

| Field | Type | Validation | Notes |
|---|---|---|---|
| Trading address | address lookup | required | Postcode → address picker; mock with 3 fixed addresses |
| Registered office | address | conditional | Pre-filled from CH if verified; editable |
| Service area mode | radio | `radius` / `postcode_list` | |
| Radius | slider | 5–50 miles | Visible if mode = radius |
| Postcode sectors | multi-input | UK sector pattern | Visible if mode = postcode_list; e.g. `M1`, `SK8` |
| Nations served | multi-checkbox | England / Wales / Scotland / NI | Drives compliance copy later |

- **UX:** Show a static map pin card below the address; no live map integration in mock.
- **Mock data:** default to `SK8 3NJ` and radius `15 miles`.

### A5 — Tax & VAT *(new screen)*

| Field | Type | Validation | Notes |
|---|---|---|---|
| VAT registered? | toggle | required | |
| VAT number | text | conditional; 9 digits | Mock verify button → `verified` |
| VAT scheme | select | `standard`, `flat_rate` | Visible if VAT registered |
| Default VAT rate | derived | 20% | Read-only info row |

- **Info card:** “Some energy-saving materials may qualify for reduced VAT — you’ll confirm per quote.”

### A6 — Compliance & Credentials

| Field | Type | Validation | Notes |
|---|---|---|---|
| Competent Person Scheme | select | required if England/Wales | `niceic`, `napit`, `elecsa`, `stroma`, `besca`, `select_scotland`, `none_yet` |
| CPS membership number | text | conditional | Mock verify → `pending` then `verified` |
| 18th Edition held? | toggle + upload | required | Toggle + file upload mock |
| Inspection & testing qual | toggle + upload | conditional | Required if offering EICRs |
| Public liability insurer | text | required | |
| PL policy number | text | required | |
| PL cover level | select | £1m / £2m / £5m / £10m | |
| PL expiry date | date | must be future | Renewal hook shown |
| PL policy upload | file mock | required | |
| Professional indemnity | optional group | | Collapsed by default |
| ECS/JIB grading | text | optional | |
| DBS check | select | optional | `basic`, `enhanced`, `none` |

- **Badge summary:** live row of badges at the top of the screen updating as fields are filled.
- **`none_yet` branch:** show warning card: “You can continue as provisional, but customer-facing quotes and AI auto-send are locked until you add a CPS.”

### A7 — Team & Capacity *(defer, new screen)*

| Field | Type | Notes |
|---|---|---|
| Number of engineers | stepper | 1–200 |
| Number of vans | stepper | 0–200 |
| Team invites | repeatable row | Name, email, mobile, role |
| Engineer grades | per invite select | `qualified`, `apprentice`, `mate` |

- **CTA:** “Skip for now” → adds to post-launch checklist.

### A8 — Services Offered

- **Card grid** of categories, each with an icon:
  - EV charger
  - Consumer unit
  - Full rewire
  - Partial rewire
  - EICR
  - Additional sockets / lights
  - Outdoor / garden power
  - Fault finding
  - Smart home / lighting design
  - Data networking
  - Emergency callout
  - Other
- **Per-category follow-up chips:**
  - EICR → “Landlord compliance work?”
  - EV → “OZEV grant handling?”
  - Emergency → “24/7 or hours-limited?”
- **Validation:** at least one category selected.
- **CTA:** “Continue”; selected categories drive the customer quote form preview at A14.

### A9 — Pricing Setup *(defer, new screen)*

- **One section per enabled category** with sensible defaults.
- **Fields:**
  - Labour model: `day_rate`, `half_day`, `hourly`, `per_point`, `fixed_per_job`
  - Standard hourly rate
  - Day rate
  - Call-out fee
  - Minimum charge
  - Materials markup %
  - Emergency multiplier
  - Preferred wholesalers (multi-select chips)
  - Per-category base price
- **UX:** show a “Benchmark band” warning mock if price >2× or <0.5× regional median.
- **CTA:** “Skip for now”.

### A10 — Quote Defaults & Terms *(defer, new screen)*

| Field | Type | Notes |
|---|---|---|
| Quote validity | number | Default 30 days |
| Deposit policy | select + % | `none`, `percent`, `fixed` |
| Payment terms | select | `on_completion`, `7_days`, `14_days`, `30_days` |
| Finance options | toggle | |
| T&Cs | template picker | 3 UK trades templates, mock only |
| Reference scheme | text | `Q-{YYYY}-{NNNN}` |
| Certifications issued | multi-select | EIC, MEIWC, EICR, Part P |

### A11 — Branding *(defer, new screen)*

- **Logo upload:** drag/drop or tap, preview thumbnail, mock “suggest from website” button.
- **Brand colour:** colour picker with contrast preview.
- **Email intro blurb:** rich-ish text (2-line input).
- **Quote PDF template:** 3 layout thumbnails, live preview card with sample quote.

### A12 — Payments & Integrations *(defer, new screen)*

- **Connect cards:** Stripe, GoCardless, Xero, QuickBooks, FreeAgent, Google Calendar, Outlook, WhatsApp Business.
- **State:** each card shows `connected` / `not connected` mock toggle.
- **Bank details fallback:** sort code + account number, modulus-check mock.
- **CTA:** “Skip for now”.

### A13 — Existing Data Import *(defer, new screen)*

- **Customer CSV import:** file picker + column mapper mock.
- **Active quotes import:** optional, marked legacy.
- **CTA:** “Start fresh” (most common).

### A14 — Review & Launch

- **Launch gate checklist:**
  - ✅ Account created
  - ✅ Business identity
  - ✅ Address & service area
  - ✅ Tax & VAT
  - ✅ Compliance & credentials
  - ✅ Services offered
  - ⏳ Team & capacity (defer)
  - ⏳ Pricing setup (defer)
  - ⏳ Quote defaults (defer)
  - ⏳ Branding (defer)
  - ⏳ Payments (defer)
  - ⏳ Data import (defer)
- **Compliance summary card:** CH verified, CPS verified/pending, insurance valid until date.
- **Preview:** “See your customer quote form” — renders the customer flow with the selected categories and colour.
- **Go-live CTA:** sets status to `active`, navigates to trade dashboard.
- **Post-launch checklist:** persists as a dashboard card until all deferred items are done.

## 5. Navigation & state

- Onboarding uses a shared stepper header: back button, step title, and progress dots.
- State is held in a single `OnboardingContext` with mock data objects.
- No persistence; refreshing the app resets to A1.
- “Skip for now” on deferred screens marks the step as `skipped` and shows it in the post-launch checklist.

## 6. Mock data defaults

For the demo video and screenshots, pre-fill A2–A6 with:
- Trading name: “Demo Electrical Ltd”
- Structure: `ltd`, CH number: `12345678`, verified
- Address: `123 Test Road, Stockport SK8 3NJ`
- Service area: radius 15 miles, nations: England/Wales
- VAT: not registered
- CPS: `napit`, membership: `NE12345`, verified
- PL insurer: `AXA`, policy `PL-123`, £2m, expiry 12 months out
- Services: consumer unit, EICR, EV charger, additional points, emergency callout

## 7. UI components needed

- `StepperHeader` (back, title, progress dots)
- `VerificationBadge` (verified / pending / manual / self_declared)
- `FormField` (label, input, error)
- `AddressPicker` (postcode → list)
- `FileUploadMock` (tap to “upload”, shows thumbnail)
- `CategoryToggleCard` (icon + label + selected state)
- `LaunchGateChecklist` (used in A14 and dashboard)
- `PreviewCard` (renders customer quote form preview)

## 8. Success criteria

- A new user can complete launch-gate onboarding in the mock in under 5 minutes.
- Verification badges are visible and understandable without explanation.
- The post-launch checklist is clearly distinct from the launch gate.
- The A14 preview convinces stakeholders that the customer form will be white-labelled per business.

## 9. Out of scope for Milestone 1

- Real Companies House / CPS / HMRC verification APIs.
- File upload backend or image processing.
- OAuth connections to Stripe, Xero, etc.
- Persistent onboarding progress across app restarts.
- Deep-link resume from a real backend state.
