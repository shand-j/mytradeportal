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
