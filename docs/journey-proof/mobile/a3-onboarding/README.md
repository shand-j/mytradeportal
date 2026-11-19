# A3 — New-tenant onboarding stepper (mobile, iOS)

Captured 2026-10-23/24 against **production** (`api-production-65db.up.railway.app`) on an
iPhone 17 Pro simulator (iOS 26.5) running the dev-client of `main@598cb93`, driven by
Appium/XCUITest. Fresh app install (no stored credentials).

**Result: PASS — full 12-step wizard completed end-to-end, real tenant provisioned.**

## What the wizard actually is (vs the 15-step expectation)

The inventory expected 15 steps. The shipped stepper
(`mobile/src/screens/onboarding/OnboardingStepperScreen.tsx:37-52`) has **12**:
Welcome → Account → Identity → Address → Tax → Compliance → Services → Branding →
**Review (registration happens here)** → Bank details → Card payments → Plan.
The UI confirms this on every screen ("Step N of 12"). Five step components exist in
`mobile/src/screens/onboarding/steps/` but are **not wired into the wizard**:
`PricingSetupStep`, `QuoteDefaultsStep`, `TeamCapacityStep`,
`PaymentsIntegrationsStep`, `DataImportStep`. (QE-M2-3)

Registration is a sequence of API calls fired from the Review step:
`POST /tenants` (gated by `X-Setup-Token`), then `PATCH /onboarding/step/*` per
section, logo upload, then a trial subscription is created server-side. Steps
10–12 run post-registration and save straight to the new tenant.

## Walkthrough

| # | Shot | What it shows |
|---|---|---|
| 01 | `01-entry-role-select.png` | Fresh-install entry: "I'm an Electrician" / "I'm a Customer" |
| 02 | `02-entry-electrician.png` | Electrician pane: Log in / Register my business |
| 03 | `03-step01-welcome.png` | Step 1 of 12: Welcome. Note the "6-step launch preview" graphic — copy mismatch (QE-M2-3) |
| 04 | `04-step02-account-filled.png` | Step 2: account form filled, password strength "Strong", terms accepted, Continue enabled |
| 05 | `05-step03-identity-filled.png` | Step 3: trading name, Limited company, Companies House no., year, website, quotes/week |
| 06 | `06-step04-address-empty.png` | Step 4: address & service area, empty (Continue disabled) |
| 07 | `07-step04-address-filled.png` | Step 4 filled: SK8 3NJ, radius 15mi, England |
| 08 | `08-step05-tax-vat-yes.png` | Step 5: VAT-registered branch (VAT number + scheme) |
| 09 | `09-step05-tax-no.png` | Step 5: not VAT registered → default 20% read-only |
| 10 | `10-step06-compliance-empty.png` | Step 6: CPS schemes, qualifications, PL insurance |
| 11 | `11-step06-compliance-filled.png` | Step 6 filled: NICEIC NE987654, 18th Ed + 2391, AXA PL-654321, £5m |
| 12 | `12-step07-services-empty.png` | Step 7: services grid (12 categories) |
| 13 | `13-step07-services-selected.png` | Step 7: consumer unit, EICR, EV charger, fault finding selected |
| 14 | `14-step08-branding.png` | Step 8: brand colour presets, custom hex, review link, logo |
| 15 | `15-step08-logo-denied.png` | Logo upload on a fresh sim with photos permission not yet granted → "Photo library access denied" (environment note below) |
| 16 | `16-step08-branding-filled.png` | Branding filled (review link set; default amber colour kept) |
| 17 | `17-step09-review.png` | Step 9: Review & launch — checklist + compliance summary. **Checklist is hardcoded** (QE-M2-2): Branding shows "To do" despite step 8 being completed; Team/Pricing/Quote defaults/Payments/Data import can never be "Done" |
| 18 | `18-step10-bank-details.png` | Step 10 (post-registration — header already shows the new tenant name): bank details for invoice emails |
| 19 | `19-step10-bank-validation-error.png` | Server-side validation: "Sort code must be 6 digits, e.g. 12-34-56" |
| 20 | `20-step10-bank-valid.png` | Valid details saved |
| 21 | `21-step11-card-payments.png` | Step 11: "Will you take card payments?" |
| 22 | `22-step11-card-payments-yes.png` | "Yes, take cards" → Stripe connection card (Not connected) |
| 23 | `23-step11-stripe-opening.png` | "Opening Stripe…" pending state |
| 24 | `24-step11-stripe-setup-spinner.png` | **Embedded Stripe Connect onboarding never loads — perpetual spinner** (QE-M2-1: `react-native-webview` missing peer dep of `@stripe/stripe-react-native` Connect components) |
| 25 | `25-step11-stripe-connected-restricted.png` | After closing the modal: "Connected — restricted" — the Connect **account was created** (POST /payments/connect works again; the DEFECT-017 503 is fixed server-side by `3e1facc`), but in-app onboarding cannot render |
| 26 | `26-step12-plan.png` | Step 12: plan picker (Sole Trader £25 / Pro £39 / Team £69), "subscriptions are set up on our website" (App Store 3.1.1 read-only) |
| 27 | `27-step12-plan-bottom.png` | Plan step bottom (note the red "!" error toast — the webview import failure persists across screens, QE-M2-1) |
| 28 | `28-dashboard-new-tenant.png` | End state: dashboard of the new tenant "QE Wave2 Electrical 1792795020" |
| 29 | `29-signed-out.png` | Signed out back to entry |

## Server-side proof

`api-subscription-proof.json` — `GET /billing/subscription` for the new account
immediately after the run: `status: trialing`, `plan_key: sole_trader`,
`trial_ends_at: 2026-11-06` (14-day trial). Tenant `e2cb9ba3-967f-4fa3-be87-57ccfc0ddc86`,
user `qe-w2-1792795020@example.com`.

## Validation states

- `19-step10-bank-validation-error.png` — server-side bank-details validation
  ("Sort code must be 6 digits").
- `30-validation-account-email-taken.png` — account step with a known email:
  inline "An account with this email already exists." banner with a
  "Log in instead" link, Continue disabled (captured on a second partial drive
  that did not register).
- `31-validation-account-weak-password.png` — 3-character password: "Weak"
  strength meter, Continue disabled.

## Environment / method notes

- The onboarding `POST /tenants` requires `EXPO_PUBLIC_SETUP_TOKEN` baked into the JS
  bundle. The originally running Metro lacked it; Metro was restarted with
  `EXPO_PUBLIC_API_BASE_URL=https://api-production-65db.up.railway.app` **and**
  `EXPO_PUBLIC_SETUP_TOKEN` set, after which registration succeeded.
- The wizard keeps all state in memory until the Review step. A mid-wizard app kill
  (e.g. the simulator's TCC photo-permission grant restarting the app) loses all
  entered data. On a real device the photo permission prompt does not kill the app,
  so this is a simulator artifact — but a user backgrounding the app mid-wizard
  long enough for iOS to reclaim it would hit the same data loss.
- Logo upload was exercised to the permission boundary; the granted-permission picker
  path was previously verified in RC cycles (DEFECT-010/011) and the post-registration
  upload path is the same `uploadTenantLogo` used from Settings.
- The plan-step Continue button rendered in the tenant's amber brand colour (default
  preset), not the dark navy of earlier steps — consistent theming, not a defect.
