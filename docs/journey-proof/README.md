# Journey proof — screenshot-documented user journeys

Screenshot-proven documentation of live user journeys, captured against
**production** (www.mytradeportal.co.uk / shand-1-electrical-lorg9.mytradeportal.co.uk /
api.mytradeportal.co.uk). Each directory has a README (expected / observed / PASS-FAIL
per step) plus numbered PNGs; where a step could not be driven through the UI, it is
marked "API-seeded" and the API payload/response JSON is committed alongside.

## web/ — public web journeys (captured 2026-10-23, Playwright Chromium)

| Journey | Folder | Result |
|---|---|---|
| H1 Marketing home (all 13 sections) | `web/h1-home/` | PASS |
| H2 TryDemo live AI quote | `web/h2-try-demo/` | PASS (live LLM, 5 guide-priced lines, 15.6s) |
| H3 Blog index + article | `web/h3-blog/` | PASS |
| H4 Pricing + subscribe | `web/h4-pricing/` | PARTIAL — prod Paddle wired to sandbox (QE-W3); checkout unreachable on an already-subscribed account |
| H5 Quote token page + accept + date preferences | `web/h5-quote-token/` | PASS (desktop + mobile) |
| H5b Invoice token page + pay page | `web/h5-invoice-token/` | PARTIAL — invoice page PASS; card pay blocked by DEFECT-017; bare `/pay/:token` fixed in #290 |
| H6 Reset password (full email round-trip) | `web/h6-reset-password/` | PASS (functionally verified: new password works, old fails) |
| H7 Fair-use policy | `web/h7-fair-use/` | PASS |
| H8 Short-code entry → tenant portal | `web/h8-code-entry/` | PASS |
| E5 Portal intake + inline AI triage | `web/e5-portal-intake/` | PASS (reference 19D7C00C) |
| E6 Portal magic-link auth (full round-trip) | `web/e6-portal-auth/` | PASS |
| E7 Portal quotes & invoices (authenticated) | `web/e7-portal-quotes-invoices/` | PASS |
| E8 Guest chat thread | inline in `web/e5-portal-intake/` steps 4–5 | PASS |
| I.1 Outbound email evidence (6 templates) | `web/i1-email-evidence/` | PASS |

### Defects found (web pass, 2026-10-23)

- **QE-W1 (S3)** — `/pay/:token` without `?pi=`/`?cs=` rendered "This invoice link is invalid or has expired" even when the token was valid. **Fixed in #290.** Evidence: `web/h5-invoice-token/03-pay-desktop.png` vs `01-invoice-desktop.png` (same token).
- **QE-W2 (S2, = DEFECT-017 consequence)** — No card-payment path reachable end to end until the tenant completes Stripe Connect onboarding. The Stripe publishable key in the deployed bundle is `pk_live_…` (live mode), so once Connect works, real charges are possible — the Payment Element remains unproven until gate F6.
- **QE-W3 (S2, evidence for DEFECT-004)** — Production bundle calls `sandbox-api.paddle.com/pricing-preview` and loads `sandbox-cdn.paddle.com` assets. Displayed prices match the static GBP fallback. Evidence: `web/h4-pricing/paddle-network.txt`.
- **QE-W4 (S4, by design?)** — The hero AI demo is one-try per IP/browser; a second visit shows "You've already tried the AI demo" with no reset path short of downloading the app. Evidence: `web/h2-try-demo/05-demo-one-try-limit.png`. Tracked in #289.
- **QE-W5 (S4, copy)** — Portal invoice detail said "use the secure pay link in your invoice email" even when the email contained no pay link (tenant without Stripe). **Fixed in #290.** Evidence: `web/e7-portal-quotes-invoices/04-invoice-detail.png`.
- **QE-W6 (info)** — `/payments/dashboard` exists in `App.tsx` on `main`; not captured — gated behind Stripe Connect onboarding.
- **QE-W7 (S4)** — No self-serve password-reset *request* form on web surfaces. Tracked in #288.

### Web method notes

- Token URLs were obtained from real production emails (Resend) received at a QE-controlled disposable inbox; email HTML is preserved under `web/i1-email-evidence/`.
- Portal customer session for E7 was established via `POST /customer/register` against the same email as the CRM contact (register links by email) and independently via a real magic-link round-trip (E6).
- Sticky nav bars appearing mid-page in some full-page screenshots are a capture artifact, not a layout bug.

## mobile/ — iOS app journeys (wave 1, captured 2026-10-23)

iPhone 17 Pro simulator (iOS 26.5), dev-client build of `main@598cb93`, prod API
(`api-production-65db.up.railway.app`), tenant Shand 1 Electrical. Driven with
Appium/XCUITest + `simctl` deep links.

| Journey | Dir | Result |
|---|---|---|
| A2 Trade login | [mobile/a2-trade-login](mobile/a2-trade-login/) | PASS |
| B1 AI quote generation | [mobile/b1-ai-quote-generation](mobile/b1-ai-quote-generation/) | PASS |
| B2 Quote review / Refine with AI | [mobile/b2-quote-refine](mobile/b2-quote-refine/) | PASS |
| B3 Send quote | [mobile/b3-send-quote](mobile/b3-send-quote/) | PASS |
| B5 Quote → job conversion | [mobile/b5-convert-to-job](mobile/b5-convert-to-job/) | PASS (acceptance API-seeded — public token only exists in the customer email) |
| C1/C2 Job lifecycle | [mobile/c-job-lifecycle](mobile/c-job-lifecycle/) | PASS |
| D1/D2 Invoice create/send/mark-paid | [mobile/d-invoice-lifecycle](mobile/d-invoice-lifecycle/) | PASS |
| F1 Calendar day/week/month | [mobile/f1-calendar](mobile/f1-calendar/) | PASS with QE-M1-2 |
| F5 Multi-day scheduling | [mobile/f5-multi-day](mobile/f5-multi-day/) | PARTIAL (day-2 blocks invisible in day/week views — QE-M1-2) |
| G Settings sweep (13 screens) | [mobile/g-settings-sweep](mobile/g-settings-sweep/) | PASS |

### Defects found (mobile wave 1)

- **QE-M1-1 (S3) — BST times displayed as UTC.** Job times entered as 08:00 BST display as 07:00 across job detail, calendar grids, and notification copy. Root cause: API returns naive UTC (`"2026-10-24T07:00:00"`), mobile parses naive strings as local (`mobile/src/api/jobs.ts:191`). **Fixed in #295.** Evidence: [mobile/b5-convert-to-job](mobile/b5-convert-to-job/), [mobile/f1-calendar](mobile/f1-calendar/).
- **QE-M1-2 (S2) — Appointments invisible in calendar day/week views.** Day/week grids rendered jobs only; appointments (including auto-created multi-day "day 2 of N" work blocks) only appeared as month-view dots. **Fixed in #295.** Evidence: [mobile/f1-calendar/02-week-view.png](mobile/f1-calendar/02-week-view.png) vs [03-month-view.png](mobile/f1-calendar/03-month-view.png).

## mobile/ — iOS app journeys (wave 2, captured 2026-10-23/24)

Captured on an iPhone 17 Pro simulator (iOS 26.5), dev-client of `main@598cb93`,
driven by Appium/XCUITest against production. Rig note: an isolated simulator +
dedicated Appium server were used after another agent's session proved to be
driving the shared booted simulator.

| Journey | Folder | Result |
|---|---|---|
| A3 Onboarding stepper (12 steps, real tenant provisioned) | `mobile/a3-onboarding/` | PASS — trial subscription verified server-side |
| A4 Billing/paywall (trialing + active tenants) | `mobile/a4-billing/` | PASS with QE-M2-4/5 |
| A8 Trade password-reset request | `mobile/a8-password-reset/` | PASS (request side) |
| C4 Certificates (EICR) prototype | `mobile/c4-certificates/` | PASS (prototype documented; QE-M2-6 needs manual check) |
| E1 Customer login (invalid + success) | `mobile/e1-customer-login/` | PASS |
| E2 Customer quote-request flow (all 11 steps captured) | `mobile/e2-quote-request/` | **FAIL — QE-M2-7: submission never reaches the backend, success screen shown regardless** |
| E3 Customer requests + chat (message sent) | `mobile/e3-requests-chat/` | PASS |
| E4 Customer calendar/invoices/profile/notifications | `mobile/e4-customer-surfaces/` | PASS (data API-seeded — see folder README) |

### Defects found (mobile wave 2)

- **QE-M2-1 (S2)** — In-app Stripe Connect onboarding cannot render: `react-native-webview`
  is a peer dependency of `@stripe/stripe-react-native@0.64.0` Connect embedded
  components but is not installed in `mobile/`. "Connect Stripe" → "Opening Stripe…" →
  "Stripe setup" modal spins forever; a red "Failed to import react-native-webview"
  error toast then persists on unrelated screens. The server side works: the account
  was created and shows "Connected — restricted" (the DEFECT-017 503 is fixed by
  `3e1facc`). Evidence: `mobile/a3-onboarding/23..25`.
- **QE-M2-2 (S3)** — The Review & launch checklist is hardcoded
  (`ReviewLaunchStep.tsx` `LAUNCH_GATE_ITEMS`): Branding shows "To do" even after the
  branding step is completed, and Team/Pricing/Quote-defaults/Payments/Data-import can
  never be "Done" because no wizard steps write them.
- **QE-M2-3 (S4)** — Step-count confusion: the wizard is 12 steps, the welcome screen
  advertises a "6-step launch preview", and 5 built step components
  (PricingSetup/QuoteDefaults/TeamCapacity/PaymentsIntegrations/DataImport) are not
  wired in.
- **QE-M2-4 (S3)** — `/(trade)/billing` always shows the new-customer plan pitch
  ("14-day free trial…") even on an active paying Team tenant; no current-plan or
  manage affordance. Evidence: `mobile/a4-billing/08` vs `07`.
- **QE-M2-5 (S4)** — Settings subscription card prints the raw plan key
  ("Sole_trader plan"). Evidence: `mobile/a4-billing/02`.
- **QE-M2-6 (S3, needs manual device check)** — EICR circuit form's bottom buttons
  (save/cancel) accept no synthetic taps under XCUITest (invisible keyboard window
  over the lower screen band is the suspected simulator cause). Live BS 7671
  validation works. Evidence: `mobile/c4-certificates/04..06`.
- **QE-M2-7 (S1)** — Guest in-app quote requests never reach the backend, but the
  customer is told they were received. Two full drives of the E2 flow both ended at
  "Shand 1 Electrical has your request" while `GET /quote-requests` showed no new
  request and the account step rendered blank (`submittedAck` null).
  `CustomerQuoteRequestFlow.submitToBackend` swallows all submit errors
  (`catch {}`) and always advances to the confirmation screen. The same endpoint +
  payload shape succeeds via curl (201, appears in the trade list). Evidence:
  `mobile/e2-quote-request/22..24`.

### Mobile wave-2 method notes

- Onboarding needs `EXPO_PUBLIC_SETUP_TOKEN` in the JS bundle; Metro was restarted with it set (registration would otherwise 401).
- Uninstall+reinstall on the simulator did **not** clear the app's stored session (signed straight back into the previous account); an explicit in-app log out was used for fresh-state captures.
- The onboarding wizard holds all state in memory until the Review step — a mid-wizard app kill (observed twice: dev-server switch, simulator TCC permission grant) loses everything entered.
