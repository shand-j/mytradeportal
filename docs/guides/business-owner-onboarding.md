# Business Owner Onboarding Guide

> **Purpose:** Get a new UK electrical trade business set up on My Trade Portal V2, logging in, and issuing their first AI-assisted quote in under 30 minutes.
>
> **Applies to:** Production environment on Railway (`MyTradePortal`, project ID `30feaeee-9464-41ac-9b17-d07ae4cfcd09`).
> **Current production URLs:**
> - Back-office web app: `https://web-production-0919a.up.railway.app`
> - API: `https://api-production-83b8.up.railway.app`
> - Django admin: `https://admin-production-5c08.up.railway.app`

---

## What you are getting

My Trade Portal V2 is an AI-native field-service management platform for UK electricians. Each business runs in its own **tenant**, isolated from every other business by PostgreSQL Row-Level Security (RLS) and application-layer checks.

Your tenant contains:

- **Back-office React app** (`web`) — where you manage customers, quotes, jobs, invoices, calendar, and settings.
- **FastAPI backend** (`api`) — the REST API that enforces tenancy and security.
- **OCERP engine** (`ocerp`) — the deterministic AI/BoQ engine that builds UK electrical quotes from free-text descriptions.
- **Django admin** (`admin`) — staff-level read-only view of your operational data, used by platform administrators for support.
- **Data pipeline** (`data-pipeline`) — keeps the Screwfix cost database and electrical quoting knowledge base up to date.

---

## Before you start

You will need:

1. An email address that will be the **first admin** for your business.
2. A strong password (at least 12 characters; the platform hashes it with bcrypt).
3. Your business name and a short **slug** (lowercase, no spaces, e.g. `acme-electrical`).

The platform administrator creating your tenant will also need these details.

---

## Step 1: Create your tenant

Tenants are created through the Django admin panel. The platform administrator logs in as `superadmin` at:

```text
https://admin-production-5c08.up.railway.app/admin/
```

Then follows these exact steps:

1. Go to **Operations → Tenants → Add**.
2. Enter:
   - **Slug:** your short business identifier (e.g. `acme-electrical`).
   - **Name:** your trading name (e.g. `ACME Electrical Ltd`).
3. Save.
4. Go to **Operations → Users → Add**.
5. Select the tenant you just created, enter the admin email, full name, set **Role** to `admin`, and set a password.
6. Save.

After this, your business exists and your admin account is ready.

> **Why Django admin?** The FastAPI backend intentionally refuses to run the local `seed_admin_user` script in production (`ENVIRONMENT=production`). Tenant creation is gated through the Django admin UI, which is protected by a separate `superadmin` account and only platform administrators can access it. This is enforced by `Settings.validate_production()` in `services/api/app/config.py`.

---

## Step 2: Log in to the back office

Open the back-office app:

```text
https://web-production-0919a.up.railway.app/login
```

1. Enter your **business slug** (e.g. `acme-electrical`).
2. Enter your **admin email** and **password**.
3. Click **Sign in**.

The app sends a session cookie to the FastAPI backend at `https://api-production-83b8.up.railway.app`. The cookie is HTTP-only, Secure, and SameSite, and it carries a JWT whose `tenant_id` claim matches your business. Every subsequent API request includes your tenant ID automatically.

If you cannot log in, check:

- You are using the exact slug, not the business name.
- Caps Lock is off.
- The administrator created the user under the correct tenant.

---

## Step 3: Set up your business settings

After login, go to **Settings** in the sidebar.

Fill in at least:

| Field | Why it matters |
|---|---|
| **Business name** | Appears on quotes and invoices. |
| **Address / phone / email** | Used for PDF headers and customer comms. |
| **VAT number** | The quote/invoice engine uses this to calculate VAT per UK rules. |
| **Hourly labour rate** | Used when the AI quote engine cannot find a fixed price for labour. |
| **Default markup / margin** | Price-floor guardrail for AI-generated quotes. |
| **Paddle settings** | Required only if you want to take card payments through the portal. |

Settings are stored in the `tenants` table and scoped to your tenant via RLS. Other businesses cannot read them.

---

## Step 4: Add your customer database

Go to **Customers → Directory** and click **Add customer**.

You need:

- Name
- Phone and/or email
- Address (used for site visits and quote PDFs)
- Any notes (e.g. access instructions, preferred contact times)

Customer records are stored in the `contacts` table and isolated by `tenant_id`. You can import later via the API if you already have a spreadsheet — ask the platform administrator for the CSV/JSON import command.

---

## Step 5: Create your first AI quote

My Trade Portal supports two quote-generation paths:

1. **OCERP BoQ engine** (recommended for electrical work) — deterministic rules + UK cost database.
2. **In-house RAG engine** — retrieval from Qdrant + LLM generation.

### Option A: OCERP BoQ quote (recommended)

1. Go to **Quotes → New quote**.
2. Select the customer.
3. Enter the job description in plain English, for example:
   > "Replace the consumer unit with an 18-way dual RCD board, add 6 new socket circuits, install LED downlights in kitchen and bathroom, and provide an EICR certificate."
4. Choose **Generate with AI / BoQ**.
5. The OCERP engine (`ocerp` service) will:
   - Parse the description into a structured `SiteSurvey`.
   - Run deterministic requirements (circuit counts, accessory schedules, compliance).
   - Look up material prices from the `cost_items` database.
   - Estimate labour using the UK electrical rules.
   - Return a Bill of Quantities with line items, totals, and compliance citations.
6. Review each line item, adjust quantities if needed, and set your margin.
7. Click **Save draft** or **Send to customer**.

### Option B: Manual quote

1. Go to **Quotes → New quote**.
2. Select the customer.
3. Click **Add line item** manually.
4. Enter description, quantity, material cost, labour cost, and VAT.
5. Save or send.

> **AI guardrail:** The engine validates a minimum margin. If a generated quote falls below your configured floor, it warns you before you send it. Always review AI-generated quotes before sending — the system discloses AI involvement.

---

## Step 6: Convert a quote to a job and invoice

Once a customer accepts a quote:

1. Open the quote and click **Approve**.
2. Click **Create job**. The job appears in **Jobs** and on the **Calendar**.
3. When the work is complete, open the job and click **Create invoice**. The invoice pulls the approved line items and calculates VAT.
4. If Paddle is enabled, the customer can pay through the portal. If not, mark the invoice as paid manually when you receive payment.

Invoice numbers are auto-generated. Audit logs record every status change.

---

## Step 7: Understand the calendar and appointments

- **Calendar** shows jobs, appointments, and availability slots.
- Create an appointment from a job or from the calendar directly.
- Appointments are stored in the `appointments` table and isolated by your tenant.

---

## Step 8: Upload files (photos, certificates, PDFs)

1. Go to **Files** or attach a file directly to a quote/job.
2. The app requests a presigned MinIO upload URL from the API.
3. Upload the file. It is stored in the `mtp-uploads` bucket in MinIO, scoped to your tenant.

Supported uploads include site photos, EICR certificates, and customer-signed quotes.

---

## Security and compliance essentials

| Topic | What you need to know |
|---|---|
| **Tenant isolation** | Your data lives in the same PostgreSQL database as other businesses, but RLS policies plus application checks prevent any tenant from reading another tenant's data. The `mtp_app` database role cannot bypass RLS. |
| **Authentication** | Session cookies are HTTP-only, Secure, and SameSite. JWT tokens include your `tenant_id` and are verified on every request. |
| **Passwords** | Passwords are hashed with bcrypt. The platform cannot read your password. |
| **HTTPS** | All production traffic is served over HTTPS with Railway-managed TLS. |
| **Audit logs** | Every login, quote change, invoice mutation, and customer edit is written to the `audit_logs` table, which is protected by RLS. |
| **SOC2** | The platform is mapped to SOC2 Common Criteria. Evidence tests live in `security/tests/`. |

---

## Known production notes and limitations

- **Region target:** All services are deployed in the `europe-west4-drams3a` (Amsterdam) region via `.railway/railway.ts`, the closest Railway region to the UK market.
- **Paddle payments:** Payment code is wired, but if `PADDLE_API_KEY` and `PADDLE_WEBHOOK_SECRET` are not set, card payments will not be available.
- **Customer PWA / chatbot / worker:** These are placeholders in the codebase (`services/pwa/`, `services/chatbot-widget/`, `services/worker/`). They are not part of the go-live release.
- **OCERP takeoff:** PDF, CAD, and photo takeoff endpoints return HTTP 501. BoQ generation from text is fully functional.

---

## Day-to-day support checklist

| Task | Where to do it |
|---|---|
| Add or deactivate a staff member | Back office → Settings → Users (or ask the platform administrator to use Django admin). |
| Change labour rates or VAT | Back office → Settings. |
| Regenerate an AI quote | Quotes → Open quote → Regenerate. |
| Check audit logs | Ask the platform administrator; they are in the Django admin under **Operations → Audit logs**. |
| Report a bug | Open an issue in the GitHub repository or contact the platform administrator. |

---

## Operational commands for administrators

These commands are for the platform administrator supporting the business owner, not for the business owner to run directly.

### Check service health

```bash
curl https://api-production-83b8.up.railway.app/health
curl https://api-production-83b8.up.railway.app/health/ready
curl https://admin-production-5c08.up.railway.app/health
```

### Create a tenant via API (one-time bootstrap, requires `SETUP_TOKEN`)

```bash
curl -X POST https://api-production-83b8.up.railway.app/tenants \
  -H "Content-Type: application/json" \
  -H "X-Setup-Token: $SETUP_TOKEN" \
  -d '{
    "slug": "acme-electrical",
    "name": "ACME Electrical Ltd",
    "admin_email": "owner@acme-electrical.example.com",
    "admin_password": "<strong-password>"
  }'
```

> Rotate or remove `SETUP_TOKEN` after the first tenant is created.

### Seed the cost database and knowledge base

Run from the `data-pipeline` service:

```bash
railway run --service data-pipeline python -m data_pipeline.load_curated_seed
railway run --service data-pipeline python -m data_pipeline.knowledge_loader
```

These populate the `cost_items` and `quoting_knowledge` Qdrant collections needed for AI quotes.

---

## Next steps

1. Confirm your business slug and admin email with the platform administrator.
2. Log in at `https://web-production-0919a.up.railway.app/login`.
3. Complete **Settings**.
4. Add one customer.
5. Create a test quote, review the AI line items, and either delete it or send it to yourself.
6. Book a 15-minute walkthrough with the platform administrator if anything is unclear.

---

## Related documentation

- [Production deployment guide](../deployment.md)
- [AGENTS.md](../../../AGENTS.md) — full technical architecture
- [SOC2 controls](../soc2-controls.md)
- [Security tests and pen-test framework](../../../security/README.md)
