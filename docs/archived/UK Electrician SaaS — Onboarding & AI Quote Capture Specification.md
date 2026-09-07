# UK Electrician SaaS — Business Onboarding & AI Quote Capture
## Product & Data Specification (v1.0)

**Audience:** product, design, and engineering
**Scope:** two intake journeys — (1) electrical business sign-up/onboarding, (2) customer quote-request capture — plus the AI quote handoff and the underlying data model.
**Out of scope:** job scheduling/dispatch internals, invoicing engine, payment processing internals (referenced only where they touch these journeys).

---

## 0. Design Principles

1. **Progressive profiling.** Gate launch on the minimum viable account (identity + business basics + compliance). Everything else — pricing, branding, integrations — is collected post-launch via a setup checklist with a visible progress bar. Tradespeople abandon long forms; get them to their first lead fast.
2. **Verify, don't just collect.** Every credential a business enters (Companies House, CPS membership, insurance) should be auto-verified where an API/public register exists, and clearly badged as "verified" vs "self-declared" in the UI.
3. **Structured first, media second, free text last.** The AI quote quality is directly proportional to structured data. Free text is a fallback, never the primary capture mechanism.
4. **Property age is the master variable.** UK housing stock era drives rewire likelihood, earthing/bonding condition, and quote risk more than any other factor. It is captured early and weighted heavily in pricing logic.
5. **Triage before quote.** Emergencies route to a human call-back, not a quote form. Never let an AI quote flow delay a safety response.
6. **AI drafts, humans send.** The AI produces a draft quote for the electrician to approve or amend. The electrician's name, insurance and reputation are on every quote — the product must never auto-send pricing to a customer without their review. This is the trust model that works for trades SaaS and the positioning that wins adoption.
7. **Every field earns its place.** Each data point below lists its consumer (AI quote, verification, ops, marketing). If no consumer exists, cut the field.

---

## 0.1 Regulatory Context (as of August 2026 — bake these into copy and logic)

| Topic | Current position | Product implication |
|---|---|---|
| **Part P (Building Regs)** | Notifiable domestic work in England & Wales (new circuits, consumer unit replacement, special locations) must be self-certified via a Competent Person Scheme (NICEIC, NAPIT, ELECSA, etc.) or notified to building control. Scotland (SELECT Approved Certifier) and NI differ.[^1^] | CPS membership is a **hard trust gate** for businesses serving England/Wales; capture nation(s) served to apply the right compliance copy. |
| **Wiring regs** | BS 7671:2018, now at **Amendment 4 (A4:2026)**.[^1^] | Credential field should read "18th Edition (BS 7671, current amendment)" — don't hard-code "Amendment 2". |
| **EICR — rented sector** | 5-yearly EICR is a legal duty for private landlords in England (2020 Regs, social rented sector now also in scope), Wales (Dec 2022) and Scotland (2015, plus PAT). C1/C2/FI codes = unsatisfactory; remedials within 28 days. Fines up to £30k.[^2^][^3^] | The customer flow must detect landlord intent and surface EICR as a compliance purchase, not an optional extra. Renewal reminders = recurring revenue feature. |
| **Renters' Rights Act 2025** | Section 21 abolished from 1 May 2026; compliance evidence now feeds possession/repair duties.[^2^] | Landlord-facing messaging: EICR records and audit trails matter more, not less. |
| **OZEV EV chargepoint grant** | Homeowners with off-street parking are **not** eligible; the grant (renters, flat owners/leaseholders, landlords) requires pre-approval **before** installation via the gov.uk portal (~10 working days), with photo evidence rules for installers.[^4^][^5^] | EV branch asks tenure **before** mentioning any grant; never quote a grant amount to an ineligible homeowner; grant logic must be config-driven as amounts/rules change. |
| **MTD for Income Tax** | Live from April 2026 for sole traders/landlords >£50k gross income; £30k from 2027, £20k from 2028. VAT registration threshold £90k (MTD for VAT mandatory for all VAT-registered).[^6^][^7^] | Accounting integrations (Xero/QuickBooks/FreeAgent) are now a *compliance* selling point, not a convenience — say so in onboarding copy. |

---

## 0.2 Journey Maps at a Glance

**Journey 1 — Business Onboarding (14 screens, ~8 min to launch)**
```
A1 Welcome → A2 Account → A3 Business identity → A4 Address & service area
→ A5 Tax & VAT → A6 Compliance & credentials → A7 Team & capacity
→ A8 Services offered → A9 Pricing setup → A10 Quote defaults & terms
→ A11 Branding → A12 Payments & integrations → A13 Data import → A14 Review & launch
   └── Launch gate = A1–A6 (+A8). A7, A9–A13 can defer to post-launch checklist.
```

**Journey 2 — Customer Quote Capture (5 core blocks + dynamic branch)**
```
C1 Entry & postcode → C2 Contact → C3 Property profile → C4 Job category picker
→ C5 Dynamic job questionnaire (branched per job type) → C6 Media capture
→ C7 Timing & urgency ──[red-flag triage]──> emergency call-back route
→ C8 Budget & context → C9 Consents & submit → C10 Confirmation & expectations
        │
        └─→ AI quote engine → draft → electrician review → send
```

---
---

# PART 1 — Business Onboarding Journey (Screen-by-Screen)

Notation: **Req** = required to proceed. *(defer)* = skippable pre-launch, surfaced in post-launch checklist. Validation patterns are consolidated in Appendix A.

---

## Screen A1 — Welcome / Value Proposition

**Goal:** set expectations, reduce abandonment ("3 minutes to your first lead").

| Element | Notes |
|---|---|
| Headline + 3-bullet value prop | "Get leads. Send AI-drafted quotes in minutes. Stay compliant." |
| Progress preview | Stepper showing the 6 launch steps |
| Primary CTA: "Create my account" | → A2 |
| Secondary: "I already have an account" | → login |

**Analytics:** `onboarding_viewed`, `onboarding_started`

---

## Screen A2 — Account Creation

**Goal:** identity + auth. Minimal friction.

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Full name | text | ✓ | 2–80 chars | Split into first/last server-side |
| Work email | email | ✓ | RFC 5322; block disposable domains | Doubles as login; verification email sent |
| Mobile | tel | ✓ | UK format (07… or +447…), E.164 stored | SMS verification optional at launch, required before payouts |
| Password | password | ✓ | ≥10 chars, zxcvbn score ≥3, breach-list check | Or **SSO**: Google / Apple buttons above the fold |
| Role in business | select | ✓ | enum: `owner`, `office_manager`, `engineer`, `other` | Drives default permissions |

**Branching:** `role != owner` → show hint: "You'll be able to invite the owner later — some compliance steps may need them."

---

## Screen A3 — Business Identity

**Goal:** legal identity for invoicing, verification, and insurance matching.

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Trading name | text | ✓ | 2–100 chars | Shown on customer-facing quotes |
| Business structure | select | ✓ | enum: `sole_trader`, `ltd`, `llp`, `partnership` | Drives branches below |
| Legal entity name | text | conditional | required if structure ≠ sole_trader | |
| Companies House number | text | conditional | required if `ltd`/`llp`; 8-char alphanumeric | **Auto-verify** via Companies House API: returns legal name + registered office; pre-fills and badges "Verified" |
| Year established | number | — | 1900–current year | Trust badge on profile |
| Website / Facebook page | url | — | valid URL | Optional trust signal; used to pre-fill branding (logo scrape suggestion) |

**Branching:**
- `structure == sole_trader` → hide Companies House fields; show MTD hint: "From April 2026, sole traders over £50k must use MTD-compatible software — we sync with Xero/QuickBooks/FreeAgent."[^6^]
- CH API match fails → allow manual continue, flag record `verification_status: manual_review`.

---

## Screen A4 — Address & Service Area

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Trading address | address lookup | ✓ | postcode → address picker | Base point for travel calculations |
| Registered office | address | conditional | if Ltd; pre-filled from CH lookup, editable | |
| Service area mode | radio | ✓ | `radius` \| `postcode_list` | |
| Radius (miles) | slider 5–50 | conditional | if mode=radius | Map preview with drive-time overlay |
| Postcode sectors | multi-input | conditional | if mode=postcode_list; validate each against UK postcode sector pattern | e.g. `M1`, `M2`, `SK8` |
| Nations served | multi-checkbox | ✓ | England / Wales / Scotland / NI | **Drives compliance copy** (Part P vs SELECT vs NI frameworks)[^1^] |

**Why it matters:** service area feeds lead matching and travel-time pricing in the AI quote.

---

## Screen A5 — Tax & VAT

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| VAT registered? | yes/no | ✓ | — | |
| VAT number | text | conditional | 9 digits (GB prefix optional); checksum-validate; verify via HMRC API if available | Required if yes |
| VAT scheme | select | conditional | `standard`, `flat_rate` | Flat rate changes invoice maths |
| Default VAT rate on domestic work | derived | auto | 20% standard; flag that some energy-saving materials may qualify for 0%/reduced rate — electrician confirms per quote line | Never auto-apply reduced rates without user confirmation |

---

## Screen A6 — Compliance & Credentials (the trust gate)

**Goal:** verify the business is legitimate. This screen is the platform's differentiator — take the time here.

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Competent Person Scheme | select | ✓ (if England/Wales) | enum: `niceic`, `napit`, `elecsa`, `stroma`, `besca`, `select_scotland`, `none_yet` | `select_scotland` shown when nation=Scotland[^1^] |
| CPS membership number | text | conditional | scheme-specific pattern | **Async verification** against scheme's public register where possible; badge `verified` / `pending` / `manual_review` |
| 18th Edition (BS 7671) held? | yes/no + upload | ✓ | certificate upload (PDF/JPG, ≤10MB) | Copy reads "current amendment" (A4:2026)[^1^] |
| Inspection & testing qual (2391 or equiv.) | yes/no + upload | conditional | required if business offers EICRs[^2^] | |
| Public liability insurer | text | ✓ | — | |
| PL policy number | text | ✓ | — | |
| PL cover level | select | ✓ | £1m / £2m / £5m / £10m | |
| PL expiry date | date | ✓ | must be future date | **Lifecycle hook:** renewal reminder at 30/14/7 days; profile badge drops if lapsed |
| Policy document upload | file | ✓ | PDF/JPG ≤10MB | Enables verified badge |
| Professional indemnity (optional) | group | — | same sub-fields | Recommended if offering design/consultancy |
| ECS card / JIB grading (optional) | text | — | — | Extra trust signal |
| DBS check status (optional) | select | — | `basic`, `enhanced`, `none` | Domestic work in occupied homes — strong conversion signal for homeowners |

**`none_yet` branch:** business may continue onboarding but is tagged `provisional`; customer-facing profile and AI-quote auto-send are locked until a CPS is added. Show explainer: notifiable work without scheme registration or building-control sign-off breaches building regs.[^1^]

**Analytics:** `credential_verified{scheme}`, `credential_manual_review`

---

## Screen A7 — Team & Capacity *(defer)*

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Number of engineers | number | ✓ | 1–200 | Capacity for scheduling; plan sizing |
| Number of vans | number | — | 0–200 | |
| Team invites | repeatable (name, email, mobile, role) | — | role enum: `admin`, `engineer`, `office` | Invite emails sent on launch |
| Engineer grades | per member select | — | `qualified`, `apprentice`, `mate` | Feeds per-grade labour rates in A9 |

---

## Screen A8 — Services Offered

**Goal:** determines which quote questionnaire branches this business's customers see, and which pricing templates A9 asks for. **Required before launch.**

Job category picker (multi-toggle cards with icons):

```
ev_charger · consumer_unit · full_rewire · partial_rewire · eicr
additional_points (sockets/lights) · outdoor_power · fault_finding
smart_home · lighting_design · data_networking · emergency_callout · other
```

For each enabled category, one follow-up chip row:
- EICR → "Landlord compliance work?" (drives compliance messaging)[^2^]
- EV charger → "OZEV grant handling?" (drives grant workflow)[^4^]
- Emergency → "24/7 or hours-limited?" (drives triage SLA)

---

## Screen A9 — Pricing Setup *(defer, but required before first AI quote)*

**This is the AI quoting engine's core input.** Presented as a guided wizard, one section per enabled category, with sensible defaults pre-filled from market benchmarks so a business can accept-and-go.

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Labour pricing model | select | ✓ | `day_rate`, `half_day`, `hourly`, `per_point`, `fixed_per_job` | Per-category override allowed |
| Standard hourly rate | money | conditional | £10–£300 | Per engineer grade if A7 completed |
| Day rate | money | conditional | £80–£1,500 | |
| Call-out fee | money | ✓ | £0–£500 | Applied to small jobs |
| Minimum charge | money | ✓ | £0–£500 | Floor price on any quote |
| Materials markup % | number | ✓ | 0–100 | Or trade-discount pass-through % |
| Preferred wholesalers | multi-select | — | CEF, Rexel, Screwfix, Edmundson, City Electrical, Toolstation, other | Materials pricing source |
| Per-category base price | money | ✓ per enabled category | benchmark-banded warning (not hard limit) if >2× or <0.5× regional median | e.g. "EICR from £…", "CU upgrade from £…" |
| Emergency multiplier | number | conditional | 1.0–3.0 | If emergency category enabled |
| Travel pricing | select | — | `included_in_radius`, `per_mile_beyond`, `per_hour_beyond` | Uses service area from A4 |

---

## Screen A10 — Quote Defaults & Terms *(defer)*

| Field | Type | Req | Notes |
|---|---|---|---|
| Quote validity period | number (days) | ✓ | Default 30 |
| Deposit policy | select + % | ✓ | `none`, `percent`, `fixed` — materials-heavy jobs default suggestion 25% |
| Payment terms | select | ✓ | `on_completion`, `7_days`, `14_days`, `30_days` |
| Finance options offered | yes/no + provider | — | Rendered in quote footer |
| T&Cs | template picker or upload | ✓ | 3 solicitor-reviewed UK trades templates provided; versioned |
| Quote/invoice reference scheme | pattern | — | e.g. `Q-{YYYY}-{NNNN}` |
| Certifications issued | multi-select | ✓ | EIC, MEIWC, EICR, Part P notification — drives post-job document automation[^1^] |

---

## Screen A11 — Branding *(defer)*

| Field | Type | Notes |
|---|---|---|
| Logo upload | image (PNG/SVG, ≥400px) | Auto-suggested from website/Facebook if provided in A3 |
| Brand colour | colour picker | Contrast-checked for quote PDF readability |
| Email signature / intro blurb | rich text | Used on quote delivery emails |
| Quote PDF template | picker (3 layouts) | Live preview with sample data |

---

## Screen A12 — Payments & Integrations *(defer)*

| Field | Type | Notes |
|---|---|---|
| Payment provider connect | OAuth | Stripe (cards), GoCardless (direct debit) — required to take deposits |
| Bank details (fallback) | sort code + account | Modulus-checked; used on invoice footer if no provider connected |
| Accounting sync | OAuth | **Xero / QuickBooks / FreeAgent** — copy: "MTD-ready from day one"[^6^] |
| Calendar connect | OAuth | Google / Outlook — for booking slots shown to customers |
| WhatsApp Business | opt-in | Customer comms channel preference |

---

## Screen A13 — Existing Data Import *(defer)*

| Field | Type | Notes |
|---|---|---|
| Customer CSV import | file + column mapper | Template provided; dedupe on email/phone |
| Active quotes import | file | Optional; marked legacy |
| Skip → "start fresh" | button | Most common path for ≤2-year-old businesses |

---

## Screen A14 — Review & Launch

- **Checklist panel:** ✅ launch-gate items (A2–A6, A8) / ⏳ deferred items with one-click resume.
- **Compliance summary card:** badges — CH verified, CPS verified/pending, insurance valid until {date}.
- **Preview:** "See your customer quote form" — renders Journey 2 exactly as this business's customers will experience it (categories from A8, branding from A11).
- **Go-live CTA** → status `active`; lead routing enabled; post-launch checklist persists in dashboard header until 100%.

**Analytics:** `onboarding_completed`, `time_to_launch`, `deferred_items_count`

---
---

# PART 2 — Customer Quote Capture Journey (Screen-by-Screen)

**Context:** this form is white-labelled per business (logo, colours, categories from A8). Mobile-first — most domestic leads arrive on phones. Save-and-resume link emailed if abandoned after C2.

---

## Screen C1 — Entry & Postcode

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Postcode | text | ✓ | UK postcode regex (App. A) | **Instant checks:** (1) inside this business's service area? (2) EPC register lookup fired in background (property size/age band pre-fill)[^8^] |

**Branches:**
- Outside service area → polite decline screen + option to leave details for referral.
- EPC found → "We've found your property details — just confirm a few things" (reduces form length, boosts completion).

---

## Screen C2 — Contact

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Name | text | ✓ | — | |
| Mobile | tel | ✓ | UK mobile | Quote + updates by SMS/WhatsApp |
| Email | email | ✓ | — | Quote PDF delivery |
| Preferred contact method | select | ✓ | `phone`, `sms`, `whatsapp`, `email` | |
| Best time to call | multi-checkbox | — | morning/afternoon/evening | Only if phone preferred |

*Captured before property details deliberately: abandoned partial leads are still contactable.*

---

## Screen C3 — Property Profile

**The AI's risk model lives here.** Friendly language — homeowners don't know trade terms.

| Field | Type | Req | Validation | Notes |
|---|---|---|---|---|
| Property type | card select | ✓ | `detached`, `semi`, `terrace`, `bungalow`, `flat_maisonette` | Flat → extra access questions |
| Property age | banded select | ✓ | `pre_1930`, `1930_1960`, `1960_1980`, `1980_2000`, `post_2000`, `not_sure` | **Pre-filled from EPC if found;** `not_sure` → show era photos picker (visual recognition beats knowledge)[^8^] |
| Bedrooms / reception rooms | steppers | ✓ | 0–15 | Point-count estimation |
| Floors | stepper | ✓ | 1–5 | |
| Tenure | select | ✓ | `owner_occupier`, `private_tenant`, `landlord`, `housing_association` | **Major branch:** landlord → EICR compliance framing; tenant → landlord-permission nudge[^2^][^4^] |
| Flat floor level + lift? | conditional | — | if flat | Access/labour adjustment |
| Parking for a van? | yes/no | ✓ | — | Labour-time factor |
| Consumer unit photo | upload | ✓ (skippable with warning) | JPG/PNG/HEIC ≤15MB | Guided overlay: "Open the grey/white box near your meter and photograph the switches" — **single most valuable image in the flow** |
| Fuse board style | visual select | — | photos: modern RCBO board / RCD split-load / rewireable fuses (old wire type) / not sure | Old wire-fuse board → rewire-risk flag |
| Known electrical issues | multi-checkbox | — | tripping, flickering, burning smell, buzzing, sockets not working, none | **Feeds triage (C7)** |

---

## Screen C4 — Job Category Picker

Tiles limited to categories this business enabled (A8). "Something else" always available → `other` branch (free text + photos, always electrician-reviewed — never AI-priced without human input).

---

## Screen C5 — Dynamic Job Questionnaire (branch specs)

Common logic: every branch ends with optional "anything else we should know?" free text. Every branch writes into `quote_request.details` JSONB keyed by job type (schema in Part 4).

### C5.1 — EV Charger
| Field | Type | Notes |
|---|---|---|
| Vehicle make/model or "ordering soon" | autocomplete | Charger compatibility |
| Charger brand preference | select / no preference | |
| Where will the car park? | select | `driveway`, `garage`, `street` — **street → ineligible for standard install; route to advice screen** |
| Tenure (recalled from C3) | derived | **owner+off-street → no grant mention;** renter/flat-owner/landlord → OZEV grant explainer + eligibility questions + "do not install before approval" warning[^4^][^5^] |
| Distance: consumer unit ↔ parking | banded | `<5m`, `5–10m`, `10–20m`, `>20m` — cable-run cost driver |
| Mounting surface | select | brick, render, timber, garage interior |
| Main fuse rating | photo + select | 60/80/100A / not sure — photo of cut-out; 60A → **DNO upgrade flag** (adds lead time, not price) |
| Wi-Fi at charge location? | yes/no | Smart charger requirement |
| Three-phase supply? | yes/no/not sure | |

### C5.2 — Consumer Unit Upgrade
| Field | Type | Notes |
|---|---|---|
| Number of circuits | count-assist | "Count the switches in your photo" — AI cross-checks count from image |
| Reason for upgrade | select | old fuse wire, no RCD, adding circuits, survey recommendation, other |
| Known faults | checkbox group | Feeds triage |
| Property occupied during work? | yes/no | Power-down duration messaging |

### C5.3 — Rewire (full/partial)
| Field | Type | Notes |
|---|---|---|
| Scope | radio | full house / specific rooms → room picker |
| Occupied during works? | yes/no | **Major price driver** — occupied rewires take materially longer |
| Decoration tolerance | select | `chase_and_make_good`, `surface_trunking`, `redecorating_anyway` |
| Flooring liftable? | per-floor select | carpet, laminate, boards, tiles |
| Loft access? | yes/no | |
| Timescale pressure | select | e.g. before move-in / renovation phase |

### C5.4 — EICR
| Field | Type | Notes |
|---|---|---|
| Who's asking? | select | landlord, homeowner, buyer (pre-purchase), seller |
| **Landlord branch** | group | compliance explainer (5-year duty, tenant copy within 28 days, C1/C2/FI remedials in 28 days); last EICR date; certificate upload if exists[^2^][^3^] |
| Property vacant or tenanted? | select | Access planning |
| Number of circuits | count/not sure | Primary price driver |
| Remedial works wanted in quote? | yes/no/price separately | Quote structure option |

### C5.5 — Additional Sockets / Lights
| Field | Type | Notes |
|---|---|---|
| What & how many | repeatable rows | item type (socket, light, switch, outdoor socket, downlights) × count × room |
| Wall type | per item or global | brick, stud/plasterboard, unknown |
| Photos of each location | upload | Guided per item |
| New circuit likely? | derived | AI estimates from load description; confirms in draft |

### C5.6 — Outdoor / Garden Power
| Field | Type | Notes |
|---|---|---|
| What's being powered | select | garden office/pod, hot tub, lighting, sockets, shed — **hot tub/sauna → high-load flag, may need dedicated circuit** |
| Distance from house | banded | Trench length |
| Ground type | select | lawn, flowerbed, patio (lifting needed), concrete (biggest cost) |
| Photos of route | upload | |

### C5.7 — Fault Finding
| Field | Type | Notes |
|---|---|---|
| Symptom | structured select + free text | tripping (which switch?), dead circuit, flickering, smell, shocks/tingling |
| When did it start? / constant or intermittent? | select | |
| What triggers it? | free text | |
| **Red-flag auto-detection** | derived | burning smell, shocks, water ingress → **immediately route to triage (C7-E), skip remaining questions** |

### C5.8 — Smart Home / Lighting Design
| Field | Type | Notes |
|---|---|---|
| Ecosystem preference | select | Philips Hue, Loxone, KNX, no preference |
| Rooms in scope | multi | |
| Existing smart kit | free text + brand chips | |
| Budget band | required here | Design-led work can't be auto-priced below a floor — draft quotes always flagged for review |

### C5.9 — Other
Free text (min 30 chars prompt-assist) + required photos. Always `requires_human_review = true`.

---

## Screen C6 — Media Capture (consolidated)

- **Required:** consumer unit photo (if skipped in C3, re-prompted here with explanation of why).
- **Branch-required:** photos defined in C5 branch (charger location, rewire rooms, garden route…).
- **Optional:** video walkthrough (≤60s) for complex jobs; document upload (previous EICR, plans, survey).
- **UX:** in-app camera with guide overlays and example "good photo" thumbnails; HEIC→JPEG transcode; >15MB compress; offline queue for poor signal.

---

## Screen C7 — Timing, Urgency & Triage

| Field | Type | Notes |
|---|---|---|
| When do you need this? | select | `emergency_today`, `this_week`, `this_month`, `flexible`, `just_researching` |
| Preferred dates | date multi-pick | If business connected calendar (A12), show real slots |

**Triage routing rules (evaluated before form completion):**

| Trigger | Route |
|---|---|
| Burning smell / smoke / scorch marks / electric shocks / water on electrics | **Emergency:** stop quote flow → "Call now" tap-to-call + safety guidance (isolate at main switch if safe, UK Power Networks 105 for supply loss). No AI quote. Notify business instantly (push + SMS). |
| `emergency_today` selected | Same call-back route, SLA from A8 emergency settings; emergency pricing multiplier disclosed up front |
| Repeated tripping, partial power loss | Priority call-back within business-defined SLA; AI draft created but flagged `safety_review` |
| Everything else | Standard AI quote pipeline |

---

## Screen C8 — Budget & Context

| Field | Type | Req | Notes |
|---|---|---|---|
| Budget band | select | optional | `under_250`, `250_500`, `500_1k`, `1k_2.5k`, `2.5k_plus`, `no_idea` — calibration + lead scoring, never shown to alter price |
| How did you hear? | select | optional | Attribution |
| Insurance claim work? | yes/no | optional | Different quote format (itemised, insurer-friendly) |

---

## Screen C9 — Consents & Submit

| Field | Req | Notes |
|---|---|---|
| T&Cs / privacy notice acknowledgement | ✓ | Checkbox, versioned record (who/when/version/IP) |
| Contact permission | ✓ | "We need to contact you about this quote" — service comms, not marketing |
| Marketing opt-in | — | **Unticked by default, granular:** tips & offers from {Business Name} (GDPR/PECR-compliant, no pre-ticked boxes) |
| Landlord-permission confirmation | conditional | If tenant + work requiring landlord consent |

**Submit →** `quote_request` created; AI pipeline invoked; confirmation screen.

---

## Screen C10 — Confirmation

- Sets expectations honestly: "{Business} will review your details and send your quote — usually within {X hours}." (X from business settings; **never promise an instant auto-sent quote** — the electrician approves first.)
- Shows submission summary + photos received.
- If high-confidence AI draft: "Good news — your quote is already being prepared."
- Referral nudge + review link post-delivery.

**Analytics:** `quote_request_submitted{job_type, urgency}`, `form_abandoned{last_screen}`, `triage_routed{trigger}`

---
---

# PART 3 — AI Quote Handoff

## 3.1 Pipeline

```
quote_request.created
  → 1. Enrichment: EPC lookup, address geocode, property-age inference, drive-time from business base
  → 2. Vision pass: consumer unit photo classification (board type, circuit count, RCD presence),
       condition flags; other photos object/scene tagged
  → 3. Scoping: job template × property profile × answers → labour units + materials list
  → 4. Pricing: business rates (A9) × labour units + materials × markup + call-out/minimum rules
       + travel rule + emergency multiplier
  → 5. Draft assembly: itemised quote, plain-English scope, T&Cs, deposit terms, validity
  → 6. Confidence scoring → routing (below)
  → 7. Electrician review UI: edit lines, adjust price, approve & send (or book site visit)
```

## 3.2 Confidence routing

| Confidence | Route | UX |
|---|---|---|
| ≥ 0.85 | Draft ready for one-tap approval | "Review & send" — 30-second job |
| 0.60–0.85 | Draft with flagged assumptions | Assumptions highlighted ("Assumed stud walls — adjust if brick"), electrician confirms each |
| < 0.60 | No price drafted | "Book a site visit" flow with pre-filled context; AI provides scoping checklist instead |
| Any `safety_review` / `other` / landlord-remedial complexity | Always human review | Never auto-draft a price |

## 3.3 Learning loop

Record per quote: `ai_drafted_amount`, `final_sent_amount`, edits made, outcome (`accepted`, `rejected`, `expired`, `won_competitor`). This feedback corpus is the fine-tuning/calibration asset — schema supports it from day one (`quotes.ai_metadata` JSONB).

---
---

# PART 4 — Data Schema

## 4.1 Entity Relationship Overview

```
businesses 1───* users
businesses 1───* business_credentials
businesses 1───* pricing_profiles 1───* pricing_rates
businesses 1───* service_areas
businesses 1───* business_services        (enabled job categories)
businesses 1───* integrations
businesses 1───* customers 1───* properties
properties  1───* quote_requests 1───* media_assets
quote_requests 1───1 quotes 1───* quote_line_items
customers   1───* consents
(all)       *───1 events                  (audit/analytics stream)
```

## 4.2 Enumerations

```sql
CREATE TYPE business_structure AS ENUM ('sole_trader','ltd','llp','partnership');
CREATE TYPE user_role          AS ENUM ('owner','admin','office_manager','engineer');
CREATE TYPE cps_scheme         AS ENUM ('niceic','napit','elecsa','stroma','besca','select_scotland','none_yet');
CREATE TYPE verification_status AS ENUM ('verified','pending','manual_review','failed','self_declared');
CREATE TYPE labour_model       AS ENUM ('day_rate','half_day','hourly','per_point','fixed_per_job');
CREATE TYPE job_type           AS ENUM ('ev_charger','consumer_unit','full_rewire','partial_rewire','eicr',
                                        'additional_points','outdoor_power','fault_finding','smart_home',
                                        'lighting_design','data_networking','emergency_callout','other');
CREATE TYPE property_type      AS ENUM ('detached','semi','terrace','bungalow','flat_maisonette');
CREATE TYPE property_era       AS ENUM ('pre_1930','1930_1960','1960_1980','1980_2000','post_2000','unknown');
CREATE TYPE tenure             AS ENUM ('owner_occupier','private_tenant','landlord','housing_association');
CREATE TYPE urgency            AS ENUM ('emergency_today','this_week','this_month','flexible','just_researching');
CREATE TYPE quote_request_status AS ENUM ('new','triaged','ai_drafted','in_review','site_visit_needed',
                                          'quoted','accepted','declined','expired','closed');
CREATE TYPE quote_status       AS ENUM ('draft','awaiting_review','sent','viewed','accepted','rejected','expired','superseded');
CREATE TYPE contact_channel    AS ENUM ('phone','sms','whatsapp','email');
```

## 4.3 Core Tables (PostgreSQL)

```sql
-- ─────────── BUSINESSES ───────────
CREATE TABLE businesses (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trading_name           text NOT NULL,
  legal_name             text,
  structure              business_structure NOT NULL,
  companies_house_number varchar(8),
  ch_verified            verification_status DEFAULT 'self_declared',
  year_established       smallint,
  website_url            text,
  trading_address        jsonb NOT NULL,          -- {line1,line2,city,postcode,lat,lng}
  registered_office      jsonb,
  nations_served         text[] NOT NULL,          -- {'england','wales'}
  vat_registered         boolean NOT NULL DEFAULT false,
  vat_number             varchar(12),
  vat_scheme             text,                     -- 'standard'|'flat_rate'
  status                 text NOT NULL DEFAULT 'onboarding',  -- onboarding|provisional|active|suspended
  launched_at            timestamptz,
  onboarding_progress    jsonb NOT NULL DEFAULT '{}',  -- {a3:true,a6:false,...} checklist state
  branding               jsonb DEFAULT '{}',       -- {logo_url,colour,template_id,email_blurb}
  quote_defaults         jsonb DEFAULT '{}',       -- {validity_days,deposit_type,deposit_value,payment_terms,ref_scheme,finance}
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  deleted_at             timestamptz
);

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id   uuid NOT NULL REFERENCES businesses(id),
  full_name     text NOT NULL,
  email         citext NOT NULL UNIQUE,
  mobile_e164   varchar(16),
  role          user_role NOT NULL,
  auth_provider text NOT NULL DEFAULT 'password',  -- password|google|apple
  mobile_verified_at timestamptz,
  last_login_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  deleted_at    timestamptz
);

CREATE TABLE business_credentials (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id       uuid NOT NULL REFERENCES businesses(id),
  cps_scheme        cps_scheme,
  cps_membership_no text,
  cps_status        verification_status DEFAULT 'pending',
  cps_verified_at   timestamptz,
  bs7671_held       boolean,
  bs7671_cert_file  text,                     -- object storage key
  inspection_qual_2391 boolean,
  pl_insurer        text,
  pl_policy_no      text,
  pl_cover_level_gbp int,
  pl_expiry_date    date,
  pl_policy_file    text,
  pi_details        jsonb,                    -- optional PI block
  ecs_jib           text,
  dbs_status        text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
-- INDEX for the insurance-renewal cron:
CREATE INDEX idx_cred_pl_expiry ON business_credentials(pl_expiry_date) WHERE pl_expiry_date IS NOT NULL;

CREATE TABLE pricing_profiles (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id  uuid NOT NULL REFERENCES businesses(id),
  labour_model labour_model NOT NULL,
  hourly_rate  numeric(8,2),
  day_rate     numeric(8,2),
  callout_fee  numeric(8,2) NOT NULL DEFAULT 0,
  minimum_charge numeric(8,2) NOT NULL DEFAULT 0,
  materials_markup_pct numeric(5,2) NOT NULL DEFAULT 0,
  emergency_multiplier numeric(3,2) DEFAULT 1.5,
  travel_rule  jsonb,                          -- {type, free_radius_mi, per_mile}
  wholesalers  text[],
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pricing_rates (                    -- per-category base prices
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id    uuid NOT NULL REFERENCES pricing_profiles(id),
  job_type      job_type NOT NULL,
  base_price    numeric(10,2) NOT NULL,
  notes         text,
  UNIQUE(profile_id, job_type)
);

CREATE TABLE service_areas (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id),
  mode        text NOT NULL,                   -- 'radius'|'postcode_list'
  radius_mi   smallint,
  postcode_sectors text[],                     -- {'M1','M2','SK8'}
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE business_services (
  business_id uuid REFERENCES businesses(id),
  job_type    job_type,
  options     jsonb DEFAULT '{}',              -- {landlord_eicr:true, ozev_handling:true, emergency_sla:'24/7'}
  enabled     boolean NOT NULL DEFAULT true,
  PRIMARY KEY (business_id, job_type)
);

CREATE TABLE integrations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id),
  provider    text NOT NULL,                   -- stripe|gocardless|xero|quickbooks|freeagent|google_cal|outlook
  status      text NOT NULL DEFAULT 'connected',
  credentials jsonb,                           -- encrypted at rest (pgcrypto / KMS envelope)
  connected_at timestamptz DEFAULT now(),
  UNIQUE(business_id, provider)
);

-- ─────────── CUSTOMERS & PROPERTIES ───────────
CREATE TABLE customers (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id  uuid NOT NULL REFERENCES businesses(id),
  full_name    text NOT NULL,
  mobile_e164  varchar(16),
  email        citext,
  preferred_channel contact_channel,
  best_call_times   text[],
  source       text,                           -- attribution
  created_at   timestamptz NOT NULL DEFAULT now(),
  deleted_at   timestamptz                     -- GDPR erasure = anonymise, not hard-delete financials
);

CREATE TABLE properties (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id   uuid NOT NULL REFERENCES customers(id),
  address       jsonb NOT NULL,                -- incl. postcode, lat/lng, uprn
  property_type property_type,
  era           property_era,
  tenure        tenure,
  bedrooms      smallint,
  reception_rooms smallint,
  floors        smallint,
  flat_floor    smallint,
  has_lift      boolean,
  van_parking   boolean,
  epc_data      jsonb,                         -- raw EPC register payload + fetched_at
  consumer_unit jsonb,                         -- {board_style, circuit_count, rcd_present, photo_ids[], vision_flags{}}
  known_issues  text[],
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- ─────────── QUOTE REQUESTS (the AI input) ───────────
CREATE TABLE quote_requests (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id    uuid NOT NULL REFERENCES businesses(id),
  customer_id    uuid NOT NULL REFERENCES customers(id),
  property_id    uuid NOT NULL REFERENCES properties(id),
  job_type       job_type NOT NULL,
  details        jsonb NOT NULL DEFAULT '{}',  -- branch answers, keyed per 4.4
  urgency        urgency NOT NULL,
  preferred_dates date[],
  budget_band    text,
  insurance_work boolean DEFAULT false,
  triage         jsonb,                        -- {flags:[], route:'emergency_callback'|'standard', triggered_at}
  status         quote_request_status NOT NULL DEFAULT 'new',
  ai_confidence  numeric(4,3),
  source_channel text,                         -- web_form|phone_logged|repeat_customer
  submitted_at   timestamptz NOT NULL DEFAULT now(),
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_qr_business_status ON quote_requests(business_id, status);
CREATE INDEX idx_qr_details_gin ON quote_requests USING gin(details);

CREATE TABLE media_assets (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quote_request_id uuid REFERENCES quote_requests(id),
  business_id  uuid NOT NULL REFERENCES businesses(id),
  kind         text NOT NULL,                  -- consumer_unit|job_photo|video|document
  storage_key  text NOT NULL,                  -- signed-URL object storage
  mime_type    text,
  bytes        int,
  vision_labels jsonb,                         -- CV output
  uploaded_at  timestamptz NOT NULL DEFAULT now(),
  retention_until date                         -- GDPR housekeeping
);

-- ─────────── QUOTES (the AI output + human approval) ───────────
CREATE TABLE quotes (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quote_request_id uuid NOT NULL REFERENCES quote_requests(id),
  business_id      uuid NOT NULL REFERENCES businesses(id),
  reference        text NOT NULL,              -- Q-2026-0001 per business scheme
  status           quote_status NOT NULL DEFAULT 'draft',
  ai_metadata      jsonb,                      -- {confidence, assumptions[], vision_flags, model_version, drafted_amount}
  subtotal_net     numeric(12,2),
  vat_amount       numeric(12,2),
  total_gross      numeric(12,2),
  deposit_amount   numeric(12,2),
  validity_until   date,
  terms_version    text,
  reviewed_by      uuid REFERENCES users(id),  -- null until human review
  approved_at      timestamptz,
  sent_at          timestamptz,
  viewed_at        timestamptz,
  decided_at       timestamptz,
  outcome          text,                       -- accepted|rejected|expired|won_competitor
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_id, reference)
);

CREATE TABLE quote_line_items (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quote_id  uuid NOT NULL REFERENCES quotes(id),
  sort      smallint NOT NULL,
  kind      text NOT NULL,                     -- labour|materials|callout|travel|other
  description text NOT NULL,
  qty       numeric(8,2) NOT NULL DEFAULT 1,
  unit      text,                              -- hours|days|points|items
  unit_price numeric(10,2) NOT NULL,
  vat_rate  numeric(4,2) NOT NULL DEFAULT 20,
  ai_generated boolean NOT NULL DEFAULT false, -- edited lines flip to false
  edited_by uuid REFERENCES users(id)
);

CREATE TABLE consents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL REFERENCES customers(id),
  business_id uuid NOT NULL REFERENCES businesses(id),
  type        text NOT NULL,                   -- terms_acceptance|service_contact|marketing
  granted     boolean NOT NULL,
  policy_version text NOT NULL,
  channel     text,                            -- web_form
  ip_address  inet,
  recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE events (                          -- append-only audit + analytics
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  business_id uuid,
  actor_type text,                             -- user|customer|system|ai
  actor_id   uuid,
  event      text NOT NULL,
  payload    jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

## 4.4 `quote_requests.details` JSONB shapes (per job type)

These are the contract between the C5 branch screens and the AI. Version them (`details._v`) so new fields don't break older submissions.

```json
// ev_charger
{ "_v": 1, "vehicle": "Tesla Model 3", "charger_pref": "ohome|zappi|no_preference",
  "parking": "driveway", "cu_to_parking_m": "5_10", "mount_surface": "brick",
  "main_fuse_a": 80, "wifi_at_location": true, "three_phase": "not_sure",
  "ozev": { "eligible_class": "renter|flat_owner|landlord|none", "pre_approved": false } }

// consumer_unit
{ "_v": 1, "circuits": 8, "reason": "no_rcd", "occupied_during_work": true, "faults": [] }

// full_rewire / partial_rewire
{ "_v": 1, "scope": "full|rooms", "rooms": ["kitchen","lounge"],
  "occupied": true, "decoration": "chase_and_make_good",
  "flooring": { "ground": "boards", "first": "carpet" }, "loft_access": true }

// eicr
{ "_v": 1, "requester": "landlord", "last_eicr_date": "2021-03-01",
  "last_eicr_upload_id": "uuid", "tenanted": true, "circuits": 6,
  "remedials_in_quote": "price_separately" }

// additional_points
{ "_v": 1, "items": [ { "type": "socket", "count": 2, "room": "lounge", "wall": "brick" } ] }

// outdoor_power
{ "_v": 1, "powering": "hot_tub", "high_load": true, "distance_m": "10_20", "ground": "patio" }

// fault_finding
{ "_v": 1, "symptom": "tripping", "which_device": "rcd_main", "onset": "this_week",
  "pattern": "intermittent", "trigger": "kettle", "red_flags": [] }
```

## 4.5 AI Payload (quote request → quote engine)

What the engine receives — assembled server-side, never trusting client-only data:

```json
{
  "quote_request_id": "uuid",
  "business": {
    "pricing": { "labour_model": "hourly", "hourly_rate": 65.00, "callout_fee": 0,
                 "minimum_charge": 95.00, "materials_markup_pct": 20,
                 "emergency_multiplier": 1.5, "travel_rule": {"type":"included_in_radius"} },
    "base_prices": { "consumer_unit": 550.00 },
    "quote_defaults": { "validity_days": 30, "deposit_type": "percent", "deposit_value": 25 },
    "wholesalers": ["CEF"]
  },
  "property": { "type": "semi", "era": "1930_1960", "bedrooms": 3, "floors": 2,
                "epc": {}, "consumer_unit_vision": {"board_style":"rewireable_fuses","rcd":false},
                "drive_time_min": 14 },
  "job": { "type": "consumer_unit", "details": {}, "urgency": "this_month" },
  "media": [ {"kind":"consumer_unit","vision_labels":{}} ],
  "constraints": { "human_review_required": false }
}
```

---

# Appendix A — Validation Patterns

| Field | Pattern / rule |
|---|---|
| UK postcode | `^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$` — normalise to upper-case, single space before inward code |
| UK mobile | `^(\+44\s?7\d{3}\s?\d{3}\s?\d{3}|07\d{3}\s?\d{3}\s?\d{3})$` — store E.164 |
| VAT number | 9 digits after optional `GB`; HMRC checksum; live-verify via HMRC API where available |
| Companies House no. | 8 chars alphanumeric (e.g. `01234567`, `SC123456`) — validate via CH API response, not regex alone |
| Sort code / account | 6-digit sort code (modulus 10/11 check), 8-digit account |
| File uploads | PDF/JPG/PNG/HEIC, ≤15MB/image, ≤25MB/doc; AV-scan; strip EXIF geodata from customer photos unless needed for scoping |
| Free text | 1,000-char cap; profanity/PII lint on customer-facing fields |

# Appendix B — Analytics Events (minimum set)

`onboarding_started` · `onboarding_step_completed{screen}` · `onboarding_abandoned{screen}` · `credential_verified{scheme}` · `onboarding_completed{time_to_launch, deferred_count}` · `quote_form_viewed{business_id}` · `quote_form_abandoned{last_screen}` · `triage_routed{trigger}` · `quote_request_submitted{job_type, urgency}` · `ai_quote_drafted{confidence_band}` · `quote_approved{edit_delta_pct}` · `quote_sent` · `quote_outcome{outcome, days_to_decision}`

# Appendix C — GDPR & Data Handling Notes

- **Lawful basis:** contract (quote provision) for service data; consent for marketing (granular, unticked by default, versioned in `consents`).
- **Data minimisation:** budget band and marketing opt-in are the only non-essential customer fields — both optional.
- **Retention:** quote media default retention 24 months (`media_assets.retention_until`), configurable; erasure requests anonymise `customers` PII while preserving financial records (legal obligation, 6 years).
- **Customer photos:** strip EXIF unless geodata is used for scoping; signed URLs only; never public buckets.
- **AI processing:** disclose AI-assisted quoting in the business-facing T&Cs and give businesses an opt-out per quote; the customer-facing promise is "reviewed by your electrician", which is literally true in this design.

---

*Regulatory references verified August 2026; grant amounts, thresholds and scheme rules change — implement them as config, not constants.*

[^1^]: https://www.elec-mate.com/part-p-self-certification — Part P scope, competent person schemes (NICEIC/NAPIT/ELECSA), Scotland/NI differences, BS 7671:2018+A4:2026
[^2^]: https://www.lettingaproperty.com/landlord/blog/mandatory-electrical-safety-inspections/ — Electrical Safety Standards in the PRS (England) Regulations 2020, 5-yearly EICR, C1/C2/FI codes, Wales/Scotland differences, Renters' Rights Act 2025
[^3^]: https://www.augustapp.com/blog/electrical-safety-inspections-for-landlords-your-complete-eicr-guide-for-2026 — landlord EICR duties, 28-day remedials, social rented sector in scope from late 2025
[^4^]: https://find-government-grants.service.gov.uk/grants/electric-vehicle-chargepoint-grant-for-renters-and-flat-owners-2 — EV chargepoint grant eligibility (renters, flat owners; dedicated off-street parking; approved vehicles)
[^5^]: https://solidstudio.io/blog/ozev-ev-chargepoint-grant-2026-complete-uk-guide-for-landlords-renters — 2026 OZEV application process: approval before installation, ~10 working days, photo evidence rules
[^6^]: https://www.sage.com/en-gb/blog/self-assessment-ending-making-tax-digital-sole-traders/ — MTD for Income Tax thresholds: £50k from April 2026, £30k 2027, £20k 2028
[^7^]: https://www.autoentry.com/news-insights/mtd-for-income-tax-self-assessment-what-are-the-thresholds — MTD threshold detail; VAT registration threshold £90k
[^8^]: EPC register lookup (gov.uk "Find an energy certificate") — address-matched property age band and floor area used to pre-fill C3
