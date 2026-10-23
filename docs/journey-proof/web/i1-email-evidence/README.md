# I.1 — Outbound email evidence (captured from web-triggered flows)

- **Method:** real emails sent by production (Resend) to a QE-controlled disposable inbox (mail.tm) and to the QE gmail alias; HTML saved verbatim (`.html`) and rendered to PNG at 800px width.
- **Captured:** 2026-10-23, production

| # | Template | Trigger (this run) | Evidence |
|---|----------|--------------------|----------|
| 1 | `quote_ready` | `POST /quotes/{id}/send` (H5) | `01-your-quote-from-shand-1-electrical.png` — contains the `/quote/:token` secure link |
| 2 | `quote_accepted` (customer confirmation) | Accept on `/quote/:token` (H5) | `02-quote-accepted-shand-1-electrical.png` — links to portal `/quotes` |
| 3 | `invoice_sent` | `POST /invoices/{id}/send` (H5b) | `03-invoice-inv-004-from-shand-1-electrical.png` — bank-transfer details; **no card pay link** (tenant has no Stripe Connect — DEFECT-017) |
| 4 | magic link | `POST /customer/auth/magic/request` (E6) | `04-your-sign-in-link-shand-1-electrical.png` — contains `/auth/magic?token=…&next=/quotes` |
| 5 | `account_created` | `POST /customer/register` (E7 setup) | `05-account-created.png` |
| 6 | `password_reset` | `POST /auth/password-reset/request` (H6) | `06-password-reset.png` — contains `/reset-password?token=…` |

Not captured (not reachable from public web flows in this pass): `quote_reminder` / `invoice_reminder` (scheduler cadence), `triage_question` email (guest answered inline before timeout), `booking_confirmed`, `payment_received` (blocked by DEFECT-017), `chat_message`, `email_failure_staff_alert`.

All six captured emails arrived within seconds of their trigger — production email delivery (Resend) is healthy.
