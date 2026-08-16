# My Trade Portal — Pivot Migration Plan
## From OCERP/BoQ back-office → brandable iOS mobile-first quoting platform

**Version:** 2.0 (approved plan)
**Date:** 2026-08-14
**Author:** Kimi Code agent
**Inputs:** `docs/UK Electrician SaaS — Onboarding & AI Quote Capture Specification.md`, current `AGENTS.md`, codebase exploration.

---

## 1. Goal & high-level direction

Pivot the existing web-only platform to a **mobile-first iOS app** used by two profiles in one App Store binary:

| Profile | Primary need |
|---|---|
| **Tradesperson / business** | Onboard their electrical business, capture leads, review AI-drafted quotes, manage bookings, assign jobs, navigate to sites. |
| **Customer / homeowner** | Scan an electrician’s QR code, request a quote via a structured form, track status, accept quotes. |

The iOS app is a **single App Store binary** that white-labels itself per business (logo, colour, categories) at runtime. The existing React web app remains the desktop back-office companion.

For the MVP, **OCERP/BoQ is parked**: we stop deploying it and stop the data-pipeline scraper. The AI scope is reduced to a **JSON line-item interpreter** — it reads a completed `quote_request` (property profile, job answers, photos) and returns high-level estimated line items for the electrician to review/approve. This is faster to ship, cheaper to run, and still delivers the core value proposition: “AI drafts, humans send.”

---

## 2. Guiding principles (carried forward from the spec)

1. **Progressive profiling.** Launch gate = identity + compliance + services. Everything else is a post-launch checklist.
2. **Verify, don’t just collect.** CH/CPS/VAT/insurance verification flows are designed, even if some integrations start as async/manual.
3. **Structured first, media second, free text last.** Customer forms use cards, steppers, and visual pickers; free text is a fallback.
4. **Property age is the master variable.** Captured early and fed to the AI interpreter.
5. **Triage before quote.** Emergencies route to a call-back, never to a draft quote.
6. **AI drafts, humans send.** Every price is reviewed by the electrician before it reaches the customer.
7. **Single binary, runtime brandable.** No per-business App Store builds.

---

## 3. Milestones

## 3. Milestones

### 3.0 Current state — Interactive mock demo (no backend)

The immediate deliverable is a **fully offline, interactive mock version** of the iOS app for stakeholder demos and marketing. It lives under `services/pwa/` as an Expo React Native app. All state is local; there is no backend connection, no API calls, and no persistence.

**What is implemented today**
- Single App Store binary skeleton (`services/pwa/`) with two runtime profiles (trade / customer).
- Runtime white-label branding via mock business configs (`services/pwa/src/data/mockBusinesses.ts`): `demo` and `jenkins`.
- Trade onboarding stepper (Welcome → Account → Business identity → Compliance → Services → Review & launch).
- Customer quote request flow (postcode, contact, property, category, urgency, confirmation).
- Trade dashboard with Leads / Quotes / Calendar / Settings tabs.
- Mobile quote editor with Time & materials / Per point toggle and editable line items.
- Calendar week strip and job detail screen with navigation, call/message, team assignment, start/complete.
- Reset demo button in Settings.
- Web-renderable version so the flow can be screenshotted and shared without an iOS simulator.

**What is intentionally mocked / out of scope for this build**
- No real AI, no backend, no payments, no OCR/vision, no camera capture, no share extension, no Apple Maps, no push notifications.
- QR code entry, emergency triage call-back, and social-share-to-quote are shown in design docs but not yet wired in the interactive demo.

### 3.1 Marketable prototype

**Goal:** Use the interactive mock demo above to produce a design-led, narrated demo video that proves the new direction to stakeholders, prospective electricians, and investors. No production data or payments.

**Deliverables**
- The interactive mock app itself (`services/pwa/`) — runnable in a browser or iOS simulator.
- High-fidelity iOS screenshots in `services/pwa/demo-screenshots/` (regenerable) covering business onboarding, customer quote capture, tradesperson dashboard, quote editor, CRM and customer flows.
- Screenshot capture scripts (`services/pwa/scripts/capture-demo-screenshots.js`, `services/pwa/scripts/capture-customer-screenshots.js`) so the storyboard can be regenerated.
- Two marketing walkthrough videos — `services/pwa/demo-video/customer-journey.mp4` and `electrician-journey.mp4` — produced automatically by the video pipeline (`scripts/build-demo-videos.sh` → `record-demo-video.js` + `compose_demo_video.py`), with framed device chrome, timed captions and intro/outro cards. Narration script in `docs/demo-video-narration.md`.
- Backup static prototype exported to `docs/design/mocks/`.
- Stakeholder feedback form + summary.

**Success criteria**
- 5+ electricians can walk through the onboarding mocks and explain the AI handoff.
- 5+ homeowners can complete the quote-request storyboard without help.
- Stakeholders sign off on the mobile-first, white-label direction and OCERP/BoQ parking decision.

### 3.2 Beta Test Version

**Goal:** A real, installable iOS app used by a closed beta of electricians and their customers. AI produces draft line items; the electrician reviews before sending.

**Deliverables**
- iOS app (single binary, brandable) with onboarding, quote capture, dashboard, calendar, job assignment, Apple Maps navigation, and iOS Share Extension.
- Backend FastAPI extensions: new data model, onboarding/verification routers, quote requests, AI interpreter, jobs/appointments, share-to-quote extraction.
- Web app updates for settings/onboarding and quote-request review.
- Dev/staging Railway environment; local Docker stack without `ocerp` and `data-pipeline` scraper.

**Success criteria**
- 10–15 electricians complete onboarding and launch.
- 50+ customer quote requests submitted.
- 30%+ of AI drafts approved with no price change; 90%+ emergency triages met within SLA.
- Calendar bookings and job assignments used in the field; navigate-to-address used by every active electrician.
- No critical crashes in TestFlight.

### 3.3 MVP Go-live

**Goal:** Public App Store release, first paid electricians, production-grade trust and compliance.

**Deliverables**
- App Store submission and release.
- AI confidence routing, assumption highlighting, and feedback loop.
- Real-time verification badge refresh; insurance-renewal lifecycle hooks.
- Payments (Stripe/GoCardless), accounting (Xero/QB/FreeAgent), and calendar (Google/Outlook) integrations.
- Quote lifecycle: send, view, accept/reject, expiry, convert to job, simple invoice.
- Customer communications: email, SMS, WhatsApp Business opt-in.
- GDPR/PECR compliance, production monitoring, CI/CD, security hardening.

---

## 4. Architecture changes

### 4.1 App strategy: one binary, runtime white-label

| Decision | Choice | Rationale |
|---|---|---|
| Framework | **React Native with Expo** | Reuses TypeScript/React skills, web design system, and TanStack Query/Zustand patterns. Faster to beta than SwiftUI. |
| Single App Store build | Yes | Binary contains all UI code. Branding config (logo, colour, categories) is downloaded as JSON and applied at runtime. Allowed by App Store guidelines as long as no remote executable code is downloaded. |
| Role entry | Deep link / slug entry + login | `mytradeportal://quote?business=demo` or `demo.mytradeportal.co.uk/quote`. Trades users log in; customers enter the quote flow for that business. |
| Offline | Limited | Business onboarding is online-only. Customer quote form can queue photos/text if signal drops, then sync. |
| Theme | Light mode only at launch | Simplifies white-label colour checks; dark mode is post-MVP. |

Key components:

```
App shell
├── ThemeProvider (loads business config: logo, colour, fonts, template)
├── Auth context
│   ├── Trade login → business onboarding / dashboard
│   └── Customer entry → quote request flow / customer dashboard
├── Navigation
│   ├── OnboardingStack (A1–A14)
│   ├── QuoteCaptureStack (C1–C10)
│   ├── TradeTabNavigator (Leads, Quotes, Calendar, Settings)
│   └── CustomerTabNavigator (Requests, Messages, Profile)
├── Calendar module (week strip, day bookings, job assignment)
├── JobDetail module (customer, address, navigate, assign, start job)
├── ShareExtension module (iOS share intent → draft quote_request)
└── MediaCapture module (camera with guide overlays, HEIC→JPEG compression)
```

### 4.2 Backend changes

- **Extend the existing FastAPI service.** Add new routers; do not build a new backend.
- **Keep RLS / multi-tenancy.** The existing `tenant_id` mechanism stays; we map the spec’s `businesses` concept onto the current `tenants` table and add new satellite tables.
- **Deprecate OCERP/BoQ.** Stop the `ocerp` and `data-pipeline` containers in Compose and Railway; gate `use_ocerp`/BoQ endpoints in `services/api/app/routers/quotes.py`; keep source code for re-enable later.
- **Introduce `ai_quote_interpreter` module.** Calls OpenAI with a function/schema output to produce line items and confidence. No Qdrant required in the simple MVP.
- **Verification services.** Async worker pattern for Companies House, CPS register scraping, HMRC VAT validation.
- **Jobs & calendar.** Extend existing `Job`/`Appointment` models with `assigned_user_id`, status lifecycle, and calendar endpoints.
- **iOS integrations.** Share Extension target posts to a `/quote-requests/from-share` extraction endpoint; Apple Maps deep-link for navigation.
- **Media storage.** Reuse existing MinIO/S3 presigned URLs for photo/video/document uploads.

### 4.3 Data model migration

Keep `tenant_id` as the multi-tenant key. Add the following:

1. Extend `tenants`:
   - `status`: `onboarding | provisional | active | suspended`
   - `onboarding_progress`: JSONB checklist
   - `launched_at`, `year_established`, `structure`, `companies_house_number`, `ch_verified`, `nations_served`, `vat_registered`, `vat_number`, `quote_defaults`, `branding`
2. New tables:
   - `business_credentials`
   - `service_areas`
   - `business_services`
   - `pricing_profiles` + `pricing_rates`
   - `integrations`
   - `customers` (migrate from `contacts` over time)
   - `properties`
   - `quote_requests`
   - `media_assets`
   - `jobs` / `appointments`
   - `consents`
   - `events`
3. Update `users` roles to: `owner`, `admin`, `office_manager`, `engineer`.
4. Keep existing `quotes`/`quote_line_items`; add `quote_request_id`, `ai_metadata`, `reviewed_by`. `bill_of_quantities`/`boq_line_items` remain unused but are not dropped yet.

Phased migration:
- **Beta:** create new tables alongside existing ones; keep `contacts` working.
- **MVP go-live:** switch reads to new entities; deprecate old `contacts` UI.
- **Post-MVP:** decide whether to drop `bill_of_quantities`/`boq_line_items`.

---

## 5. Integration touch points with the existing backend

| Capability | What already exists | How we reuse / extend it |
|---|---|---|
| **Auth & sessions** | `services/api/app/security.py`, `/auth/login` cookie endpoint, `User` table with `tenant_id`, `TenantDep`. | Keep cookie-based auth for web. Add token/JWT session option for iOS. Add Apple/Google OAuth and customer-auth endpoints. |
| **Tenant / business identity** | `Tenant` model (`slug`, `name`, `settings` JSONB), `GET/PATCH /tenants/me`, `POST /tenants` (bootstrap). | Extend `Tenant.settings` for `onboarding_progress`, `branding`, `quote_defaults`, `status`. Add `/onboarding/*` endpoints and satellite tables. |
| **Users & roles** | `User` model with `admin`, `manager`, `technician`. | Align to `owner`, `admin`, `office_manager`, `engineer`. Add team-invite endpoints. |
| **Customers / contacts** | `Contact` model (`name`, `email`, `phone`, `address`, `postcode`). | Introduce `customers` + `properties` tables; dual-write or migrate during Beta. |
| **Quotes** | `Quote`, `QuoteLineItem`, `BillOfQuantities`, `BoQLineItem`; `/quotes` CRUD, send/approve/convert/PDF. | Reuse `Quote`/`QuoteLineItem`; add `quote_request_id`, `ai_metadata`, `reviewed_by`. Deprecate BoQ endpoints. Add explicit `/quotes/{id}/approve` and `/quotes/{id}/send`. |
| **Jobs / appointments** | `Job` and `Appointment` models already exist. | Extend with `assigned_user_id`, status lifecycle, address geocoding. Add `/jobs` and `/appointments` routers. |
| **Media uploads** | Files router (`/files/presigned-upload`) using MinIO/S3. | Reuse for `media_assets`. Add `/media` router. |
| **RLS & multi-tenancy** | `app.rls.set_tenant_in_session`, `TenantScopedBase`, Postgres RLS policies. | Keep identical mechanism for all new tenant-scoped tables. |
| **Audit & analytics** | `write_audit_log`, `Actions` enum. | Formalise append-only `events` table for analytics and audit. |
| **Email** | `app.email` (aiosmtplib). | Reuse for quote delivery and notifications; SMS/Twilio later. |
| **OCERP integration** | `services/api/app/clients/ocerp.py`, `/quotes/generate-boq`. | Gate / ignore for MVP. Keep source for re-enable. |

### New API endpoints required

| Area | Endpoint | Purpose |
|---|---|---|
| Onboarding | `POST /onboarding` `PATCH /onboarding/{step}` `GET /onboarding/status` | Progressive business onboarding, launch gate. |
| Verification | `POST /verifications/companies-house` `POST /verifications/cps` etc. | Async credential verification. |
| Customer | `POST /customers` `GET /customers/{id}` `POST /customers/{id}/properties` | Customer + property records. |
| Quote request | `POST /quote-requests` `GET /quote-requests` `POST /quote-requests/{id}/media` | Capture and triage. |
| AI interpreter | `POST /ai/interpret-quote` | Returns draft line items + confidence. |
| Quotes | `POST /quotes/{id}/approve` `POST /quotes/{id}/send` | Explicit human handoff. |
| Jobs / calendar | `POST /jobs` `GET /jobs` `PATCH /jobs/{id}/assign` `PATCH /jobs/{id}/status` | Scheduling and assignment. |
| Share extension | `POST /quote-requests/from-share` | Extract details from forwarded message text/photos. |
| Business config | `GET /businesses/{slug}/public-config` | White-label logo, colour, categories (public, no auth). |

---

## 6. Backend work by phase

### 6.1 Beta Test Version

| Work stream | Tasks |
|---|---|
| **Schema & migrations** | Extend `tenants`; create `business_credentials`, `service_areas`, `business_services`, `pricing_profiles`/`pricing_rates`, `integrations`, `customers`, `properties`, `quote_requests`, `media_assets`, `jobs`, `appointments`, `consents`, `events`. Add RLS policies. |
| **Auth** | Apple/Google OAuth; customer sign-up/login; password reset; token/session handling for iOS. |
| **Onboarding API** | Progressive onboarding endpoints, launch-gate calculation, verification status tracking. |
| **Verification integrations** | Companies House sync; CPS register async check (with manual fallback); VAT checksum; insurance upload + expiry tracking. |
| **Quote capture API** | `quote_requests` CRUD, EPC/geocode enrichment, media upload, triage rules, customer consent recording. |
| **AI interpreter** | Pydantic output schema, OpenAI function-calling prompt, confidence/assumptions routing. |
| **Quote approval / send** | Reuse `Quote`/`QuoteLineItem`; add `ai_metadata`, `reviewed_by`; implement approve & send endpoints. |
| **Jobs & calendar** | Extend existing `Job`/`Appointment` models; assignment endpoints; status lifecycle; calendar read API. |
| **iOS integrations** | Public business-config endpoint; `/quote-requests/from-share` extraction endpoint; presigned media upload endpoint. |
| **Push notifications** | APNs/Firebase integration for emergency triage, quote received, job assigned. |
| **Infra / deprecation** | Remove `ocerp` and `data-pipeline` from Compose/Railway; gate old BoQ endpoints; update CI to skip OCERP/data-pipeline tests by default. |

### 6.2 MVP Go-live

| Work stream | Tasks |
|---|---|
| **Payments** | Stripe / GoCardless OAuth connect; deposit collection on quote acceptance; webhook handlers. |
| **Accounting** | Xero / QuickBooks / FreeAgent OAuth; invoice sync. |
| **Calendar sync** | Google / Outlook OAuth; two-way availability sync for quote-request preferred dates. |
| **AI confidence routing** | 0.85+ / 0.60–0.85 / <0.60 / site-visit routes; assumption highlighting UI; feedback loop on `ai_metadata`. |
| **Insurance lifecycle** | Renewal reminders; badge refresh; lapsed-lock logic. |
| **Customer communications** | Email templates; SMS via Twilio; WhatsApp Business opt-in and message sending. |
| **Analytics** | Aggregate events into KPIs; retention funnel; quote acceptance metrics. |
| **GDPR / security** | Granular consent export/erasure; data retention policies; rate limiting; security review. |
| **Production hardening** | App Store submission assets; CI/CD production smoke tests; monitoring; incident runbooks. |

---

## 7. AI quote interpreter (MVP scope)

Input: `quote_request` JSON (property, job answers, urgency, media labels) + business `pricing_profile`.

Output schema:

```json
{
  "confidence": 0.78,
  "route": "draft_with_assumptions",
  "assumptions": ["Assumed stud/plasterboard walls", "Assumed consumer unit accessible"],
  "line_items": [
    {"kind": "labour", "description": "Consumer unit replacement - 6-8 circuits", "qty": 1, "unit": "job", "unit_price": 520.00},
    {"kind": "materials", "description": "Metal 12-way RCBO board + extras", "qty": 1, "unit": "job", "unit_price": 180.00},
    {"kind": "callout", "description": "Call-out fee", "qty": 1, "unit": "item", "unit_price": 45.00}
  ],
  "callout_fee": 45.00,
  "minimum_charge": 95.00,
  "emergency_multiplier": 1.0,
  "compliance_notes": ["Part P self-certification included"]
}
```

- Uses OpenAI function calling / structured output with a Pydantic schema.
- Prompt includes the business’s labour model, rates, markup, base prices, travel rule, and emergency multiplier.
- If confidence < 0.60 or red flags present, returns `route: site_visit_needed` with a scoping checklist instead of line items.
- Every AI-generated line item is flagged (`ai_generated=true`) and reviewed by a human before it becomes a sent quote.

---

## 8. Detailed demo plan — Milestone 1: Marketable prototype

### 8.1 Goal

Use the **interactive mock iOS app** to produce a 3-minute narrated demo video that proves the new mobile-first direction to stakeholders, prospective electricians, and investors. No working backend is needed; the demo is fully offline.

### 8.2 Audience

- 5+ UK electricians (prospective beta users).
- 5+ homeowners (prospective customers).
- Internal stakeholders / investors.

### 8.3 Running the interactive mock

The mock app is an Expo React Native project under `services/pwa/`. It can be run in a browser for quick screenshots, or on an iOS simulator/device once Xcode / Expo Go is available.

**Quick web run (for screenshots / sharing)**

```bash
cd services/pwa
pnpm install
npx expo start --web
# open http://localhost:8081 in a mobile-sized viewport
```

**iOS simulator / device**

```bash
cd services/pwa
pnpm install
npx expo start --ios
# or scan the QR code with Expo Go on a physical device
```

**Regenerate demo screenshots**

```bash
# Terminal 1: start the web server
cd services/pwa && npx expo start --web

# Terminal 2: capture the trade and customer storyboards
node services/pwa/scripts/capture-demo-screenshots.js
node services/pwa/scripts/capture-customer-screenshots.js
```

Captured PNGs land in `services/pwa/demo-screenshots/`.

**Reset the demo**

Tap **Settings → Reset demo** to return to the entry screen. No data is persisted.

### 8.4 Storyboard (3 minutes)

| Time | Scene | Screenshot asset |
|---|---|---|
| 0:00–0:10 | **Hook.** One app, two profiles. Enter a business code to see a branded experience. | `01-entry.png`, `02-business-selected.png` |
| 0:10–0:45 | **Business onboarding.** Welcome → account → identity → compliance → services → review & launch. Emphasise the 6-step launch gate and trust badges. | `03-onboarding-welcome.png` → `08-onboarding-review.png` |
| 0:45–1:20 | **Customer quote request.** Homeowner enters postcode, contact, property, job type, urgency, and submits. | `22-customer-dashboard.png` → `29-customer-dashboard.png` |
| 1:20–2:00 | **AI draft & human approval.** Lead appears on the trade dashboard. Electrician opens the quote editor, toggles Time & materials ↔ Per point, reviews line items. | `09-trade-dashboard.png`, `10-quote-edit.png`, `11-quote-edit-per-point.png` |
| 2:00–2:35 | **Scheduling & navigation.** Job appears in the calendar; electrician opens job detail, sees customer, address, team assignment, and navigate action. | `12-calendar.png`, `13-job-detail.png` |
| 2:35–3:00 | **White-label close.** Same binary, different business branding. “One app, every electrician’s brand.” Mention `jenkins` business code for second brand. | `01-entry.png` + `02-business-selected.png` |

### 8.5 Demo video assembly

The demo videos are now produced **automatically** — no manual editing required:

```bash
services/pwa/scripts/build-demo-videos.sh all
```

This records each journey through the live Expo web build with Playwright and
composites a framed, captioned MP4 (with intro/outro cards) via ffmpeg. Output
lands in `services/pwa/demo-video/`. See
[`services/pwa/demo-video/README.md`](../services/pwa/demo-video/README.md) and
`docs/demo-video-narration.md` for the voiceover script.

The manual alternative (for a bespoke marketing cut) remains:

1. Export the PNGs from `services/pwa/demo-screenshots/`.
2. In Loom, ScreenPal, Keynote, or Canva, create a 390 × 844 phone frame and sequence the screenshots with a 0.5s Ken Burns pan/zoom and captions.
3. Record narration following the storyboard above.
4. End with a QR code / call-to-action for beta sign-up.

### 8.6 Deliverables

1. **Marketing walkthrough videos** — `services/pwa/demo-video/customer-journey.mp4` and `electrician-journey.mp4`, regenerated by `scripts/build-demo-videos.sh`; narration in `docs/demo-video-narration.md`.
2. **Interactive Expo mock** runnable in browser or iOS simulator.
3. **Screenshot set** in `services/pwa/demo-screenshots/` (regenerable via scripts).
4. **Stakeholder feedback form** with 5 questions:
   - Can you describe the app’s main value in one sentence?
   - Which screen was most confusing?
   - Would you download this app as a customer?
   - Would you onboard your business on this app?
   - What is missing before you would pay for it?

### 8.7 Success criteria

- 5+ electricians can explain the onboarding flow and the AI handoff without help.
- 5+ homeowners can complete the quote-request storyboard without asking what to do next.
- Stakeholders sign off on the mobile-first, white-label direction and OCERP/BoQ parking decision.
- Feedback form yields ≤2 major open questions that need design iteration before Beta build starts.

### 8.8 Screenshot asset index

Trade flow (`services/pwa/demo-screenshots/0*.png`):

| File | Screen |
|---|---|
| `01-entry.png` | Business code lookup |
| `02-business-selected.png` | Business found, choose profile |
| `03-onboarding-welcome.png` | A1 Welcome / value proposition |
| `04-onboarding-account.png` | A2 Account creation |
| `05-onboarding-identity.png` | A3 Business identity |
| `06-onboarding-compliance.png` | A6 Compliance & credentials |
| `07-onboarding-services.png` | A8 Services offered |
| `08-onboarding-review.png` | A14 Review & launch |
| `09-trade-dashboard.png` | Trade dashboard (Leads default when leads exist) |
| `10-quote-edit.png` | Review AI quote — Time & materials |
| `11-quote-edit-per-point.png` | Review AI quote — Per point |
| `12-calendar.png` | Calendar of bookings |
| `13-job-detail.png` | Job detail & assignment |

Customer flow (`services/pwa/demo-screenshots/2*.png`):

| File | Screen |
|---|---|
| `21-customer-entry.png` | Customer entry / business selected |
| `22-customer-dashboard.png` | Customer dashboard / My quotes |
| `23-customer-postcode.png` | C1 Entry & postcode |
| `24-customer-contact.png` | C2 Contact |
| `25-customer-property.png` | C3 Property profile |
| `26-customer-category.png` | C4 Job category picker |
| `27-customer-urgency.png` | C7 Timing & urgency |
| `28-customer-confirmation.png` | C10 Confirmation |
| `29-customer-dashboard.png` | Customer dashboard after submission |

---

## 9. Sequenced delivery roadmap

| Week | Theme | Key deliverables |
|---|---|---|
| 1–2 | **Marketable prototype** | Design lock, demo video, stakeholder sign-off. |
| 3–4 | **Foundation** | New data model migrations, API stubs, Expo app shell, theming, auth. |
| 5–6 | **Business onboarding** | A1–A14 screens, launch gate, verification integrations, post-launch checklist. |
| 7–8 | **Customer quote capture** | C1–C10 forms, media capture, triage rules, save-and-resume, QR code entry. |
| 9 | **AI interpreter** | Prompt/schema, line-item output, confidence routing. |
| 10 | **Dashboards & handoff** | Trade leads/drafts/approve-send; customer status dashboard. |
| 11 | **Calendar & job assignment** | Calendar of bookings, job detail, user assignment, Apple Maps navigation. |
| 12 | **iOS integrations** | Share Extension / App Intent from SMS/WhatsApp/social media → draft quote request; push notifications. |
| 13–14 | **Beta hardening** | Payments skeleton, analytics, TestFlight, 15 beta electricians. |
| 15–16 | **MVP Go-live** | App Store submission, security review, GDPR docs, production smoke tests, launch. |

---

## 10. OCERP / BoQ / data-pipeline deprecation

> **Implementation status:** OCERP/BoQ is parked — commented out in
> `docker-compose.yml` and `.railway/railway.ts`, with the BoQ endpoints
> gated (HTTP 501) in `services/api/app/routers/quotes.py`. The
> `data-pipeline` service is **still wired** in Compose and Railway; parking
> the scheduled scraper is the remaining action in the table below.

| Asset | Action |
|---|---|
| `services/ocerp/` source | **Keep.** Do not delete. Mark as parked in `AGENTS.md`. |
| `docker-compose.yml` | Remove `ocerp` and `data-pipeline` services. Keep Postgres/Redis/MinIO. |
| `.railway/railway.ts` | Remove `ocerp` and `dataPipeline` services; remove `OCERP_URL` env var. |
| `services/api/app/routers/quotes.py` | Default `use_ocerp=false`; 410-gate `/quotes/generate-boq`; hide BoQ review endpoints. |
| `services/api/app/clients/ocerp.py` | Keep but do not call. |
| `packages/shared/py/mtp_shared/ocerp.py` | Keep contracts for re-enable. |
| `services/data-pipeline/` source | Keep. Stop scheduled scraping. Optionally keep `knowledge_loader` for compliance context. |
| `bill_of_quantities` / `boq_line_items` tables | Leave in DB, unused. Drop after the pivot is proven. |
| CI | Scope pytest to `services/api/tests` and required paths; exclude `services/ocerp/tests` and `services/data-pipeline/tests` from default CI. |
| Docs | Update `AGENTS.md`, `docs/ai-quote-engine.md`, `docs/deployment.md` to reflect parked OCERP and active AI interpreter. |

---

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| White-label single binary rejected by App Store | High | Static code + remote config only (no remote JS); prepare fallback web/PWA quote form. |
| AI estimates are too inaccurate to approve | High | Start with high-confidence templates; always route low confidence to site visit; tight feedback loop per quote. |
| Verification integrations (CH/CPS) are flaky | Medium | Build async/manual review fallback; badge “verified” vs “self-declared”. |
| Existing web app drift while building mobile app | Medium | Share design system where possible; schedule web dashboard updates in each milestone. |
| Schema migration is large and risky | Medium | New tables alongside old; dual-write period; no destructive migrations until MVP. |
| Team bandwidth too thin for Expo + backend + design | High | Sequenced milestones let design/frontend/backend work in parallel; defer non-MVP features. |

---

## 12. Definition of done for Task 1

- [x] Migration plan written and stored in `docs/pivot-migration-plan.md`.
- [x] Design specification for onboarding + dashboards written in `docs/design/ios-onboarding-dashboard-mocks.md`.
- [x] High-fidelity static mock assets generated and referenced in the design doc.
- [x] Interactive offline mock app implemented under `services/pwa/`:
  - Entry screen with runtime white-label business selection (`demo`, `jenkins`).
  - Trade onboarding stepper (A1–A14 launch-gate subset).
  - Customer quote request flow (C1–C10 core steps).
  - Trade dashboard with leads, quote editor (Time & materials / Per point), calendar, job detail.
  - Reset demo button in Settings.
- [x] Demo screenshot capture scripts and PNGs in `services/pwa/demo-screenshots/`.
- [x] Automated marketing videos (`services/pwa/demo-video/{customer,electrician}-journey.mp4`) with capture/compose pipeline and narration script.
- [x] Integration touch points, Beta/MVP backend work, and Milestone 1 demo plan documented.
- [ ] Stakeholder review and approval (external to this agent).

---

## 13. Next steps after plan approval

1. ~~Produce narrated demo video~~ — done: automated `customer`/`electrician` journey videos in `services/pwa/demo-video/` (record narration over them using `docs/demo-video-narration.md`).
2. Run stakeholder feedback sessions with the interactive mock.
3. Move to Beta build: Alembic migrations for the new data model, business onboarding API, auth, quote requests, AI interpreter, jobs/calendar endpoints.
4. Finish OCERP/BoQ deprecation (done) and park the `data-pipeline` scraper in Compose/Railway (pending).
5. Begin iOS Share Extension, camera media capture, and Apple Maps navigation once the core backend is in place.
