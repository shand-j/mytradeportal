# I — System integrations (wave 3, captured 2026-10-24)

Integration-level evidence: remaining outbound email templates, webhook ledgers,
and observability wiring. Email captures use a QE-controlled disposable inbox
(mail.tm, no-auth HTTP API) as the customer email, with the raw HTML saved and a
Playwright render alongside.

## I.1 Outbound email — remaining templates (`email-wave3/`)

Prod sends via Resend from `quotes@mytradeportal.co.uk` /
`no-reply@mytradeportal.co.uk` (tenant-branded From name + tenant Reply-To).

| Template | Trigger used | File | Result |
|---|---|---|---|
| `triage_question` | Portal quote request `B48C3E89` ("Electrics are acting up.") → auto-draft + staff `POST /communications/{qr}/ai-followup` | `triage_question_1.html/.png`, `triage_question_2.html/.png` | PASS — captured via BOTH paths: the low-confidence auto-draft (`start_ai_triage`) and the staff AI-followup endpoint. Both carry the magic-link "Reply in chat" CTA into the portal thread |
| `booking_confirmed` | `POST /jobs` with `scheduled_start`/`scheduled_end` for the QE contact | `booking_confirmed.html/.png` | PASS — date/time window/address/tradesperson block + "Create your account" claim CTA (passwordless auto-provisioned customer) |
| `chat_message` | Staff `POST /communications` (`channel=in_app_chat`, `quote_request_id=…`) | `chat_message.html/.png` | PASS — message preview + magic-link "Reply in the portal" CTA |
| `payment_received` | `POST /invoices` → `/issue` → `/send` → `/mark-paid` (non-card path, `card_payment=False`) | `payment_received.html/.png` | PASS — invoice/amount/date block. The card variant only differs in copy; the Stripe-mediated path remains gated by live-Stripe F6 |
| `invoice_sent` | same invoice INV-008 send step (re-captured; web wave already had this template) | `invoice_sent_INV-008.html/.png` | PASS |
| `quote_reminder` | — | — | **NOT-CAPTURABLE today.** No manual send endpoint exists; the in-process scheduler (`scheduler.py`, tick 3600s, enabled by default) requires a sent-but-unanswered quote ≥ `quote_reminder_interval_days` (default 3) old. The only sent quote in prod is <24h old, and prod DB access for this pass was read-only, so eligibility could not be forced. Code path documented; `reminders` ledger table is empty as expected (`webhooks/reminders-ledger.txt`) |
| `invoice_reminder` | — | — | **NOT-CAPTURABLE today.** Same reasoning: first reminder fires `invoice_reminder_interval_days` (default 7) after due date; no invoice is old enough |
| `email_failure_staff_alert` | not re-triggered | — | **PASS by prod evidence, not re-triggered.** The path has already fired in prod: `email_failure_alerts` holds 5 rows (`webhooks/resend-bounce-staff-alerts.txt`) — 2 Resend-webhook `bounce` rows (2026-09-14/15) and 3 send-time `HTTPStatusError` rows, one with purpose "quote reminder". Code path: send-time failures hook `alert_staff_email_failure` from `send_customer_email`; Resend `email.bounced`/`email.failed` webhooks resolve the `mtp_tenant`/`mtp_contact` tags into the same helper; dedupe is one alert per (tenant, contact, day); staff alert mail deliberately uses plain `send_event_email` so alerts cannot loop |

`email-wave3/manifest.json` records subject/from/to/date per captured email.

## I.3 Webhooks (`webhooks/`)

Evidence is the API's `processed_webhooks` idempotency ledger (prod DB, read-only
psql via Railway proxy). No webhook UI exists, so query output is committed as text.

- `webhook-summary.txt` — 120 processed events total: **113 Paddle** + **7 Stripe**,
  grouped by provider/event type with first/last seen.
- `stripe-events.txt` — 5 × `payment_intent.succeeded` (2026-09-15 → 2026-10-08;
  the 2026-10-08 event `evt_3UOKUI5pCtc1F7Y71IEGgIS3` corresponds to Payment row
  `pi_3UOKUI5pCtc1F7Y714AqdL2D` settling INV-001) and 2 × `account.updated`
  (2026-10-23 23:31, from the wave-2 Connect onboarding attempts).
- `paddle-events-recent.txt` — Paddle sandbox subscription lifecycle
  (`subscription.created/trialing/activated/updated/canceled`,
  `transaction.paid/billed/completed/canceled`), most recent 2026-10-24 00:51 —
  i.e. sandbox webhook deliveries are being signed, verified and processed in prod.
- `resend-bounce-staff-alerts.txt` — the Resend webhook surface: only
  `email.bounced`/`email.failed` are handled (Svix signature verified,
  5-minute timestamp tolerance, untagged events acked as no-op 200); there is no
  delivery ledger by design, so bounce evidence lives in `email_failure_alerts`.
- `reminders-ledger.txt` — `reminders` table count (0) supporting the
  NOT-CAPTURABLE call on reminder emails above.

## I.5 New Relic

Dashboard access was not available, so verification is configuration + code:

- Prod env vars set on both services: `NEW_RELIC_LICENSE_KEY` +
  `NEW_RELIC_APP_NAME=mytradeportal-api` (api) / `=mytradeportal-admin` (admin).
- Both Dockerfiles wrap the server process:
  `newrelic-admin run-program uvicorn app.main:app …` (`services/api/Dockerfile:29`)
  and `newrelic-admin run-program gunicorn admin_project.wsgi …`
  (`services/admin/Dockerfile:23`).
- `newrelic>=9.0.0` is a declared dependency (root `pyproject.toml` for the API,
  `services/admin/requirements.txt` for the admin), so `newrelic-admin` is present
  in both images and the agent initialises at process boot.
- Boot-time agent registration lines are outside the `railway logs` tail window;
  APM data receipt itself is only confirmable from the New Relic UI (owner action).
