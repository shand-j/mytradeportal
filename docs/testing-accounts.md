# Testing accounts & seeded demo estate

Everything below is created by `scripts/seed_demo_estate.py` against the local
Postgres. **All passwords are `GoLive2026!` — local testing only, never reuse
anywhere else.**

## Seeding / reseeding

```bash
docker compose up -d postgres          # check with: docker compose ps
source .venv/bin/activate
python scripts/init_db.py              # first run only (creates schema + RLS)
python scripts/seed_demo_estate.py
```

The script is **idempotent by wipe-and-reseed**: each demo tenant (identified by
slug) is deleted — the database `ON DELETE CASCADE` removes all of its users,
quotes, jobs, invoices, etc. — and recreated. Re-running always yields the same
counts. Non-demo tenants are never touched.

The script prints the tenant lookup codes (6-digit) at the end; they are
regenerated on every run, so read them from the latest output.

> **Port-5432 caveat (this dev machine):** a Homebrew Postgres also listens on
> `127.0.0.1:5432`, so the default `DATABASE_URL`
> (`postgresql+asyncpg://mtp:mtp@localhost:5432/mtp`) targets the *host*
> Postgres — that is what the locally-run API and tests use, and it is already
> seeded. The `docker compose` Postgres container has been seeded separately
> (schema + data) for the full `docker compose up` stack. On a machine without
> a host Postgres on 5432, the default URL hits the container directly and no
> extra step is needed. To seed a specific target, set `DATABASE_URL` before
> running the script.

## Demo tenants

| Slug | Business | Settings highlights |
|---|---|---|
| `sparks` | Sparks & Sons Electrical | £65/hr labour, 20% markup, £95 min charge |
| `voltworks` | VoltWorks Ltd (Ltd company) | £70/hr labour, 25% markup, £110 min charge |
| `brightsparks` | Bright Sparks London (sole trader) | £75/hr labour, 15% markup, £120 min charge |

## Logins

### Staff — web back-office (`http://localhost:3000`) and mobile trade login

Enter the tenant slug at login if asked (login also resolves by subdomain).

| Tenant | Email | Role |
|---|---|---|
| sparks | `sam@sparksandsons.co.uk` | owner |
| sparks | `danny@sparksandsons.co.uk` | engineer |
| voltworks | `olivia@voltworks.co.uk` | owner |
| voltworks | `marcus@voltworks.co.uk` | engineer |
| brightsparks | `kieran@brightsparkslondon.co.uk` | owner |
| brightsparks | `priya@brightsparkslondon.co.uk` | office_manager |

### Customers — mobile customer login (customer portal)

| Tenant | Email | Name |
|---|---|---|
| sparks | `margaret.holloway@example.co.uk` | Margaret Holloway |
| sparks | `peter.okafor@example.co.uk` | Peter Okafor |
| sparks | `susan.doyle@example.co.uk` | Susan Doyle |
| sparks | `rajesh.patel@example.co.uk` | **Rajesh Patel — showcase lead: completed AI triage chat + converted quote** |
| voltworks | `hannah.sutcliffe@example.co.uk` | Hannah Sutcliffe |
| voltworks | `tom.gallagher@example.co.uk` | Tom Gallagher |
| voltworks | `aisha.rahman@example.co.uk` | Aisha Rahman |
| brightsparks | `freddie.aldous@example.co.uk` | Freddie Aldous |
| brightsparks | `nadia.hussain@example.co.uk` | Nadia Hussain |
| brightsparks | `george.papa@example.co.uk` | George Papadopoulos |

## Seeded data map (identical shape per tenant)

**Quote requests (leads)** — 3 per tenant:

- *New* — status `pending`: "Fuse box keeps tripping…" (web form).
- *In triage* — status `processed`: kitchen downlights + sockets, with a 4-message
  `in_app_chat` thread (customer ↔ AI; AI messages carry
  `ai_metadata = {"complete": false, "confidence": 60}`, so the thread is still open
  for follow-up testing).
- *Converted* — status `converted_to_quote`: consumer unit replacement, linked to
  the AI draft quote below.

**Quotes** — 5 per tenant:

| Title | Status | Notes |
|---|---|---|
| Consumer unit replacement | `draft` | **AI-generated** (confidence 0.87), linked to the converted lead |
| Kitchen downlights and additional sockets | `sent` | **AI-generated** (confidence 0.74) + one manual line added → `ai_feedback.edited=true`, `line_count_delta=1`, `price_drift_pct=12.14` |
| EV charger installation | `approved` | manual quote, linked to the scheduled + in-progress jobs |
| Garden lighting installation | `rejected` | manual quote |
| EICR with minor remedial works | `invoiced` | converted to the paid invoice |

AI quotes carry the full instrumentation shape: `extra_data.rag` (confidence,
warnings, assumptions, notes, `retrieval_status="grounded"`,
`generation_seconds≈8.3`), `extra_data.ai_draft` snapshot, and
`extra_data.ai_feedback` edit metrics — same as the real generate/refine flow.

**Jobs** — 3 per tenant: `scheduled` (EV charger, +4 days), `in_progress`
(EV charger site visit, started today), `completed` (EICR, last week).

**Appointments** — 6 per tenant, spanning this week and next: today (+3h,
linked to the in-progress job), tomorrow, +2 days (cancelled), +3 days,
+8 days (next week), plus a completed one yesterday.

**Invoices** — 3 per tenant: `INV-001` draft, `INV-002` sent (due in 11 days),
`INV-003` **paid** (`paid_at` set, `paid_via="stripe"`, plus a completed Stripe
`Payment` row mirroring the `payment_intent.succeeded` webhook with a
`pi_seed_*` PaymentIntent id). All are linked to their source quote and job.

**Payments (Stripe Connect)** — every seeded tenant also gets a fully onboarded
`StripeAccount` row (`acct_seed_<slug>`, charges/payouts enabled), so the
invoice `payment_url` flow offers card payment exactly as in production.
Receivables are Stripe-only; Paddle is platform subscription billing and never
appears on invoice payments.

**Reviews** — 3 per tenant: ratings 5/4/5, sources `in_app`/`google`, two
`approved` (one with a business response), one `pending`.

**Feature flags** — the `/feature-flags` endpoint is served at runtime from
Railway Signals; there is nothing to seed in the database. Locally
(`RAILWAY_TOKEN` unset) `voice_ai_insights`, `demand_forecasting` and
`external_integrations` all resolve to **OFF** (fail-closed defaults).

## Recommended manual test flows (priority order)

1. **Signup / onboarding of a NEW tenant** — run the onboarding flow end-to-end
   with a fresh business (slug not in the seeded three). Confirms registration,
   tenant provisioning and first-login work without seed help.
2. **Lead → AI quote pipeline** — log in as a seeded customer (e.g.
   `margaret.holloway@example.co.uk`), submit a new quote request, watch the AI
   triage chat (compare with the seeded `processed` thread), then log in as
   staff (`sam@sparksandsons.co.uk`), generate an AI quote from the lead, refine
   it (`POST /quotes/{id}/refine` in the UI), and send it.
3. **Quote → job → calendar → invoice** — approve a sent quote, confirm the job
   appears, check the calendar against the seeded appointments (today/tomorrow/
   next week), then convert the quote to an invoice and compare with seeded
   `INV-001..INV-003` (including the paid one with its Payment row).
4. **Tenant isolation spot-check** — log in as `sam@sparksandsons.co.uk`, note
   the quote/job/invoice lists, then log in as `olivia@voltworks.co.uk` and
   confirm none of the Sparks data appears (and vice versa via the API with a
   mismatched `X-Tenant-ID`, expecting 403).

## Reset

Just re-run `python scripts/seed_demo_estate.py`. To wipe the whole local
database instead: `docker compose down -v` (destroys the container volume) and,
on this machine, drop/recreate the host `mtp` database if you also want the
host Postgres cleared.

## Troubleshooting: "login doesn't work on the mobile app / emulator"

Two gotchas have bitten us:

1. **The API isn't running, or the wrong stack is up.** The mobile e2e suite
   runs its own compose project (`docker-compose.mobile.yml`) and its teardown
   stops the backend. Before testing, run `docker compose up -d` and check
   `curl http://localhost:8000/health` returns 200.
2. **There are two Postgres servers on this machine.** `localhost:5432` is
   claimed by the Homebrew Postgres, so running the seed on the host writes to
   the *host* database — but the Dockerised API uses the *container* database.
   To seed the database the API actually serves:

   ```bash
   docker compose up -d   # api healthy first
   docker compose cp scripts/seed_demo_estate.py api:/app/scripts/seed_demo_estate.py
   docker compose exec -T api python /app/scripts/seed_demo_estate.py
   ```

   Verify with:
   `curl -s -X POST http://localhost:8000/auth/token -H 'Content-Type: application/json' -d '{"tenant_slug":"sparks","email":"sam@sparksandsons.co.uk","password":"GoLive2026!"}'`
   (expect HTTP 200 with an access_token).

The iOS Simulator shares the host network, so `EXPO_PUBLIC_API_BASE_URL=http://localhost:8000`
in `mobile/.env` is correct. On a physical device, use the machine's LAN IP instead.
