# Re-verification of #298 / #299 / #307 (mobile, 2026-10-24)

Re-verification pass over three fixes merged to `main` (`c0cce05`), run on the
iPhone 17 Pro simulator (iOS 26.5) against **production**
(`api-production-65db.up.railway.app`, tenant Shand 1 Electrical /
`shand-1-electrical-lorg9`, trade login `jshand89@gmail.com`).

Rig: dev-client `.app` **with** the `react-native-webview` native module
(unpacked from `/tmp/mtp-299-build.tar.gz`, `xcrun simctl install`), serving the
latest-`main` JS bundle from Metro (`/tmp/mtp-pr166/mobile`, `c0cce05` = merge of
#305 + #306 + #307). Driven with Appium/XCUITest; screenshots via
`xcrun simctl io <udid> screenshot`, resized with `sips -Z 1200`.

## Results

| Fix | Item | Result | Evidence |
|---|---|---|---|
| #298 (S1, PR #305) | Guest quote-request happy path reaches the server and shows a real reference | **PASS** | 01–04, `api-quote-requests.json` |
| #298 (S1, PR #305) | Failed submission blocks with error + retry, no fake confirmation; retry succeeds after unblock | **PASS** | 05–07, `api-quote-requests.json`, `api-contact.json` |
| #299 (S2, PR #306) | Stripe Connect embedded onboarding renders in-app | **PASS** | 08–10, `api-payments-status.json` |
| #307 (polish) | Settings subscription card shows display name; `/billing` is read-only for a subscribed tenant | **PASS** | 11–12 |

## #298 — guest quote-request failure surfacing (was QE-M2-7)

### Happy path

1. `01-code-entry.png` — guest entry, tenant code `755862` entered.
2. `02-business-found.png` — business resolved server-side (Shand 1 Electrical,
   tenant-branded red theme).
3. `03-consents-step.png` — full 11-step flow completed (postcode SK8 3NJ,
   contact QE Reverify Guest / qe-reverify@example.com, property, consumer-unit
   questionnaire, photos skipped, timing Flexible, budget £500–£1,000), consents
   ticked, submit armed.
4. `04-confirmation-server-ref.png` — confirmation "Shand 1 Electrical has your
   request" **with server reference `037A0849`** and an accurate summary.
   Server-side confirmation: `GET /quote-requests` (trade bearer + X-Tenant-ID)
   returns row `037a0849-fed8-4411-8fd5-4a28a85a09e1`, created
   2026-10-24T04:49:11Z, `source: app`, structured data matching the form
   (consumer_unit, 8 circuits, no_rcd, budget 500_1k) — see
   `api-quote-requests.json`. CRM contact `bbc0dafd-…` created with the same
   details (`api-contact.json`).

### Failure path (server-side block + retry)

5. `05-failpath-consents-ready.png` — flow re-driven with the same email after
   the contact was blocked via `POST /contacts/{id}/block` (trade API).
6. `06-submit-blocked-error.png` — submit against the blocked contact (server
   403 `customer_blocked: …`): the flow **stays on step 9 (Consents)**, shows a
   blocking error banner ("This customer has been blocked by the business and
   cannot log in, request quotes or send messages. Contact the business
   directly." — the machine prefix `customer_blocked:` correctly stripped), the
   CTA changes to **Retry**, and **no confirmation screen is shown**
   (app-tree check: no "has your request" element present). No new quote request
   appears server-side for the blocked attempt.
7. `07-retry-success.png` — after `POST /contacts/{id}/unblock`, tapping **Retry**
   resubmits successfully: confirmation screen with a **new server reference
   `E80AFD6E`**, confirmed server-side as
   `e80afd6e-85a1-4152-b632-0589f88cace7` created 2026-10-24T04:56:29Z against
   the same contact (`api-quote-requests.json`). The contact was left unblocked
   after the test (`api-contact.json`, `is_blocked: false`).

This is the exact scenario that previously ended at a fake success screen with
`submittedAck` null (QE-M2-7). Both directions now behave correctly.

## #299 — react-native-webview / Stripe Connect embedded onboarding (was QE-M2-1)

8. `08-payments-initial.png` — Settings → Payments, Stripe connection card
   ("Not connected" on first paint — see QE-RV-1 below), Connect Stripe CTA.
9. `09-connect-onboarding-rendered.png` — tapping Connect Stripe opens the
   "Stripe setup" sheet and the **embedded Connect onboarding component renders**:
   "Add information to start accepting money / My Trade Portal uses Stripe to
   help you receive payments…" with an "Add information" button. Three
   `XCUIElementTypeWebView` elements present in the app tree; no infinite
   spinner (loading resolved in ~15 s), no red "Failed to import
   react-native-webview" toast. No real onboarding fields were completed —
   render proof only, per the verification scope.
10. `10-payments-connected-restricted.png` — after closing the sheet, the card
    re-syncs to **"Connected — restricted"** with "Finish Stripe setup" /
    "Refresh status" / "View payouts & Stripe activity", matching the server
    (`api-payments-status.json`: `connected: true`, `charges_enabled: false`,
    `payouts_enabled: false`, `acct_1UTx5WGblruzCXwd`).

## #307 — plan display names + read-only billing

11. `11-settings-team-plan.png` — Settings subscription card shows **"Team plan"**
    (display name, not the raw plan key), status Active, "Renews 3 Nov",
    "Manage your subscription at mytradeportal.co.uk".
12. `12-billing-readonly.png` — `/(trade)/billing` on this subscribed tenant
    shows the **read-only status view** ("Your subscription": Active / Team plan
    / Renews 3 Nov / manage at mytradeportal.co.uk, single Done button) — not
    the new-customer plan pitch ("14-day free trial…") flagged in QE-M2-4.

## New defects / observations

- **QE-RV-1 (S4, transient)** — On first navigation to Settings → Payments
  straight after a fresh login, the Stripe card rendered "Not connected"
  (`08-payments-initial.png`) even though the tenant's Connect account already
  existed server-side (`connected: true`). Revisiting the screen minutes later
  showed the correct "Connected — restricted" (`10-payments-connected-restricted.png`).
  Looks like a stale/failed first `usePaymentsStatus` fetch with no retry
  surface; worth a watch, not blocking.

## Cleanup note

Two real leads ("QE Reverify Guest" / qe-reverify@example.com, refs 037A0849 and
E80AFD6E) and one CRM contact remain in the Shand 1 Electrical production tenant
as evidence artifacts; the contact is **not** blocked (post-test state).
