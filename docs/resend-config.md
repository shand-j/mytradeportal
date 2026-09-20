# Resend setup guide: no-reply vs tenant-branded quotes

The two-address split described here is **implemented** —
`services/api/app/email.py::_resend_from()` picks the From address by send
type (see Step 3). What remains ops-side is domain verification and the
Railway variables.

## Step 1 — Verify domain health in Resend (5 min)

Resend dashboard → Domains → your domain shows Verified (green).
Click it and confirm three records show Valid: DKIM (`resend._domainkey…`),
SPF (`send`), DMARC (`_dmarc`).
If DMARC is missing, add this TXT record at your DNS host:
`_dmarc.<yourdomain>` → `v=DMARC1; p=quarantine; rua=mailto:postmaster@<yourdomain>`.
It protects deliverability of both addresses.

## Step 2 — The two addresses

| Address | Used for | Display name | Reply behaviour |
|---|---|---|---|
| `no-reply@<yourdomain>` | Password resets, account creation, system notifications | My Trade Portal | None — no Reply-To is set |
| `quotes@<yourdomain>` | Quote-ready and invoice emails to customers | `<Tenant business name>` (e.g. `Sparks & Sons <quotes@…>`) | `Reply-To: <tenant's email>` — replies land straight in the electrician's normal inbox |

Key point on replies: customers hit "reply" in their mail client, and the
reply goes to the tenant's real email address via the Reply-To header.
`quotes@` never needs to receive mail, so you don't need a mailbox or inbound
processing for it.

## Step 3 — Railway variables (API service) and the code behind them

- `RESEND_FROM_EMAIL` = `quotes@<yourdomain>` (set to
  `quotes@mytradeportal.co.uk` in production).
- `RESEND_NO_REPLY_EMAIL` = `no-reply@<yourdomain>` — falls back to
  `RESEND_FROM_EMAIL` when unset.
- `RESEND_API_KEY` — keep as-is.
- `RESEND_WEBHOOK_SECRET` — Svix signing secret for `POST /webhooks/resend`;
  bounce/failed events page the electrician to phone the customer instead
  (see `docs/runbooks/alerts.md`). Empty disables the endpoint (it answers
  503 until configured).
- `APP_PUBLIC_URL` — back-office origin only. Customer-facing links never use
  it: portal emails carry magic links on `{slug}.mytradeportal.co.uk`, Stripe
  onboarding returns bounce through `PUBLIC_DOCS_BASE_URL/payments/stripe-bounce`,
  and calendar feeds use `CALENDAR_FEED_BASE_URL`. Do NOT point customer
  journeys at it.

How the code splits senders (already shipped — no change needed): branded
sends (quotes/invoices) pass the tenant's business name as the display name
and go out on `RESEND_FROM_EMAIL` with the tenant's address as Reply-To;
transactional sends (password resets, account mail) pass no display name and
go out as `My Trade Portal <no-reply@…>` with no Reply-To
(`services/api/app/email.py`, config in
`packages/shared/py/mtp_shared/config.py::resend_no_reply_email`).

## Step 4 — Test end-to-end

1. Trigger a password reset from the app → confirm the sender is
   `My Trade Portal <no-reply@…>` and the links work (they resolve on
   `PASSWORD_RESET_BASE_URL`).
2. Send a quote to a customer → confirm the sender is
   `<Business name> <quotes@…>`, then hit reply in the customer inbox and
   verify the compose window addresses the electrician's email.
3. First sends may land in spam while the domain builds reputation — the
   DKIM/SPF/DMARC alignment from Step 1 keeps this minimal.

## Optional later — mail sent directly to quotes@

Only needed if a customer manually writes to `quotes@` instead of replying.
Resend Inbound (webhook) can receive and forward it to the tenant's email.
Skipped for beta — Reply-To covers the real journey.
