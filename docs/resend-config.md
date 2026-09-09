Resend setup guide: no-reply vs tenant-branded quotes
Step 1 — Verify domain health Resend (5 min)
Resend dashboard → Domains → your domain shows Verified (green).
Click it and confirm three records show Valid: DKIM (resend._domainkey…), SPF (send), DM (_dmarc).
If DMARC is missing, add this TXT record at your DNS host: _dmarc.<yourdomain> → v=DMARC1; p=quarantine; rua=mailto:postmaster@<yourdomain>. It protects deliverability of both addresses.
Step 2 — Decide the two addresses
Address	Used for	Display name	Reply behaviour
no-reply@<yourdomain>	Password resets, account creation, system notifications	My Trade Portal`	None — do not set Reply-To
quotes@<yourdomain>	Quote-ready and invoice emails to customers	<Tenant business name> (e.g. Sparks & Sons <quotes@…>)	-To: <tenant's email> — replies land straight in the electrician's normal inbox
Key point on replies: customers hit "reply" in their mail client, and the reply goes to the tenant's real email address via the Reply-To header. quotes@ never needs to receive mail, so you don't need a mailbox or inbound processing for it. This is already wired in /api/app/routers/quotes.py:252 and invoices.py:278 — what's missing is only the split From-address.

Step 3 — Set Railway variables (API service)
RESEND_FROM_EMAIL = quotes@yourdomain> (currently onboarding@resend.dev — change this)
RESEND_NO_REPLY_EMAIL = no-reply@<yourdomain> (new variable — requires the small code change below to take effect)
RESEND_API_KEY — keep as-is
APP_PUBLIC_URL — already set; password-reset links use it. Currently points at the Railway admin URL, which works, but point it at your real domain later for cleaner links.
Step 4 — Code change (required, not yet in the repo)
Today services/api/app/email.py:_resend_from() uses one global address for everything, and password resets are even tenant-branded with the tenant as Reply-To (auth.py309-318). Needed:

Add resend_no_reply_email to mtp_shared/config.py next to resend_from_email.
In email.py, choose the From address by send type: branded sends (quote/invoice which pass from_name) → quotes@; transactional sends (password reset) → no-reply@ with no Reply-To.
In auth.py, drop the tenant branding/reply-to on reset emails so they come from My Trade Portal <no-reply@…>.
Step 5 — Test end-to-end
Trigger a password reset from the app → confirm sender is My Trade Portal <no-reply@…>, links work.
a quote to a customer → confirm sender is <Business name> <quotes@…>, then hit reply in the customer inbox and verify the compose window addresses the electrician's email.
First sends may land in spam while the domain reputation — DKIM/SPARC alignment from step 1 keeps this minimal.
Optional later — mail sent directly to quotes@
Only needed if a customer manually writes to quotes@ instead of replying. Resend Inbound (webhook) can receive and forward it to the tenant's email. Skip for beta — via Reply-To cover the real journey.

