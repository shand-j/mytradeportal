# User journeys — My Trade Portal

The complete map of **implemented** user journeys, derived from the code
(mobile route tree, landing-site routes, API routers) — not from marketing
copy. Snapshot: `main` @ `df10a1f` (2026-10-23), cross-checked against the
QE evidence matrix (`/tmp/mtp-qe/matrix.md`, RC6 cycle) where noted.

## How to read the evidence status

| Status | Meaning |
|---|---|
| **device** | Verified on a physical iPhone |
| **simulator** | Verified on the iOS simulator / mobile web build |
| **web** | Verified in a browser (landing site or back-office SPA) |
| **API-only** | Endpoint exists and is exercised by tests/clients; no full UI pass recorded |
| **config-pending** | Code complete but needs provider configuration before it can run live (e.g. Telnyx SMS keys/number) |
| **device-pending** | Code complete but only verifiable on a physical device (APNs push, on-device speech recognition) |

## Surfaces

- **Mobile** — `mobile/` Expo Router app. Trade routes under `app/(trade)/`,
  customer routes under `app/(customer)/`, entry/onboarding at the root.
- **Landing** — `web/landing/new design/app` (one host-aware bundle):
  `www`/apex serves marketing + public token pages; `{slug}.mytradeportal.co.uk`
  serves the tenant customer portal (`src/portal/`).
- **Back-office** — `web/app` SPA (dashboard, CRM, quotes, jobs, invoices,
  calendar, reviews, AI insights, settings).
- **API** — `services/api/app/routers/`. Endpoint paths below include the
  router prefix.

---

## Electrician (tradesperson)

### E1. Business onboarding wizard
- **Entry:** fresh install → `app/onboarding/index.tsx` (also re-enterable until `POST /onboarding/launch`).
- **Screens:** `OnboardingStepperScreen` — welcome → account → identity →
  address/service-area → tax/VAT → compliance → services → branding →
  review/launch, then post-launch bank details → card-payments gate → plan
  (`mobile/src/screens/onboarding/steps/`).
- **API:** `POST /tenants`, `GET /tenants/email-availability`,
  `GET /onboarding/status`, `PATCH /onboarding/step/{step_name}`,
  `POST /onboarding/launch`, `GET /integrations/address/autocomplete`,
  `GET /pricing/profiles`, `POST /tenants/me/logo`.
- **Evidence:** simulator.

### E2. Login / password reset
- **Entry:** `app/index.tsx` (EntryScreen) → `app/trade-login.tsx`;
  `app/reset-password.tsx` (deep-linked from the email).
- **API:** `POST /auth/token` / `POST /auth/login`, `GET /auth/me`,
  `POST /auth/password-reset/request`, `POST /auth/password-reset/confirm`.
- **Evidence:** simulator + web.

### E3. Subscription gate (paywall) and plan management
- **Entry:** `app/paywall.tsx` gates the trade area while the subscription is
  incomplete; the paywall polls so a web subscription releases it
  automatically. Plan management at `app/(trade)/billing.tsx` (reuses
  `PlanPaymentStep`) — **billing is web-first**: checkout happens on the
  landing `/subscribe` page (Paddle), no tappable billing links in-app.
- **API:** `GET /billing/plans`, `GET /billing/subscription` (carries `seats`
  / `seats_in_use`), `POST /billing/checkout`, `POST /billing/plan-change`,
  `POST /billing/portal-session`; Paddle webhooks at `POST /webhooks/...`.
- **Evidence:** web (RC5: sandbox card end-to-end on `/subscribe`, both
  postcode paths; paywall gate + copy verified on simulator).

### E4. Dashboard
- **Entry:** `app/(trade)/dashboard.tsx` (default tab); web back-office `/`.
- **API:** `GET /analytics/dashboard`, `GET /notifications`,
  `GET /notifications/unread-count`.
- **Evidence:** simulator + web.

### E5. Leads inbox → quote request handling
- **Entry:** `app/(trade)/inbox.tsx` → `app/(trade)/lead/[id].tsx`;
  `app/(trade)/manual-lead.tsx` records a lead by hand;
  `app/(trade)/request-info.tsx` asks the customer for more detail
  (message thread or AI follow-up chat).
- **API:** `GET /quote-requests`, `GET/PATCH /quote-requests/{id}`,
  `POST /quote-requests` (manual), `POST /communications/threads`,
  `POST /communications/{quote_request_id}/ai-followup`.
- **Evidence:** simulator.

### E6. AI quote generation and refinement (incl. voice dictation)
- **Entry:** `app/(trade)/quote-intake.tsx` (QuoteIntakeScreen) →
  `app/(trade)/quote/[id].tsx` (QuoteEditScreen).
- **Flow:** free-text description (with on-device **voice dictation** via
  `VoiceInputButton`, iOS SFSpeechRecognizer) → `POST /quotes/generate`
  (`/generate-async` variant) → guide-priced ex-VAT line items with
  `ai_confidence` / `ai_warnings` / `ai_assumptions` / `ai_observations`
  (customer photos captioned by the vision pass). Electrician instructions
  re-run via `POST /quotes/{id}/refine`, which preserves manual edits and
  returns a post-refine **amends summary** plus refreshed confidence; the
  electrician rates the refine with **thumbs up/down**
  (`POST /quotes/{id}/refine-rating`). Per-quote VAT override chip
  ("VAT x% / Zero-rated 0%") for VAT-registered tenants.
- **API:** `POST /quotes/generate`, `POST /quotes/generate-async`,
  `POST /quotes/{id}/refine`, `POST /quotes/{id}/refine-rating`,
  `PATCH /quotes/{id}` (`vat_rate`), `GET /quotes/training-events`.
- **Evidence:** simulator for the generate/refine/rating flow;
  **voice dictation device-pending** (native speech module, per QE matrix).

### E7. Quote review and send
- **Entry:** `app/(trade)/quotes.tsx` → `app/(trade)/quote/[id].tsx`;
  web back-office `/quotes/:id`.
- **Flow:** edit lines, approve (`POST /quotes/{id}/approve`) or reject,
  PDF preview (`GET /quotes/{id}/pdf`), then `POST /quotes/{id}/send` —
  emails the customer a token link to the landing `/quote/:token` page.
  Tenant `quote_rounding` (0/5/10) rounds totals up
  (`rounding_adjustment` carried on the quote).
- **API:** as above + `GET /quotes`, `POST /quotes`,
  `DELETE /quotes/{quote_id}`.
- **Evidence:** simulator + web.

### E8. Quote lifecycle: chasing, acceptance, draft job
- **Flow:** the reminder scheduler (`app/scheduler.py`) emails quote
  reminders (default 3, then stop; per-tenant cadence in tenant settings).
  Customer accept/decline lands via the public token page (see C5);
  acceptance with ranked date preferences auto-creates a tentative **draft
  job** (`status="draft"`) prefilled with the 1st choice — drafts never block
  the calendar and never email the customer. The electrician confirms via
  `POST /quotes/{id}/convert-to-job`; the mobile job-create screen shows the
  customer's preferences as tappable chips.
- **API:** `POST /public/quote/{token}/accept|decline|preferences`,
  `POST /quotes/{id}/convert-to-job`, `GET /jobs/suggest-schedule`.
- **Evidence:** simulator + web (token page); scheduler API-only.

### E9. Jobs and calendar
- **Entry:** `app/(trade)/calendar.tsx` (day/week/month; **All/Me** assignee
  filter on multi-seat plans only), `app/(trade)/job/new.tsx`,
  `app/(trade)/job/[id].tsx`; web back-office `/calendar`, `/jobs/:id`.
- **Flow:** job create/convert defaults the assignee to the only active user
  on single-seat plans; explicit assignees validated server-side. Every
  assignment path passes the dispatch guardrails (`app/dispatch.py`) —
  structured 409s: `schedule_conflict`, `daily_hours_cap`, `job_locked`.
  Multi-day jobs are split into consecutive working-day appointment blocks
  (`app/work_blocks.py`); reschedules shift the blocks by the same delta.
  Job detail: **Navigate** button opens the device's maps app (GPS nav),
  one-tap tel:/sms:/mailto:, **photos with before/after/general kinds**,
  **measurements** list, start → complete → invoice
  (`POST /jobs/{id}/start`, `/complete`). Calendar subscription via
  `GET /calendar/feed-link` / `GET /calendar/feed.ics` (webcal/.ics).
- **API:** `GET/POST /jobs`, `GET/PATCH/DELETE /jobs/{id}`,
  `POST /jobs/{id}/media`, `PATCH /jobs/{id}/media/{asset_id}`,
  `POST /jobs/{id}/cancel`, `GET/POST/PATCH/DELETE /appointments`,
  `GET /appointments/availability`.
- **Evidence:** simulator (photos, measurements, calendar views, guardrail
  409s); GPS nav verified on simulator maps.

### E10. Invoices
- **Entry:** `app/(trade)/invoices.tsx`, `app/(trade)/invoice/new.tsx`
  (prefills accepted quote lines when only `job_id` is sent), 
  `app/(trade)/invoice/[id].tsx`; web back-office `/invoices/:id`.
- **Flow:** create from quote (mirrors quote totals exactly — never
  re-rounded) or scratch (rounded once at creation) → issue → **send by
  email** (`POST /invoices/{id}/send`) and/or **SMS**
  (`POST /invoices/{id}/send-sms`) → customer pays by card (see C6) or the
  electrician marks paid manually (`POST /invoices/{id}/mark-paid`);
  refund / cancel supported. The scheduler emails invoice reminders
  (recur until paid).
- **API:** `GET/POST /invoices`, `GET/PATCH/DELETE /invoices/{id}`,
  `POST /invoices/{id}/issue|send|send-sms|mark-paid|refund|cancel`.
- **Evidence:** simulator + web; **SMS send config-pending** (Telnyx).

### E11. CRM
- **Entry:** `app/(trade)/customers.tsx` → `app/(trade)/customer/[id].tsx`;
  web back-office `/customers`.
- **API:** `GET/POST /contacts`, `GET/PATCH/DELETE /contacts/{id}`,
  `POST /contacts/{id}/block|unblock`, `GET/POST /customers`.
- **Evidence:** simulator + web.

### E12. Team invites and seats
- **Entry:** `app/(trade)/team.tsx` (TeamSettingsScreen) — admin invites
  staff; seat cap enforced per plan (sole_trader 1 / pro 5 / team 15) with a
  structured `seat_limit_reached` error. Invitee sets their password from the
  emailed single-use link on the landing `/accept-invite` page.
- **API:** `POST /users/invite`, `POST /users/accept-invite`,
  `POST /users/invite/magic-link` (fresh link; revokes earlier ones),
  `GET/PATCH/DELETE /users/...`, `GET /billing/subscription` (seat counts).
- **Evidence:** simulator + web.

### E13. Branding (colour + logo)
- **Entry:** `app/(trade)/branding.tsx` (BrandingSettingsScreen); logo also
  set during onboarding.
- **API:** `POST /tenants/me/logo` (multipart → MinIO),
  `DELETE /tenants/me/logo`, `PATCH /tenants/me`; logo served publicly at
  `GET /businesses/{slug}/logo`, `GET /businesses/{slug}/public-config`.
- **Evidence:** simulator.

### E14. Payments setup (Stripe Connect) and payouts
- **Entry:** `app/(trade)/payments.tsx` (PaymentsSettingsScreen +
  `StripeConnectCard`) — embedded Stripe `account_onboarding` component
  in-app (no Safari bounce); "View payouts & Stripe activity" opens the
  landing `/payments/dashboard` (embedded `notification_banner`, `payouts`,
  `balances` components). Default card-payments toggle only enables when the
  account is connected with charges enabled.
- **API:** `GET /payments/status` (re-syncs mirrored account flags),
  `POST /payments/connect`, `POST /payments/connect/session`
  (`components=onboarding|dashboard`), `PATCH /payments/settings`,
  `GET /payments/onboarding-return` (legacy hosted AccountLink bounce via
  `/payments/stripe-bounce`).
- **Evidence:** simulator as far as reachable — **blocked by DEFECT-017**
  (`POST /payments/connect` 503s server-side in RC6; the embedded component
  itself not yet reachable). Negative check passed: no Safari bounce.

### E15. Analytics and AI insights
- **Entry:** `app/(trade)/analytics.tsx`; web back-office `/ai-insights`.
- **API:** `GET /analytics/dashboard`, `GET /analytics/ai-insights`.
- **Evidence:** simulator + web.

### E16. Reviews
- **Entry:** web back-office `/reviews`.
- **API:** `GET/POST /reviews`, `GET /reviews/stats`.
- **Evidence:** web.

### E17. Settings, data export, offboarding
- **Entry:** `app/(trade)/settings.tsx` hub → follow-ups
  (`follow-ups.tsx` — quote/invoice reminder cadence), working hours
  (`working-hours.tsx` — drives `/appointments/availability`), payment
  details (`payment-details.tsx` — bank details shown on invoices),
  branding, team, billing.
- **API:** `PATCH /tenants/me` (settings JSONB), `GET /export/my-data`
  (GDPR export), `POST /tenants/me/offboard` (self-service offboarding —
  see P2).
- **Evidence:** simulator.

### E18. Portal promotion (QR / 6-digit code)
- **Entry:** mobile Settings/CRM quote-request share sheet
  (`PortalQrSheet`, `src/lib/qr.ts`) — the electrician shows a QR code or a
  6-digit code pointing at their portal; customers redeem the code on the
  landing `/code` page.
- **API:** `GET /businesses/by-code/{code}/public-config`,
  `POST /businesses/{slug}/quote-requests/uploads` (public photo upload).
- **Evidence:** simulator + web.

---

## Customer (homeowner)

### C1. Quote request — portal form / QR / share
- **Entry:** tenant portal `{slug}.mytradeportal.co.uk` (`/` → PortalHome
  quote-request form with inline AI triage check), QR/6-digit code from the
  electrician, or the mobile customer flow
  (`CustomerQuoteRequestFlow` — postcode → category → job-specific
  questionnaires (EICR / EV charger / consumer unit / other) → media capture
  → contact → budget → consents → confirmation; emergency callback path).
- **API:** `POST /businesses/{slug}/quote-requests` (public submit — portal
  form and mobile flow), `POST /quote-requests/{id}/media`,
  `POST /quote-requests/from-share`,
  `POST /businesses/{slug}/quote-requests/uploads`.
- **Evidence:** web + simulator.

### C2. Portal sign-in (magic link, invisible auth)
- **Entry:** emailed magic link → portal `/auth/magic`; first-time claim at
  portal `/claim`. Mobile: `app/customer-login.tsx`.
- **API:** `POST /customer/auth/magic/request`, `POST /customer/auth/magic`,
  `POST /customer/auth/claim`, `POST /customer/login`,
  `POST /customer/register`, `GET /customer/me`.
- **Evidence:** web + simulator.

### C3. Quote review, accept/decline, date preferences
- **Entry:** emailed token page `/quote/:token` (landing) or portal
  `/quotes/:id` (PortalQuoteDetail).
- **Flow:** view the quote with tenant branding; **accept** with up to 3
  ranked date/time-window preferences picked against an availability-aware
  calendar (coarse available/partial/busy/closed per day — no booking
  details leak), or **decline**. Acceptance auto-creates the draft job (E8).
- **API:** `GET /public/quote/{token}` (via `GET /public/{kind}/{token}`),
  `GET /public/quote/{token}/availability`,
  `POST /public/quote/{token}/accept|decline|preferences`;
  portal: `GET /customer/quotes`, `POST /customer/quotes/{id}/accept|reject`.
- **Evidence:** web (token page incl. preferences calendar) + API-only
  (portal accept/reject).

### C4. Bookings
- **Entry:** portal bookings on PortalHome after sign-in.
- **API:** `GET /customer/appointments`, `POST /customer/appointments`.
- **Evidence:** API-only.

### C5. Messages
- **Entry:** portal thread on the quote, mobile
  `app/(customer)/messages.tsx`.
- **API:** public threads router (`/public/threads`),
  `POST /communications` (staff side).
- **Evidence:** web + simulator.

### C6. Invoice card payment
- **Entry:** emailed token page `/invoice/:token` → **Pay by card** →
  `/pay/:token` (Stripe Elements `PaymentForm`; the API mints/reuses a
  PaymentIntent and the page confirms it with the client secret); portal
  `/invoices/:id` (PortalInvoiceDetail) → pay in place; mobile
  `app/(customer)/invoice/[id].tsx`. Mobile result deep link:
  `app/payments/[result].tsx`.
- **API:** `GET /public/{kind}/{token}` (carries `payment_url`),
  `POST /customer/invoices/{id}/pay`; Stripe webhooks at
  `POST /webhooks/stripe/...` mark the invoice paid.
- **Evidence:** web (pay page renders; a real-card live-Stripe payment is
  the go-live gate per the QE matrix) + simulator.

### C7. Reminders — email + SMS with STOP opt-out
- **Flow:** scheduler emails quote/invoice reminders; appointment reminders
  text the customer **and** the assigned electrician (default 24h and 2h
  before) via Telnyx, degrading to email/push when unconfigured. Inbound
  CTIA keywords on `POST /webhooks/telnyx` (Ed25519-verified): **STOP** sets
  `sms_opt_out` on the contact (sweep falls back to email), START/UNSTOP
  re-enables. Permanent SMS failures page staff once per day.
- **API:** `app/appointment_reminders.py`, `app/sms.py`,
  `app/sms_alerts.py`, `app/routers/telnyx_webhooks.py`.
- **Evidence:** **config-pending** — needs provisioned Telnyx keys/number;
  live SMS delivery to a real handset is still open per the QE matrix.

### C8. Notifications (in-app + push)
- **Entry:** mobile `app/(customer)/notifications.tsx`; push registration
  on first launch (`src/lib/pushNotifications.ts`).
- **API:** `GET /customer/notifications`, unread count, mark-read/read-all.
- **Evidence:** simulator for in-app; **push delivery device-pending**
  (APNs cannot be simulated).

### C9. Help centre
- **Entry:** landing `/help`, `/help/:slug` (HelpIndex/HelpArticle).
- **Evidence:** web.

### C10. Customer mobile home
- **Entry:** `app/(customer)/` tabs — requests (own quote requests),
  calendar, invoices, messages, profile.
- **API:** `GET /customer/quote-requests`, `GET /customer/invoices`,
  `GET /customer/appointments`, `POST /customer/files/upload`,
  `GET /customer/files/download`.
- **Evidence:** simulator.

---

## Platform / ops

### P1. SaaS billing (web-first subscribe)
- **Entry:** landing `/subscribe` (SubscribePanel → Paddle checkout, the
  merchant-of-record flow); `/fair-use` policy page; plan changes and the
  Paddle customer portal from the back-office/mobile billing screen.
- **API:** `GET /billing/plans`, `POST /billing/checkout`,
  `POST /billing/plan-change`, `POST /billing/portal-session`,
  `GET /billing/checkout-page`; Paddle webhooks (`POST /webhooks/...`)
  mirror subscription state.
- **Evidence:** web (RC5 sandbox end-to-end).

### P2. Tenant offboarding
- **Entry:** mobile Settings (tenant admin) — self-service with
  `confirm_slug`.
- **API:** `POST /tenants/me/offboard` — cancels the Paddle subscription and
  deletes the Stripe connected account (best-effort), deactivates all
  staff/customer accounts, revokes magic-link/invite/document/reset tokens,
  deactivates the tenant, anonymises PII in place while retaining financial
  records per `docs/data-retention.md`.
- **Evidence:** API-only.

### P3. Ops, alerts and diagnostics
- **Entry/flow:** staff AI-cost dashboard (`GET /staff/ops/ai-costs`);
  email bounce/failure alerts via Resend webhooks
  (`app/routers/resend_webhooks.py`) with a dedupe ledger shared with SMS
  failure paging (`app/sms_alerts.py`); health/feature-flags/diagnostics
  routers (`GET /health`, `GET /feature-flags`); runbooks in
  `docs/runbooks/`.
- **Evidence:** API-only; alert runbooks documented.

---

## Parked / not built

Deliberately absent or stubbed — do not document as working journeys:

- **Certificates (EICR)** — mobile UI shell only: `certificates.tsx`,
  `certificate/[id].tsx`, `CertificateScreen`/`CircuitFormScreen` render a
  hardcoded "No certificates yet" empty state. There is **no certificates
  router/model in the API**.
- **Deposits** — no code anywhere (no model, endpoint, or UI).
- **Offline mode** — connected mode only by design. `OfflineBanner` +
  `offlineStore` are a visual stub; nothing reads the sync queue.
- **Xero / QuickBooks integrations** — no code. Onboarding's
  `PaymentsIntegrationsStep` is presentational.
- **BoQ engine (ocerp)** — service deleted; the parked 501 client shim
  (`app/clients/ocerp.py`) and `POST /quotes/generate-boq`,
  `GET/PATCH /quotes/{id}/boq` remain intentionally parked.
- **Dark mode** — post-MVP (mobile is light-mode only at launch).

## Verification

Every route and endpoint named above was checked against the code on
`main` @ `df10a1f`. Spot-checks (grep-based, 2026-10-23) — all confirmed:

1. `mobile/app/(trade)/quote-intake.tsx` + `QuoteIntakeScreen.tsx` —
   `VoiceInputButton` import and usage.
2. `services/api/app/routers/quotes.py` — `/generate`, `/generate-async`,
   `/{quote_id}/refine`, `/{quote_id}/refine-rating`, `/{quote_id}/send`.
3. `services/api/app/routers/public_docs.py` —
   `/quote/{token}/availability`, `/{kind}/{token}`, `/quote/{token}/accept`,
   `/decline`, `/preferences`.
4. `services/api/app/routers/invoices.py` — `/{invoice_id}/send`,
   `/send-sms`, `/mark-paid`, `/refund`.
5. `services/api/app/routers/payments.py` — `/connect`, `/connect/session`,
   `/status`, `/onboarding-return`; embedded onboarding confirmed in
   `mobile/src/hooks/useStripeConnectOnboarding.tsx` (`EmbeddedStripeOnboarding`).
6. `web/landing/new design/app/src/App.tsx` — portal routes (`/`,
   `/auth/magic`, `/claim`, `/quotes/:id`, `/invoices/:id`) and www routes
   (`/subscribe`, `/quote/:token`, `/pay/:token`, `/payments/dashboard`,
   `/help`, `/code`).
7. `services/api/app/routers/users.py` — `/invite`, `/accept-invite`,
   `/invite/magic-link`.
8. `services/api/app/routers/tenants.py` — `/me/logo` (POST/DELETE),
   `/me/offboard`.
9. `services/api/app/routers/jobs.py` — `/suggest-schedule`,
   `/{job_id}/media`, `/{job_id}/start`, `/{job_id}/complete`.
10. `services/api/app/routers/telnyx_webhooks.py` + `app/sms.py` — STOP
    opt-out handling and Telnyx send path.
11. Certificates stub: `mobile/src/screens/trade/CertificatesScreen.tsx`
    hardcodes the empty state; no `certificate` matches in
    `services/api/app/routers/`.
12. Onboarding step order: `OnboardingStepperScreen.tsx` `STEPS` array
    (welcome → account → identity → address → tax → compliance → services →
    branding → review, then bank_details → card_payments → plan).
