# Alert Runbooks

One runbook per alert, five lines each: what it means / check first / likely
causes / action / escalation. Alerts arrive via Slack webhook + email
(Observability PRD §4.3). Dashboards are T+1 by design — only these alerts
interrupt the day.

## Budget 80% alert (monthly AI budget)

- **Means:** estimated month-to-date AI spend has crossed 80% of the £600 monthly budget.
- **Check first:** per-org cost leaderboard in Metabase — one org or broad?
- **Likely causes:** power-user concentration; retry storm; new feature (chat, intake briefs) driving unpriced volume.
- **Action:** identify the top driver; if a single org, apply cheaper-model routing and note for the monthly review; if broad, re-forecast and flag on Friday one-pager.
- **Escalate:** if projection exceeds 100% of budget before mid-month — founder + lead dev same day; consider tightening burst rate limits.

## Daily-spend-anomaly alert (>3× trailing-7-day mean)

- **Means:** yesterday's AI spend was over 3× the trailing 7-day average — spike, not trend.
- **Check first:** Langfuse traces for the spike window — retries, loop behaviour, token blow-ups.
- **Likely causes:** retry loop on a failing generation; abuse/scraping via intake forms; a runaway scheduled job; a bug multiplying calls per request.
- **Action:** if retry/loop, ship the fix or kill the job; if abuse, apply per-org burst rate limit and block source; log cause in the incident note.
- **Escalate:** if not explained within 4 hours or a second anomaly fires this week — lead dev investigates immediately; P0 if spend is still climbing.

## Fair-use-threshold alert (org crosses threshold)

- **Means:** an org has crossed the fair-use threshold (~3–5× beta p95 AI actions/mo).
- **Check first:** the org's usage pattern — legitimate heavy tradie or scripted/abnormal traffic?
- **Likely causes:** genuine power user; automated misuse; a customer-side flow (intake/chat) generating volume the org didn't ask for.
- **Action:** invisible guardrails only — cheaper-model routing + burst limits. Never block automatically; if restriction is warranted, human review and contact the tradie first (fair-use policy commitment).
- **Escalate:** founder decision before any customer-visible action; recurring crossings by the same org feed the monthly pricing review.

## Rollup-job-failure alert (nightly rollups)

- **Means:** last night's rollup job failed — dashboards are silently stale, not just empty of insight.
- **Check first:** job logs for the failing step (event table read, aggregation, write); confirm whether `ai_call_events` is still growing.
- **Likely causes:** schema drift after a migration; Postgres timeout on event volume; a bad deploy touching the event schema.
- **Action:** re-run the rollup manually after fixing; verify dashboards show yesterday's data; events are fail-open so no data was lost — only the aggregation.
- **Escalate:** if dashboards are stale >48h or the failure recurs after a fix — lead dev; flag on the Friday one-pager, as pricing decisions depend on this data.

## Email-failure staff alert (customer email bounced / failed to send)

- **Means:** a customer-facing email (quote, invoice, reminder, booking confirmation) bounced or failed at send time; the tenant's staff were paged in-app and by email with a "contact them by phone instead" directive (`alert_staff_email_failure`). Two sources feed the same alert: the send-time transport failure hook in `app/email.py`, and the Resend webhook `POST /webhooks/resend` (`email.bounced` / `email.failed`).
- **Check first:** the alert body itself — it carries the error class and, for bounces, the Resend `bounce.type` / `bounce.reason` (SMTP diagnostic); the structured logs `email_failure_alert_raised` and `resend_webhook_processed` carry the same detail, so deliverability incidents are diagnosable without opening the Resend dashboard.
- **Likely causes:** the customer's mailbox is dead or full (hard bounce on one contact); DKIM/SPF/DMARC or domain-reputation trouble on our sending domain (soft bounces across many contacts); a Resend outage or a missing `RESEND_WEBHOOK_SECRET` (the endpoint answers 503 and Resend replays the event).
- **Action:** a single-contact alert needs no platform action — the tradie has already been told to phone the customer. If bounces span contacts, check the sending domain's DKIM/SPF/DMARC setup per `docs/resend-config.md`. Alerts dedupe per (tenant, contact, calendar day), so a repeat page for the same contact means a new day, not a webhook retry loop.
- **Escalate:** if bounces span multiple tenants or the bounce reason points at our domain's authentication or reputation — lead dev same day; deliverability decay silently kills the quote→invoice→paid email loop.

## SMS-failure staff alert (appointment-reminder text undeliverable)

- **Means:** an appointment-reminder SMS to a customer permanently failed, reported by the Telnyx delivery-receipt webhook (`POST /webhooks/telnyx`, `message.finalized` with `sending_failed` / `delivery_failed`); the tenant's staff were paged in-app and by email with a "contact them another way" directive (`app/sms_alerts.py::alert_staff_sms_failure`).
- **Check first:** the alert body and the reminder row's `delivery_status` / `delivery_events` history; the structured logs `sms_failure_alert_raised` and the `telnyx_webhook_*` / `telnyx_receipt_*` events carry the same detail. A `401` on the webhook means `TELNYX_PUBLIC_KEY` is wrong, a `503` means it is unset and Telnyx is replaying events.
- **Likely causes:** the customer's number is dead or a landline (one contact); the Telnyx number/messaging profile lost its sender-ID registration (failures across many contacts); a Telnyx outage.
- **Action:** a single-contact alert needs no platform action — the sweep has already degraded that contact to email, and STOP replies set `sms_opt_out` so they are never texted again. Failures spanning contacts mean check the Telnyx number/profile in Mission Control. Dedupe shares the email-failure ledger: one page per (tenant, contact, calendar day) regardless of channel.
- **Escalate:** if failures span multiple tenants or the messaging profile itself is suspended — lead dev same day; undelivered reminders quietly no-show appointments.
