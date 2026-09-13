# Wave A — Quote-to-cash lifecycle evidence (local stack)

Scripted, reviewable video evidence of the full quote-to-cash lifecycle against
the **local** stack, with every external service mocked. Captured
2026-09-13 on the repo's docker-compose infra (Postgres, Mailpit) plus a local
API instance and the landing dev server described below.

**The story, end to end:** a tradie onboards (`Evidence Electrical`), sends
AI-drafted quotes (LLM mocked by seeding), edits a draft line, sends the quote
(trial extension fires on the 3rd sent AI quote; `quote_sent` outcome event),
the customer opens the secure `/quote/:token` page and accepts via the
homeowner portal (`quote_accepted` outcome event), the tradie converts the
approved quote to a scheduled job and completes it, an invoice mirroring the
quote totals is created and sent, the customer opens `/invoice/:token` and
gets a "Pay this invoice" button backed by a real (stub-destination-charge)
`payment_url`, payment settles via a `payment_intent.succeeded` webhook with a
**genuine HMAC signature**, the invoice page shows paid and the tradie is
notified, then the tradie issues a full refund and the invoice ends `refunded`.

## What is real and what is mocked

| Concern | Status | How |
|---|---|---|
| API code paths | **Real, unmodified** | `app.main:app` runs as-is (tenant onboarding, quotes, sends, customer portal accept, convert-to-job, invoices, public docs, webhook handler, trial extension, telemetry, notifications, audit log). No app source was changed. |
| Database | **Real** | docker-compose Postgres (`mtp` DB), RLS enforced. |
| LLM (Kimi) | **Mocked** | Quotes are seeded through `POST /quotes` with `ai_generated: true` line items; only the funnel `trace_id` (normally minted by the generation path) and the `extra_data.rag` metadata are stamped via SQL. The LLM is never called. |
| Stripe | **Mocked at the client seam** | `app.stripe_client` network functions (PaymentIntent create/retrieve, refund, account retrieve) are monkeypatched in-process by `scripts/stubbed_api.py`. The real destination-charge code in `app/routers/public_docs.py` executes and issues a genuine `/pay/:token?pi=...&cs=...` URL. The tenant's `stripe_accounts` row is seeded directly (normally written by real Connect onboarding). |
| Stripe webhook signature | **Real** | `scripts/replay_stripe_webhook.py` computes a real `t=...,v1=HMAC-SHA256(secret, t.body)` header; verification runs through `stripe.Webhook.construct_event` with a test secret. |
| Email (Resend) | **Mocked transport** | `RESEND_API_KEY` blanked → SMTP fallback to local Mailpit (`:8025`). The branded quote/invoice emails genuinely flow and are captured in `07-mailpit.webm`. |
| Supabase Auth | **Mocked** | Blanked → local bcrypt path (the app's documented dev fallback). |
| Paddle | **Not touched** | Onboarding creates the internal no-card trial row only. |
| `/pay/:token` Stripe.js | **Honest degradation** | The landing app runs **without** `VITE_STRIPE_PUBLISHABLE_KEY`, so `/pay/:token` renders its branded shell + the documented "Card payments aren't available right now" state. The Stripe Payment Element itself cannot be shown without a publishable key and a live Stripe backend. |

### App bugs surfaced while capturing (not fixed — app source untouched)

1. **`app/stripe_client.construct_event` is broken on stripe-python ≥ 15** —
   it ends with `dict(event)`, which raises `TypeError` on SDK 15.x
   (`StripeObject` no longer subclasses `dict`; `.to_dict()` is required).
   The root venv has `stripe==15.6.1` (pyproject pins only `stripe>=10.0.0`).
   `scripts/stubbed_api.py` wraps the function: verification still runs
   entirely through the real `stripe.Webhook.construct_event`; only the return
   shape is adapted. **Follow-up: fix `dict(event)` → `dict(event.to_dict())`
   or pin `stripe<15`.** (The `mtp_api` Docker image doesn't even have the
   `stripe` package installed, so the webhook route would 503 there anyway.)
2. **Local dev schema drift** — the compose Postgres volume predates the
   Stripe/telemetry model revisions (`stripe_accounts` table, several
   `invoices`/`ai_call_events` columns missing). The fail-open telemetry
   writer silently dropped outcome events because of it.
   `scripts/ensure_schema.py` reconciles the local DB **additively**
   (ADD COLUMN / CREATE TABLE IF NOT EXISTS / re-apply RLS policies) — same
   end state as a fresh `scripts/init_db.py` run.
3. Minor: the landing `STATUS_LABELS` map has no `approved` entry, so an
   accepted quote's badge renders lowercase "approved" and the
   "You've accepted this quote" banner (which checks for `accepted`) never
   shows — see `02-quote-accepted.webm`.
4. Cosmetic: on `/invoice/:token` the due-date and paid-date fragments render
   with no separator — "Due by 27 September 2026Paid on 13 September 2026"
   (adjacent JSX fragments in `DocumentShell`, `ViewQuote.tsx`) — visible in
   `05-invoice-paid.webm`.

## Videos

All 1280×720 webm, recorded live (terminal segments show the actual runner
output as it executed, rendered by `scripts/terminal.html` polling the runner
log; browser segments are the real landing pages).

| File | Duration | What it proves |
|---|---|---|
| `00a-terminal-onboarding-quote.webm` | ~25s | Runner steps 1–8: tenant created with 14-day no-card trial → login → branding/VAT/card-payments setup → contact → 3 AI quotes seeded (LLM mocked) → 2 sent (trial counter = 2) → tradie edits a draft line (£1,137.00 → £1,176.00, `quote_lines_edited` training event) → hero quote sent: `quote_sent` outcome event asserted, **trial extension fires** (`trial_ends_at` 14d → 30d, `trial_extended_at` marker), quote email lands in Mailpit, `/public/quote/<token>` verified. |
| `00b-terminal-accept-job-invoice.webm` | ~15s | Runner steps 10–12: customer registers (portal account auto-links to the CRM contact), quote visible as `sent`, customer **accepts** with preferred dates → status `approved`, `quote_accepted` outcome (actor=customer), tradie in-app notification, acceptance email → tradie converts to scheduled job, starts, completes → invoice created from the job mirroring the quote totals exactly → invoice sent, email + token, `/public/invoice/<token>` returns a **payment_url** from the real destination-charge path. |
| `00c-terminal-payment-settled.webm` | ~10s | Runner step 14: `payment_intent.succeeded` webhook replayed with a real HMAC signature → HTTP 200, invoice `paid`/`stripe`/`paid_at`, `payments` row (£1,176.00 GBP completed), `invoice_paid` outcome closes the AI funnel, tradie notification "Invoice paid", public payload flips to paid with `payment_url=null`. |
| `00d-terminal-refund.webm` | ~13s | Runner steps 15–16: `POST /invoices/{id}/refund` (stub refund `re_evidence_stub_0001`) → status `refunded`, audit row, tradie notification → `charge.refunded` webhook replay is an idempotent no-op → funnel summary (`quote_sent`, `quote_accepted`, `invoice_paid` all present for the hero quote's trace). |
| `01-quote-view.webm` | ~17s | Customer opens the emailed `/quote/:token` link: branded "Evidence Electrical" header, "Awaiting response" badge, personalised greeting, all four line items (incl. the edited 5 hr labour line), subtotal £980.00 / VAT £196.00 / **total £1,176.00**, "Reply to your electrician" CTA. |
| `02-quote-accepted.webm` | ~7s | Same page after the customer accepted: badge now "approved". (Shows the minor STATUS_LABELS gap noted above.) |
| `03-invoice-pay-button.webm` | ~15s | Customer opens `/invoice/:token`: branded invoice INV-00x, due date, mirrored line items and totals, and the **"Pay this invoice"** button — rendered only because `payment_url` was issued (Stripe configured + Connect account charges-enabled + card payments on). |
| `04-pay-page-degraded.webm` | ~8s | The button's target `/pay/:token?pi=...&cs=...`: branded "Pay Evidence Electrical — Secure payment" shell with the invoice total, showing the graceful config-error state ("Card payments aren't available right now…") because `VITE_STRIPE_PUBLISHABLE_KEY` is unset — the documented degradation path, honestly captured. |
| `05-invoice-paid.webm` | ~9s | Invoice page after the webhook settled the payment: "Paid on 13 September 2026", **"This invoice is paid — thank you."** banner, Pay button gone. |
| `06-invoice-refunded.webm` | ~7s | Invoice page after the tradie's full refund: "refunded" badge. |
| `07-mailpit.webm` | ~19s | Mailpit inbox proving the lifecycle emails really flowed: quote-ready emails, "Quote accepted — Evidence Electrical" confirmation, "Invoice INV-00x from Evidence Electrical" with the working `localhost:5174/invoice/<token>` view link. |

Still frames of the key states are in `run/screenshots/`.

## Reproducing

Prereqs: docker infra up (`docker compose up -d postgres mailpit`), repo venv
(`.venv`), Node + Playwright chromium (`npx playwright install chromium`),
`psql`, `jq`, `curl`. **Do not** run the docker `mtp_api` seed/LLM flows
concurrently — the capture uses its own API instance on :8100.

```bash
# 1. Start the stubbed-Stripe API (:8100) + landing dev server (:5174).
#    (runs ensure_schema.py first; Ctrl-C stops both)
docs/evidence/wave-a/scripts/start-stack.sh

# 2. In another terminal, run the whole capture (runner segments + browser
#    segments, videos land in docs/evidence/wave-a/):
node docs/evidence/wave-a/scripts/capture.mjs
```

To drive the lifecycle manually without video:

```bash
PAUSE=1 PY=.venv/bin/python bash docs/evidence/wave-a/scripts/lifecycle.sh        # all steps
PAUSE=1 PY=.venv/bin/python bash docs/evidence/wave-a/scripts/lifecycle.sh 1 8    # a range
```

The runner is idempotent: re-runs reuse the tenant/contact/customer, mint
fresh quotes/jobs/invoices each time, and reset the trial-extension marker so
the threshold crossing is genuine on every run. State (ids, document tokens,
pay URL) lives in `run/state.env`.

### The environment the stubbed API runs with

Everything not listed is the compose default. This is the entire mocking
surface (see `start-stack.sh`):

```
ENVIRONMENT=staging
DATABASE_URL=postgresql+asyncpg://mtp:mtp@localhost:5432/mtp
RESEND_API_KEY=                       # -> SMTP to Mailpit :1025
SUPABASE_URL= SUPABASE_ANON_KEY= SUPABASE_SERVICE_ROLE_KEY=
STRIPE_SECRET_KEY=sk_test_evidence_stubbed        # enables the code path only
STRIPE_WEBHOOK_SECRET=whsec_evidence_local_test   # real HMAC target
PUBLIC_DOCS_BASE_URL=http://localhost:5174
ALLOWED_ORIGINS=http://localhost:5174,http://localhost:3000
REMINDER_SCHEDULER_ENABLED=false ROLLUP_SCHEDULER_ENABLED=false
```

The landing dev server is the same Vite app with
`VITE_API_URL=http://localhost:8100` and **no** `VITE_STRIPE_PUBLISHABLE_KEY`.

## Files

```
docs/evidence/wave-a/
├── README.md                     # this file
├── 00a..00d-terminal-*.webm      # narrated runner videos (steps 1–16)
├── 01..07-*.webm                 # browser videos (landing pages + Mailpit)
├── run/
│   ├── lifecycle.log             # full transcript of the captured run
│   ├── state.env                 # ids/tokens from the captured run
│   ├── stack.log                 # stubbed API + Vite logs
│   └── screenshots/              # still frames of key states
└── scripts/
    ├── start-stack.sh            # env + launch stubbed API & landing
    ├── stubbed_api.py            # real app, stripe_client stubs + SDK-15 shim
    ├── ensure_schema.py          # additive local-schema reconciliation
    ├── lifecycle.sh              # narrated, asserting lifecycle runner
    ├── replay_stripe_webhook.py  # real-HMAC Stripe webhook replay
    ├── terminal.html             # live terminal-in-browser page
    └── capture.mjs               # Playwright video orchestrator
```

## Known limitations

- The Stripe Payment Element itself (card fields) cannot be evidenced without
  a publishable key and live Stripe; `04-pay-page-degraded.webm` shows the
  branded shell and the graceful degradation instead — this is deliberate.
- The tradie-side steps are driven via the API (curl) rather than the mobile
  UI; the assertions hit the same endpoints the app calls.
- Emails are captured in Mailpit, not delivered to a real inbox.
- The seeded quotes bypass the retrieval/generation pipeline (`app/rag/`), so
  AI *drafting* quality is not what these videos evidence — the lifecycle and
  outcome funnel are.
