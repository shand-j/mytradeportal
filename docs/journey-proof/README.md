# Journey proof — screenshot-documented user journeys

Screenshot-proven documentation of live user journeys, captured against
**production** (www.mytradeportal.co.uk / shand-1-electrical-lorg9.mytradeportal.co.uk /
api.mytradeportal.co.uk) with Playwright Chromium.

## web/ — public web journeys (captured 2026-10-23)

| Journey | Folder | Result |
|---|---|---|
| H1 Marketing home (all 13 sections) | `web/h1-home/` | PASS |
| H2 TryDemo live AI quote | `web/h2-try-demo/` | PASS (live LLM, 5 guide-priced lines, 15.6s) |
| H3 Blog index + article | `web/h3-blog/` | PASS |
| H4 Pricing + subscribe | `web/h4-pricing/` | PARTIAL — prod Paddle wired to sandbox (QE-W3); checkout unreachable on an already-subscribed account |
| H5 Quote token page + accept + date preferences | `web/h5-quote-token/` | PASS (desktop + mobile) |
| H5b Invoice token page + pay page | `web/h5-invoice-token/` | PARTIAL — invoice page PASS; card pay blocked by DEFECT-017; bare `/pay/:token` shows misleading "invalid link" (QE-W1) |
| H6 Reset password (full email round-trip) | `web/h6-reset-password/` | PASS (functionally verified: new password works, old fails) |
| H7 Fair-use policy | `web/h7-fair-use/` | PASS |
| H8 Short-code entry → tenant portal | `web/h8-code-entry/` | PASS |
| E5 Portal intake + inline AI triage | `web/e5-portal-intake/` | PASS (reference 19D7C00C) |
| E6 Portal magic-link auth (full round-trip) | `web/e6-portal-auth/` | PASS |
| E7 Portal quotes & invoices (authenticated) | `web/e7-portal-quotes-invoices/` | PASS |
| E8 Guest chat thread | inline in `web/e5-portal-intake/` steps 4–5 | PASS |
| I.1 Outbound email evidence (6 templates) | `web/i1-email-evidence/` | PASS |

## mobile/ — iOS app journeys (captured 2026-10-23/24, wave 2)

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

## Defects found (mobile pass, 2026-10-24)

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

## Defects found (web pass, 2026-10-23)

- **QE-W1 (S3)** — `/pay/:token` without `?pi=`/`?cs=` renders "This invoice link is invalid or has expired" even when the token is valid. Repro: open a valid `/invoice/:token`, then swap `/invoice/` for `/pay/` in the URL. Expected: redirect to the invoice page or show bank-transfer fallback. Evidence: `web/h5-invoice-token/03-pay-desktop.png` vs `01-invoice-desktop.png` (same token).
- **QE-W2 (S2, = DEFECT-017 consequence)** — No card-payment path is reachable end to end: the invoice email contains no pay link when the tenant has no Stripe Connect account, and Connect onboarding 503s platform-wide. The Stripe publishable key in the deployed bundle is `pk_live_…` (live mode), so once Connect works, real charges are possible — the Payment Element remains unproven.
- **QE-W3 (S2, evidence for DEFECT-004)** — Production bundle calls `sandbox-api.paddle.com/pricing-preview` and loads `sandbox-cdn.paddle.com` assets. Displayed prices match the static GBP fallback. Evidence: `web/h4-pricing/paddle-network.txt`.
- **QE-W4 (S4, by design?)** — The hero AI demo is one-try per IP/browser; a second visit shows "You've already tried the AI demo" with no reset path short of downloading the app. Evidence: `web/h2-try-demo/05-demo-one-try-limit.png`.
- **QE-W5 (S4, copy)** — Portal invoice detail says "use the secure pay link in your invoice email" even when the email contained no pay link (tenant without Stripe). Evidence: `web/e7-portal-quotes-invoices/04-invoice-detail.png` vs `web/i1-email-evidence/03-…png`.
- **QE-W6 (info)** — `/payments/dashboard` exists in `App.tsx` on `main` (resolves the inventory §0 discrepancy); not captured — gated behind Stripe Connect onboarding (DEFECT-017).
- **QE-W7 (S4)** — Neither the marketing nor the portal `/reset-password` page offers a "request a reset link" form; both only consume tokens and point the user back to the mobile app's forgotten-password screen. Customers who only ever used the web portal have no web self-serve reset entry point. Evidence: `web/h6-reset-password/01-reset-password.png`, `web/e6-portal-auth/06-portal-reset-password.png`.

## Method notes

- Token URLs were obtained from real production emails (Resend) received at a QE-controlled disposable inbox; email HTML is preserved under `web/i1-email-evidence/`.
- Portal customer session for E7 was established via `POST /customer/register` against the same email as the CRM contact (register links by email) and independently via a real magic-link round-trip (E6).
- Sticky nav bars appearing mid-page in some full-page screenshots are a capture artifact, not a layout bug.

### Mobile wave-2 method notes

- Onboarding needs `EXPO_PUBLIC_SETUP_TOKEN` in the JS bundle; Metro was restarted with it set (registration would otherwise 401).
- Uninstall+reinstall on the simulator did **not** clear the app's stored session (signed straight back into the previous account); an explicit in-app log out was used for fresh-state captures.
- The onboarding wizard holds all state in memory until the Review step — a mid-wizard app kill (observed twice: dev-server switch, simulator TCC permission grant) loses everything entered.
