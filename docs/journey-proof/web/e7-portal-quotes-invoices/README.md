# E7 — Portal quotes & invoices (authenticated customer)

- **Actor:** customer (homeowner), signed in
- **Surface:** https://shand-1-electrical-lorg9.mytradeportal.co.uk/quotes, `/quotes/:id`, `/invoices`, `/invoices/:id`
- **Auth:** the contact used for the H5 quote/invoice (`qe-web-…@maxxspace.com`) had no customer account, so one was created via `POST /customer/register` (201 — register reuses the CRM contact by email, so the existing quote + invoice linked immediately). Session was also independently proven via the real magic-link flow (see e6-portal-auth, steps 2–3).
- **API verification:** `GET /customer/quotes` → 200 with the accepted quote; `GET /customer/invoices` → 200 with INV-004
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | `/quotes` | Quote list | "Consumer unit replacement — 3-bed semi, Sent 23 October 2026, £625.00, ACCEPTED" (`01-quotes-list.png`) | PASS |
| 2 | `/quotes/:id` | Quote detail with lines + status timeline | Full line items, totals, timeline (Created → Sent to you → Accepted, all 23 October 2026), "Booking request sent" banner, DISCUSS THIS QUOTE + CALL/EMAIL actions (`02-quote-detail.png`) | PASS |
| 3 | `/invoices` | Invoice list | INV-004 listed (`03-invoices-list.png`) | PASS |
| 4 | `/invoices/:id` | Invoice detail + pay path | INV-004 lines/totals, due 6 November 2026; "To pay online, use the secure pay link in your invoice email — or call…" + CALL button (`04-invoice-detail.png`) | PASS with note (QE-W5: copy references a pay link the email didn't contain because the tenant has no Stripe Connect) |
| 5 | Mobile viewport (390x844) | Lists usable on mobile | Renders (`05-quotes-list-mobile.png`) | PASS |

**Overall: PASS**
