# Beta PRD — My Trade Portal Mobile (iOS)

> **Status (2026-09-20): shipped.** Every iteration below is complete and the
> October 2026 beta cohort is live; this document is kept as the historical
> spec. `docs/beta-test-plan.md` is the current verification map, and
> `AGENTS.md` documents the architecture as built. Two statements in this PRD
> did not survive implementation: **demo mode was removed entirely** (connected
> mode is the only runtime mode — the `owner@demo.trade` account is a real
> seeded user, not a client-side mock), and **real payments did ship** —
> Stripe Connect destination charges for customer→tradesperson invoices plus
> Paddle for the platform subscription (see `docs/payments-model.md`).

> Product Requirements Document for the closed Beta of the white-label electrician
> field-service app. Goal: a single iOS app that brands per tenant, supports
> separate electrician and customer logins, and is fully integrated with the
> existing FastAPI backend, Supabase auth, PostgreSQL data, and the **Kimi API**
> AI layer.

## 1. Beta goal

Ship a working Beta of the React Native + Expo iOS app that:

1. Runs as a **multi-tenant white-label** app, themed from a business's public
   tenant config fetched on launch.
2. Supports **two distinct authenticated roles** in the same binary:
   - **Electrician / trade user** — onboard a business, manage quotes, jobs,
     invoices, calendar, and chat with customers.
   - **Homeowner / customer** — request quotes, view quotes, accept/reject,
     book appointments, and chat with the electrician.
3. Is **fully backend-integrated** in "connected" mode (`EXPO_PUBLIC_API_BASE_URL`
   set). Demo mode to be deprecated.
   Beta acceptance requires connected mode to work end-to-end.
4. Delivers the **two approved Beta AI features**, both powered by the
   **Kimi API**:
   - Quote Agent — AI draft quote generation from job details + natural language
     for trade review and edit. Triggered when a customer submits a quote request
     or when a tradesperson generates a quote.
   - Lead Triage Agent — AI clarifying chat that follows up with the customer
     after a quote request is submitted and before it reaches the electrician,
     to improve quote accuracy.

## 2. Scope boundaries

### 2.1 In scope for Beta

- White-label tenant branding (logo, primary colour, business name, services).
- Trade onboarding wizard (account, business identity, compliance, services,
  review & launch) persisted to the backend.
- Trade login via Supabase-backed bearer token (`POST /auth/token`).
- Customer registration and login against a tenant (`POST /customer/register`,
  `POST /customer/login`).
- Customer quote request capture flow (branched questionnaires, triage,
  media, consent) submitted to `POST /businesses/{slug}/quote-requests`.
- Trade quote management: view leads/quote requests, generate AI draft quote,
  edit line items, approve, send, convert to invoice.
- Trade job & calendar management: view scheduled jobs, start/complete, day/week
  calendar views.
- Trade invoice management: view invoices, mark paid, convert from quote/job.
- In-app chat thread between customer and trade user tied to a quote request or
  quote.
- AI quote generation using the existing backend `/quotes/generate` endpoint,
  routed through the **Kimi API**, returning editable guide-priced line items
  (the OCERP/BoQ path stays disabled).
- AI customer follow-up chat using a new lightweight backend endpoint that
  persists messages and asks clarifying questions.

### 2.2 Explicitly out of scope for Beta

- Voice-to-quote, voice-to-cert, voice transcription.
- Dashboard AI insights / sparkles banner.
- OCERP / Bill of Quantities (BoQ) generation (`/quotes/generate-boq` stays 501).
- Real-time GPS tracking, route optimisation, engineer dispatch.
- Native calendar sync (Apple/Google Calendar) — in-app calendar only.
- Real payments capture / Stripe GoCardless checkout.
- Companies House, CPS, HMRC verification APIs (self-declared badges).
- Web app parity changes (web/app remains in its current state; mobile is the
  Beta focus).

## 3. Key assumptions

- The existing FastAPI backend (`services/api`) is the source of
  truth for auth, data, and AI. No new mobile-specific API will be created.
- **AI layer:** both the Quote Agent and Lead Triage Agent are backed by the
  **Kimi API** via the existing provider-agnostic LLM routing in the backend
  (`LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`).
- Supabase auth remains the credential provider; local bcrypt fallback stays
  for dev/test only.
- The app supports one runtime mode:
  - **Connected mode** — real backend, required for Beta acceptance.
  - **Demo mode** — is deprecated

## 4. Architecture and integration

### 4.1 Mobile app layers

```
┌─────────────────────────────────────────────┐
│  mobile/ React Native + Expo iOS app          │
│  - screens/  (trade, customer, onboarding)   │
│  - api/      (NEW/RESTORED client layer)     │
│  - lib/      (apiClient, config, tokenStorage)│
│  - stores/   (Zustand auth + business theme)  │
└──────────────────┬──────────────────────────┘
                   │ HTTP / Bearer + X-Tenant-ID
┌──────────────────▼──────────────────────────┐
│  services/api FastAPI backend (restore/use)   │
│  - auth (Supabase + JWT)                      │
│  - routers: tenants, businesses, quote-       │
│    requests, quotes, jobs, appointments,      │
│    invoices, communications, analytics        │
│  - rag: generate_quote_from_prompt (Kimi API)   │
│  - postgres + qdrant + redis infra            │
└─────────────────────────────────────────────┘
```

## 5. Feature specifications

### 5.1 White-label tenant branding

- On app launch in connected mode, if `EXPO_PUBLIC_BUSINESS_SLUG` is set, call
  `GET /businesses/{slug}/public-config` (no auth) and store the resulting
  `BusinessConfig` in `businessStore`.
- Apply logo URL, primary colour, secondary colour, business name, and enabled
  service categories to the entry screen, quote flow, and customer portal.
- If no slug is configured, show a generic marketplace entry with a code/slug
  input to resolve a tenant.

### 5.2 Trade onboarding & login

- Entry screen offers "Register my business" and "Trade login".
- Registration wizard collects: account owner details, business identity,
  address & service area, tax/VAT, compliance & credentials, services offered,
  review & launch.
- Connected mode with `EXPO_PUBLIC_SETUP_TOKEN`: provision tenant via
  `POST /tenants`, authenticate, record onboarding steps, and call
  `POST /onboarding/launch`.
- Trade login calls `POST /auth/token` with tenant slug and stores the JWT in
  `expo-secure-store`.
- Demo mode keeps pre-filled credentials (`owner@demo.trade` / `demo123`) for
  screenshots.

### 5.3 Customer onboarding & login

- Customer landing page is branded by the tenant.
- Customer can request a quote as a guest or create an account.
- Registration calls `POST /customer/register` with full name, phone, email,
  password, address, and preferred contact method.
- Login calls `POST /customer/login`.
- Bearer token is stored the same way as trade tokens; the backend distinguishes
  customers via `subject_type="customer"` claims.

### 5.4 Quote management (trade)

- **Leads list**: `GET /quote-requests` mapped to the app's `Lead` type,
  sorted by urgency, with New / Flagged filters.
- **Lead detail**: shows captured property details, questionnaire answers, photos,
  customer contact. Actions: Generate AI quote, Request more info (opens chat),
  Mark dead.
- **AI quote generation**: `POST` with `quote_request_id` and
  optional extra description. The backend returns a draft quote with guide-priced
  line items.
- **Quote edit**: review and edit line items (description, qty, unit price),
  switch between labour/materials and per-point pricing models where supported,
  view subtotal/VAT/total.
- **Quote lifecycle**: Approve & send (`POST /quotes/{id}/send`), accept/reject
  actions are customer-facing but trade can view status.
- **Convert to invoice**: `POST /quotes/{id}/convert-to-invoice`.

### 5.5 Job, calendar & invoice management (trade)

- **Jobs list / calendar**: `GET /jobs` mapped to the app's `Job` type; day and
  week calendar views.
- **Job detail**: view scheduled date/time, customer, address. Actions: call,
  message, navigate, start (`POST /jobs/{id}/start`), complete
  (`POST /jobs/{id}/complete`), create invoice.
- **Invoices list**: `GET /invoices`; status badges (draft, sent, paid,
  overdue).
- **Invoice detail**: view line items, total, due date. Actions: mark paid
  (`POST /invoices/{id}/mark-paid`).

### 5.6 Customer portal

- **My requests / quotes**: `GET /customer/quote-requests` shows quote
  requests and linked quotes. Cards show status (awaiting review, open,
  accepted, rejected).
- **Quote detail**: view line items, assumptions, totals, validity. Actions:
  Accept quote → book date/time; Reject quote → optional reason; Request changes
  → opens chat.
- **Calendar**: `GET /appointments` (or filtered jobs) shows booked dates.
- **Profile**: load and edit name, phone, email, addresses, communication
  preferences.
- **Messages**: opens chat thread with the business.

### 5.7 In-app chat

- A chat thread is associated with a `quote_request_id` (and optionally a
  `quote_id`).
- Backend: add a small chat router or extend `/communications` with
  thread-scoped messages that include `quote_request_id` and `sender_role`
  (`customer` | `business`).
- Mobile:
  - Customer `MessagesScreen` loads the thread for their open quote request and
    allows free-text replies.
  - Trade user can open the same thread from lead detail or quote detail.
  - Messages are persisted in the backend `communications` table and surfaced
    via polling in Beta (real-time is post-Beta).
- The AI assistant participates in the customer thread as `sender_role="ai"`
  when asking clarifying questions.

### 5.8 AI quote generation (trade)

- Triggered from lead detail or quote intake screen.
- Mobile sends the quote request id and any free-text notes to
  `POST /quotes/generate`.
- Backend (already implemented in `f4c0e02`): uses form/structured data + free
  text, optional Qdrant catalogue retrieval, and a **Kimi API** call to return
  line items with guide prices for labour and materials.
- The electrician reviews the draft in the quote edit screen. Pricing is
  explicitly editable; accuracy is a starting point, not a guarantee.
- Catalogue match is optional; the LLM always returns editable line items.

### 5.9 AI customer follow-up chat

- After a homeowner submits a quote request, the app opens (or prompts to open)
  the chat thread.
- Backend: add `POST /communications/{quote_request_id}/ai-followup` that:
  - Reads the quote request and any prior messages.
  - Calls the **Kimi API** with a prompt to ask one clarifying question at a
    time.
  - Persists the assistant message to the thread.
- Mobile displays the assistant message and suggested reply chips; free-text
  replies are also allowed. Each customer reply is persisted and can trigger
  the next follow-up question.
- The collected answers are included when the trade user later generates an AI
  quote for the same quote request.

## 6. Backend contract map

The mobile app consumes the following existing backend endpoints. No new
mobile-specific endpoints are required except for chat.

| Mobile feature | Backend endpoint(s) |
|---|---|
| Public tenant branding | `GET /businesses/{slug}/public-config` |
| Trade login | `POST /auth/token` |
| Customer register/login | `POST /customer/register`, `POST /customer/login` |
| Tenant provisioning | `POST /tenants`, `PATCH /onboarding/step/{step}`, `POST /onboarding/launch` |
| Public quote request | `POST /businesses/{slug}/quote-requests` |
| Trade leads | `GET /quote-requests`, `GET /quote-requests/{id}` |
| Customer history | `GET /customer/quote-requests` |
| AI draft quote | `POST /quotes/generate` |
| Quote lifecycle | `GET /quotes`, `GET /quotes/{id}`, `POST /quotes/{id}/send`, `POST /quotes/{id}/approve`, `POST /quotes/{id}/convert-to-invoice` |
| Jobs / calendar | `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/start`, `POST /jobs/{id}/complete` |
| Appointments | `GET /appointments` |
| Invoices | `GET /invoices`, `GET /invoices/{id}`, `POST /invoices`, `POST /invoices/{id}/mark-paid` |
| Dashboard KPIs | `GET /analytics/dashboard` |
| Chat messages | `GET /communications` (filtered), `POST /communications`, `POST /communications/{quote_request_id}/ai-followup` (NEW) |

## 7. Data flow examples

### 7.1 Customer requests a quote → AI follow-up → trade AI quote

1. Customer enters tenant slug/code; app fetches public config and themes.
2. Customer completes quote request wizard and submits to
   `POST /businesses/{slug}/quote-requests`.
3. App notifies customer of chat message, customer opens chat thread; backend posts first AI clarifying question via
   `POST /communications/{quote_request_id}/ai-followup`.
4. Customer answers; answers are persisted as `communications` rows.
5. App calls `POST /quotes/generate` with
   the quote request id. The backend prompt includes structured data + chat
   history.
6. AI returns guide-priced line items; stored for trade edits and approval.
7. Trade user logs in, sees lead in `GET /quote-requests`.
8. Trade reviews generate quote, edits accordingly.
9. Trade sends quote; customer sees it in their history, accepts, and books a
   date.

### 7.2 Quote accepted → job → invoice

1. Customer accepts quote via customer quote detail; app creates an appointment
   (`POST /appointments` or updates quote/job status).
2. Job appears in trade calendar via `GET /jobs`.
3. Trade starts and completes job via job lifecycle endpoints.
4. Trade creates invoice from job/quote via `POST /invoices` and sends it.
5. Invoice appears in invoices list; payment status tracked via
   `POST /invoices/{id}/mark-paid`.

## 8. Acceptance criteria

### 8.1 Functional

- [ ] Connected mode builds and type-checks with no missing `mobile/src/api/*`
      imports.
- [ ] A trade user can complete onboarding, log in, view leads, generate an AI
      quote, edit line items, send it, convert to invoice, and mark paid.
- [ ] A customer can enter a tenant code, submit a quote request, receive AI
      follow-up questions, view the sent quote, accept it, and book a date.
- [ ] Customer and trade user can exchange messages in a thread tied to a
      quote request.
- [ ] White-label branding (logo, colour, name) is applied to entry screen,
      quote request flow, and customer portal.
- [ ] Demo mode still works for screenshots when no API base URL is configured.

### 8.2 Non-functional

- [ ] All backend calls in connected mode use Bearer token + `X-Tenant-ID`.
- [ ] JWT tokens are stored in `expo-secure-store` and cleared on logout.
- [ ] Customer tokens cannot access trade-only endpoints (enforced by backend
      `subject_type` claims).
- [ ] Rate limits are respected (`/auth/*` 5/min, `/quotes/generate` 10/min per
      tenant).
- [ ] AI quote generation returns non-empty draft line items for common
      electrical jobs (consumer unit, EV charger, EICR, additional sockets).

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `services/api` is deleted from the working tree | Restore from git history (`f4c0e02` or later). The backend is the Beta source of truth. |
| `mobile/src/api/` is missing, breaking imports | Recreate the API client layer using the prior `services/pwa/src/api/` files as a template. |
| Mobile and backend type/shape drift | Reconcile the app's `Quote`, `Job`, `Invoice`, `Lead` types against current backend `schemas.py`. |
| AI quote generation returns empty results | Already fixed in `f4c0e02` by removing the catalogue-lock; verify with end-to-end tests. |
| Chat persistence model is basic | Extend the existing `Communication` model with `quote_request_id` and `sender_role` columns. |

## 10. Deliverables for Beta

1. Restored/working `services/api` backend in the working tree.
2. Restored/created `mobile/src/api/*` client modules.
3. Wired mobile screens using real backend data in connected mode.
4. New backend chat endpoints and updated `Communication` model.
5. New mobile chat UI replacing the scripted `MessagesScreen` Q&A.
6. End-to-end smoke tests for the critical flows above.
7. Updated Beta PRD document committed to `docs/prd-beta.md`.

## 11. Out of scope recap

- Voice features, dashboard AI insights, OCERP/BoQ.
- Web app changes.
- Real payment processing.
- Native calendar/contact integrations.
- Real-time chat (WebSockets / Supabase realtime) — polling is sufficient for
  Beta.

## 12. Implementation roadmap

The Beta is delivered through sequential iterations. Each iteration produces a
working, testable slice and builds on the previous one. Do not start an
iteration until the prior one is merged and passing its acceptance checks.

### Iteration 0 — Restore backend and local infrastructure

**Goal:** have a runnable FastAPI backend and mobile app that type-checks.

- Restore `services/api` from git history (`f4c0e02` or later) to the working tree.
- Reconcile root config (`docker-compose.yml`, `pnpm-workspace.yaml`,
  `pyproject.toml`, `conftest.py`) so the backend builds and tests run.
- Start local infrastructure: PostgreSQL, Redis, Qdrant, MinIO, Mailpit.
- Run backend migrations/RLS setup and confirm `pytest` passes.
- Add Kimi API environment variables to `.env.example`:
  `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TEMPERATURE`,
  `EMBEDDING_API_BASE`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`.
- Verify `pnpm install` works across `mobile/`, `web/app/`, and shared packages.

**Definition of done:** `docker compose up -d postgres redis qdrant minio mailpit`
starts, backend tests pass, and `cd mobile && pnpm lint` reaches the current
compiler errors (not import-resolution crashes).

### Iteration 1 — Mobile API client layer

**Goal:** replace every broken `../../api/*` import with a working client module.

- Port/adapt the prior `services/pwa/src/api/`
  modules: `auth.ts`, `businesses.ts`, `onboarding.ts`, `quoteRequests.ts`,
  `quotes.ts`, `jobs.ts`, `invoices.ts`, `analytics.ts`, and a stub
  `communications.ts`.
- Update screen imports to use the modules.
- Add TanStack Query provider to `app/_layout.tsx` if not already present.
- Reconcile mobile `Quote`, `Job`, `Invoice`, `Lead`, and `BusinessConfig` types
  with backend `schemas.py`.
- Ensure demo mode still works when `EXPO_PUBLIC_API_BASE_URL` is unset.

**Definition of done:** `cd mobile && pnpm lint` passes with no unresolved
`../../api/*` imports.

### Iteration 2 — White-label tenant branding

**Goal:** the app themes itself from a live tenant config.

- Backend: confirm `GET /businesses/{slug}/public-config` returns logo, colours,
  name, services, contact phone, and address.
- Mobile: on launch, fetch public config when `EXPO_PUBLIC_BUSINESS_SLUG` is set
  and store it in `businessStore`.
- Apply branding to `EntryScreen`, customer quote request flow, and customer
  portal header.
- Add a generic marketplace entry screen that lets the user type a slug/code when
  no `EXPO_PUBLIC_BUSINESS_SLUG` is configured.

**Definition of done:** changing `EXPO_PUBLIC_BUSINESS_SLUG` visibly changes the
app's entry screen branding in the iOS Simulator.

### Iteration 3 — Authentication for both roles

**Goal:** real trade and customer login/registration against the backend.

- Trade login: wire `POST /auth/token` with tenant slug; store JWT + tenant id in
  `expo-secure-store`.
- Customer registration: wire `POST /customer/register` with address and
  preferred contact fields.
- Customer login: wire `POST /customer/login`.
- Logout clears tokens and returns to the entry screen.
- Remove or gate demo pre-filled credentials so they do not appear in Beta builds.

**Definition of done:** a trade user and a customer can each register, log in,
and log out in connected mode against a local backend.

### Iteration 4 — Customer quote request → trade leads

**Goal:** a homeowner can submit a quote request and the electrician can see it
as a lead.

- Wire `POST /businesses/{slug}/quote-requests` from the customer quote request
  wizard.
- Wire `GET /quote-requests` and `GET /quote-requests/{id}` to the trade
  `LeadsScreen` and `LeadDetailScreen`.
- Map backend quote-request status to the app's `Lead` status badges.
- Preserve demo fallback for offline screenshots only.

**Definition of done:** submitting a quote request as a customer creates a lead
that appears in the trade user's leads list within seconds.

### Iteration 5 — Quote Agent (AI draft quotes)

**Goal:** the electrician can generate, edit, and send an AI draft quote.

- Wire `POST /quotes/generate` with `quote_request_id` and optional free-text
  notes, routed through the Kimi API.
- Display returned line items in `QuoteEditScreen`; allow edit of description,
  quantity, and unit price.
- Wire `POST /quotes/{id}/send` and update the quote status.
- Customer can view the sent quote in their requests/quotes list.
- Validate that Kimi returns non-empty line items for the Beta demo categories.

**Definition of done:** a trade user taps "Generate AI quote" on a lead, reviews
and edits the draft, sends it, and the customer sees the quote.

### Iteration 6 — Customer quote lifecycle and booking

**Goal:** the homeowner can accept/reject a quote and book an appointment.

- Wire customer quote detail from `GET /customer/quote-requests` (including the
  linked quote and line items).
- Implement accept quote and reject quote actions.
- After acceptance, show date/time booking UI and persist the appointment via
  `POST /appointments` (or equivalent quote/job status update).
- Show booked appointments in the customer calendar via `GET /appointments`.

**Definition of done:** a customer can accept a quote and book a slot; the slot
appears in the customer calendar.

### Iteration 7 — Trade calendar, jobs, and invoices

**Goal:** the electrician can manage scheduled work and raise invoices.

- Wire `GET /jobs` to the trade calendar day/week views and `JobsScreen`.
- Wire `POST /jobs/{id}/start` and `POST /jobs/{id}/complete`.
- Wire `GET /invoices`, `POST /invoices`, and `POST /invoices/{id}/mark-paid`.
- Convert an approved/sent quote to an invoice (`POST /quotes/{id}/convert-to-invoice`).
- Create an invoice from a completed job.

**Definition of done:** a trade user can view the calendar, start and complete a
job, and create/mark paid an invoice for that job.

### Iteration 8 — Lead Triage Agent (AI follow-up chat)

**Goal:** the customer receives AI clarifying questions after submitting a quote
request; answers inform the Quote Agent.

- Backend: extend the `Communication` model with `quote_request_id` and
  `sender_role` columns.
- Backend: add `POST /communications/{quote_request_id}/ai-followup` that reads
  the quote request + prior messages, calls the Kimi API for one clarifying
  question, and persists the assistant message.
- Mobile: replace the scripted `MessagesScreen` Q&A with a real chat thread that
  loads messages from `GET /communications` and posts replies via
  `POST /communications`.
- Trade users can open the same thread from lead detail or quote detail.
- Include chat history in the prompt when `POST /quotes/generate` is called for
  that quote request.

**Definition of done:** after submitting a quote request, a customer receives a
Kimi-generated clarifying question, replies, and the answer is visible to the
trade user before they generate the AI quote.

### Iteration 9 — Beta hardening and smoke tests

**Goal:** the Beta is stable enough for external users.

- Remove remaining demo scaffolding from connected mode:
  - pre-filled credentials,
  - hardcoded business codes,
  - mock fallback on detail routes,
  - hardcoded bank details.
- Add connected-mode E2E smoke tests covering:
  1. customer submits quote request,
  2. customer AI chat follow-up,
  3. trade generates AI quote and sends,
  4. customer accepts quote and books,
  5. trade completes job and marks invoice paid.
- Run dependency audits (`pnpm audit`, `pip-audit`) and fix high/critical issues.
- Review tenant isolation and rate limits.
- Update `AGENTS.md`, runbooks, and `docs/prd-beta.md` with final architecture.

**Definition of done:** the full customer → lead → AI quote → booking → job →
invoice flow passes in connected mode against a local backend, and the demo
screenshot fallback is explicitly flagged as deprecated.

---

*Beta PRD v1.0 — integrated against the existing FastAPI backend and the
React Native + Expo iOS app.*
