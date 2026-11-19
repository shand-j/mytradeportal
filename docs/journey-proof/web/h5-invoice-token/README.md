# H5b — Invoice token page + pay page (`/invoice/:token`, `/pay/:token`)

- **Actor:** homeowner (unauthenticated, via emailed secure link)
- **Setup (API):** `POST /invoices {contact_id, quote_id}` → INV-004 (`88a02fff-…`, mirrors the accepted quote exactly: subtotal £625 / VAT £0 / total £625), `POST /invoices/{id}/send` → `invoice_sent` email received with `https://www.mytradeportal.co.uk/invoice/vqbvkDANJLj-rH0VnMmlvVL6nkRoD8Lh5a81CNwkI7M` (email evidence `../i1-email-evidence/03-…`)
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/invoice/:token` (desktop) | Branded invoice with lines, totals, due date, payment method | INV-004, "Due by 6 November 2026", line items match the quote exactly, "Pay by bank transfer" block with account name/sort code/account number/payment reference INV-004 (`01-invoice-desktop.png`) | PASS |
| 2 | Open `/invoice/:token` (mobile 390x844) | Same, usable layout | Renders (`02-invoice-mobile.png`) | PASS |
| 3 | Pay by card | Secure pay link in email → Stripe Payment Element | **No pay link in the invoice email** — the tenant has no Stripe Connect account (platform-wide Connect onboarding is broken, DEFECT-017), so `payment_url` is null and the email carries only the bank-transfer details | BLOCKED (upstream DEFECT-017) |
| 4 | Open `/pay/:token` bare (same valid token, no `?pi=`/`?cs=`) | Sensible fallback (bank details or redirect to invoice) | **"This invoice link is invalid or has expired"** — misleading: the token is valid (step 1 proves it); the pay page requires PaymentIntent query params that only exist when the tenant has Stripe Connect (`03-pay-desktop.png`, `04-pay-mobile.png`, QE-W1). Stripe.js still loads; deployed publishable key is `pk_live_…` (live mode) | FAIL (QE-W1) |

Stripe live-mode status: front-end bundle carries a `pk_live_` publishable key; the Payment Element itself was not renderable without a Connect-backed PaymentIntent. No real card payment was attempted.

**Overall: PARTIAL** — invoice token page PASS; card pay BLOCKED by DEFECT-017; bare `/pay/:token` error copy is a defect (QE-W1).
