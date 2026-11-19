# H5 — Quote token page + accept flow (`/quote/:token`)

- **Actor:** homeowner (unauthenticated, via emailed secure link)
- **Setup (API, trade account jshand89@gmail.com, tenant Shand 1 Electrical):** created contact "QE Probe" (`f565fb95-…`), created quote `b19aa7df-…` ("Consumer unit replacement — 3-bed semi", 4 lines, total £625.00), `POST /quotes/{id}/send` → `quote_ready` email received at the contact inbox containing `https://www.mytradeportal.co.uk/quote/hzvwgHzbNHCfTDtkCllezF3Io_XVmD4uKJ8iiJFspcU` (email evidence in `../i1-email-evidence/01-…`)
- **Captured:** 2026-10-23, production, desktop 1440x900 + mobile 390x844

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/quote/:token` (desktop) | Branded quote doc with line items, totals, CTAs | Shand 1 Electrical branded (red), "AWAITING RESPONSE", 4 line items, subtotal £625 / VAT £0 / total £625 (tenant not VAT-registered — 0% rate is correct for this tenant), ACCEPT QUOTE / DECLINE / ASK A QUESTION (`01-quote-desktop.png`) | PASS |
| 2 | Open `/quote/:token` (mobile 390x844) | Same content, usable layout | Renders fully, CTAs stack vertically (`02-quote-mobile.png`) | PASS |
| 3 | Click ACCEPT QUOTE | Acceptance recorded, confirmation | Immediate state change (`03-before-accept.png` → `04-after-accept-click.png`) | PASS |
| 4 | Post-accept state | Accepted badge + confirmation + next step | Green "ACCEPTED" badge; banner "Booking request sent — Shand 1 Electrical will confirm your visit once it's scheduled. We've emailed you a confirmation…"; "CHOOSE YOUR PREFERRED VISIT DATES" CTA appears (`05-accept-confirmation.png`). `quote_accepted` confirmation email received (see `../i1-email-evidence/02-…`) | PASS |
| 5 | Click CHOOSE YOUR PREFERRED VISIT DATES | Availability calendar | "When suits you? Pick up to 3 dates — the calendar shows when Shand 1 Electrical is free", Mon–Sun grid with availability states, legend "partly booked · greyed-out days are fully booked or not working days" (`06-date-preference-ui.png`) | PASS |
| 6 | Pick 2 dates (Sat 24 Oct, Sun 25 Oct) + SEND MY PREFERRED DATES | Preferences submitted | "Your preferred visit dates: 1. Sat 24 Oct, 2. Sun 25 Oct — Shand 1 Electrical will confirm which of these works" persisted (`07-dates-selected.png`, `08-dates-submitted.png`) | PASS |

Notes:
- The duplicated nav bar mid-page in `05`/`08` is a full-page-screenshot artifact of the sticky header, not a layout bug.
- DECLINE and ASK A QUESTION were not exercised to keep the quote in the accepted state needed for the invoice journey.

**Overall: PASS**
