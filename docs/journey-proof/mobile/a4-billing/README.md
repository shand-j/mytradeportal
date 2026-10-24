# A4 — Billing & paywall surfaces (mobile, iOS)

Captured 2026-10-24 against production, same rig as `../a3-onboarding/`.

**Result: PASS with defects (QE-M2-4).**

## Fresh tenant (trialing) — QE Wave2 Electrical

| # | Shot | What it shows |
|---|---|---|
| 01 | `01-fresh-tenant-dashboard.png` | Dashboard of the just-onboarded tenant |
| 02 | `02-fresh-settings-trial-card.png` | Settings → Subscription card: **Free trial, "Sole_trader plan", Trial ends 6 Nov** (raw plan key with underscore — QE-M2-5) |
| 03 | `03-fresh-billing-plan-picker.png` | `/(trade)/billing`: plan picker with trial copy |
| 04 | `04-fresh-billing-bottom.png` | Billing screen bottom |
| 05 | `05-paywall-route-redirects-when-trialing.png` | `/paywall` deep link on a trialing tenant redirects straight to the dashboard (paywall correctly not shown mid-trial) |

## Existing tenant (active subscription) — Shand 1 Electrical (jshand89@gmail.com)

| # | Shot | What it shows |
|---|---|---|
| 06 | `06-jshand-dashboard.png` | Dashboard after trade login |
| 07 | `07-jshand-settings-subscription-active.png` | Settings → Subscription card: **Active, Team plan, Renews 3 Nov**. The red "!" toast bottom-left is the persisted `react-native-webview` import error (QE-M2-1) |
| 08 | `08-jshand-billing-active-team.png` | `/(trade)/billing` on the active **paying** tenant still renders "Choose your plan / Every plan starts with a 14-day free trial…" (QE-M2-4) |
| 09 | `09-jshand-billing-bottom.png` | Billing screen bottom — no current-plan or manage-subscription affordance |

## Findings

- **QE-M2-4 (S3)** — `mobile/app/(trade)/billing.tsx` renders the onboarding
  `PlanPaymentStep` unconditionally: an active Team-plan tenant sees the new-customer
  sales pitch and gets no current-plan, renewal, or manage-billing affordance on the
  billing screen. Current status only appears on the Settings card (shot 07).
- **QE-M2-5 (S4)** — Settings subscription card prints the raw plan key
  ("Sole_trader plan") instead of "Sole Trader".
- Paddle checkout itself is intentionally not exercised here (web-covered; prod
  Paddle still sandbox per DEFECT-004 / QE-W3). The in-app plan step is read-only
  by design (App Store 3.1.1) and points to the website.
