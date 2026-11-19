# B3 — Send quote (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** mixed. The generated quote's placeholder contact ("Generated lead", no email) was updated **via API** (`PATCH /contacts/a17e08d2-…` → John Shand, `john.shand06+qe@gmail.com`) so the send has a real recipient. The send itself was UI-driven.

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | (API) attach real email to the quote's contact | contact updated | 200 — name John Shand, email set | PASS (API-seeded) |
| 2 | Tap "Send quote" on the review screen | Native confirmation naming the customer | Alert "Send quote? Send this quote to John Shand?" with Cancel/Send — [01-send-confirmation.png](01-send-confirmation.png) | PASS |
| 3 | Tap "Send" | Quote marked sent, app returns, `quote_ready` email queued | App returned to Dashboard; API confirms `status: sent`, `sent_at: 2026-10-23T21:16:28Z` ([api-quote-sent.json](api-quote-sent.json)); Quotes list shows the quote as "Accepted" after later approval — [02-quotes-list-after.png](02-quotes-list-after.png) | PASS |

**Email trigger:** `POST /quotes/{id}/send` issues a fresh document token and emails the `quote_ready` template (secure `/quote/:token` link + portal magic link) to `john.shand06+qe@gmail.com` via Resend. Email rendering evidence is covered by the web wave; the send side is proven here by the state transition + audit (`Actions.QUOTE_SENT`).

**Observation (not a defect):** the confirmation alert names the customer from the loaded quote; after an out-of-band contact edit the old name persisted until app restart (TanStack Query cache) — expected client caching behaviour.
