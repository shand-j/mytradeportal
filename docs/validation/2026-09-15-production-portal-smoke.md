# Production portal smoke — fresh demo tenant (2026-09-15)

**Tenant:** Calder Valley Electrics Ltd (`calder-sparks`, id `0bcafd52-4075-47d1-b48b-d7b4c2aa3b09`, code 034935)
**Staff:** jshand.demo+smoke@gmail.com · **Customer:** Amira Choudhury jshand.demo+customer@gmail.com (both +aliases of the founder inbox; all emails also visible in Resend dashboard)
**API:** api-production-65db.up.railway.app · Raw evidence: `docs/validation/smoke-*.json|html`

## Journey executed

| # | Step | Result |
|---|---|---|
| 1 | Tenant bootstrap via `POST /tenants` + `X-Setup-Token` | ✅ 201, admin user created atomically |
| 2 | Tenant subdomain portal `https://calder-sparks.mytradeportal.co.uk` | ✅ 200 |
| 3 | Public quote intake (contact + full address + property detail + preferred contact) with `sync_check` | ✅ 201 in 3.1s; AI returned a relevant follow-up question + guest thread token |
| 4 | Guest thread reply (thread token auth) | ✅ posted as `customer`; **AI reply timed out after ~20s (`guest_followup_failed`)** — see D2 |
| 5 | Background AI draft (Kimi k2.6) | ✅ ~3 min; 7 grounded lines, sensible units (`hour`/`ea`/`m`), £926.00, 11 estimated hours |
| 6 | VAT for non-registered tenant | ✅ 0% applied on quote **and** invoice (C1 regression stayed fixed) |
| 7 | Send quote → `quote_ready` email | ✅ dispatched (message_id `bc13f114…`) — **but Gmail bounced it within 2s**; bounce webhook → staff alert email fired and was itself processed (see D1) |
| 8 | Magic-link quote view `GET /public/quote/{token}` | ✅ full branded payload; raw tokens are SHA-256-hashed at rest (could not be recovered from DB — verified as a security property) |
| 9 | Token accept + reconfirmed dates | ✅ status `approved`, `accepted_dates` persisted; `quote_accepted` email dispatched |
| 10 | Quote → job conversion with scheduling + notes | ✅ job `7fe6d117` scheduled 22 Sep; notes persisted |
| 11 | Multi-day planner | ✅ unit-verified: 11h → Tue 10h + Wed 1h blocks. Explicit 8h window correctly produced no split (not a defect) |
| 12 | Invoice from job | ✅ total mirrors quote exactly (£926, VAT 0); issue + send → `invoice_sent` email dispatched |
| 13 | Card-payment URL without Stripe Connect | ✅ graceful `payment_url: null` (page shows bank-transfer fallback — correct degradation) |
| 14 | Manual `mark-paid` | ✅ staff notified + `invoice_paid` outcome event recorded — **but no customer confirmation email** (see D3) |
| 15 | Stripe Connect onboarding `POST /payments/connect` | ❌ **HTTP 500** — platform not enrolled in Connect (see D4) |
| 16 | Booking-confirmed email on scheduling | ❌ never sent on create/convert (see D5) |

## Defects found

### D1 (P0) — Customer emails bounce to Gmail; bounce reason not captured
The `quote_ready` email was accepted by Resend then bounced by Gmail 2s later (`email.bounced` webhook → `email_failure_alert_raised` → staff alert dispatched, `alerted=true`). A second untagged bounce followed (likely the staff alert to the same Gmail domain). If Gmail is rejecting our mail, the entire customer email journey is broken in production for the largest consumer mailbox provider.
- **Owner action:** check the bounce reason in the Resend dashboard (Emails → the message → bounce details) — likely DKIM/SPF/DMARC alignment or domain reputation on `mytradeportal.co.uk`.
- **Code gap:** `resend_webhooks.py` logs `event_type` only; the webhook payload's `bounce.type`/`reason` is dropped. Add it to the log + staff alert.

### D2 (P2) — Guest AI follow-up reply times out at ~20s on prod
The customer answered the AI's follow-up question; `guest_followup_failed` TimeoutError logged, no AI reply. Fail-open worked (message stored, no 5xx), but the promised "AI follows up fast" portal experience silently degrades to one-way.

### D3 (P1) — Manual `mark-paid` sends no customer confirmation or review prompt
`payment_received` + review-prompt emails fire only from the Stripe webhook (`stripe_webhooks.py:39-90`). The manual path (`invoices.py:396`) notifies staff and records the outcome event, but the customer hears nothing — yet bank transfer + manual mark-paid will be the dominant payment rail until Connect onboarding is widespread.

### D4 (P0) — Stripe platform not enrolled in Connect; onboarding endpoint 500s
`POST /payments/connect` → Stripe error `req_HKpICiWFsC42x`: *"You can only create new accounts if you've signed up for Connect"* (dashboard.stripe.com/connect). No tradie can onboard to card payments until the platform owner completes Connect signup in the Stripe dashboard. The endpoint also returns a raw 500 instead of a clean error, contradicting the "never a 500" degradation contract in `payments.py`.

### D5 (P1) — `booking_confirmed` email only fires on reschedule, never on first scheduling
`_email_booking_confirmed` has exactly one call site: the job **PATCH** path (`jobs.py:348`). Direct job create and quote→job conversion with a schedule send nothing — despite the module docstring (jobs.py:26) promising the email on create. The main booking flow is exactly the one that misses it.

## Verified-good notes
- Tokens hashed at rest; document tokens rotate (re-send revokes the old link).
- `issue` + `send` did not duplicate the invoice email (single `invoice_sent` event).
- Scheduler tick healthy (`reminder_tick_complete`, 0 errors).
- AI telemetry: draft event attributed (model `openai/kimi-k2.6` visible in logs).
