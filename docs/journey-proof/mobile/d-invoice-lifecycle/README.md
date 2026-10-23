# D1/D2 — Invoice create, send, mark paid (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** D1 create + D2 send fully UI-driven on job `55177aa9-…`. Mark-paid demo uses a separate scratch invoice (`aba10338-…`, INV-006) seeded via API (`POST /invoices` + `/issue` + `/send`) — the mission asked not to touch real payment state on the job's invoice.

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Completed job → "Create invoice" | New-invoice form prefilled from the job's accepted quote | Title, "John Shand", "Build with AI" box prefilled with the quote description, quote line items, "Total as quoted £782.50" — [01-invoice-create-prefilled.png](01-invoice-create-prefilled.png) + [02-invoice-lines-total-as-quoted.png](02-invoice-lines-total-as-quoted.png) | PASS |
| 2 | Tap "Create invoice" | Invoice mirrors quote totals exactly (no re-rounding) | Invoice detail: DRAFT, £782.50, customer + line items, "Send invoice" — [03-invoice-draft.png](03-invoice-draft.png). API: INV-005, total 782.50, `job_id` linked | PASS |
| 3 | Tap "Send invoice" | Status → sent; `invoice_sent` email with pay link + bank details queued | Invoice detail: SENT chip, "Mark as paid" + "Send reminder" — [04-invoice-sent.png](04-invoice-sent.png). API confirms `status: sent` | PASS |
| 4 | Scratch invoice (API-seeded, sent) | SENT detail with "Mark as paid" | [05-scratch-invoice-sent.png](05-scratch-invoice-sent.png) | PASS (API-seeded) |
| 5 | Tap "Mark as paid" | PAID state + payment row | "PAID" chip, green "Payment received — £50.00 paid by John Shand" banner, "View revenue dashboard" / "Send receipt" — [06-invoice-marked-paid.png](06-invoice-marked-paid.png) | PASS |

**Email trigger (D2):** `POST /invoices/{id}/send` sends the `invoice_sent` template (payment-details block from the tenant's bank details + `/pay/:token` link) to the contact email — covered end-to-end by the web wave.

**Observations:**
- Mark-as-paid applies immediately with no confirmation dialog (single tap) — worth a product decision; matches web behaviour.
- Invoice header title is the first line item's description ("Metal consumer unit 10-way…") rather than the job/quote title — cosmetic.
- No card-payment path exercised (Stripe Connect blocked by DEFECT-017 at platform level; see g-settings-sweep/06).
