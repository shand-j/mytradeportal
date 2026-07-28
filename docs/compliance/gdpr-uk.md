# GDPR Compliance Guide — My Trade Portal V2 (UK)

> **Status:** pre-go-live, production target: tomorrow
> **Scope:** UK field-service management platform for electrical contractors
> **Primary jurisdiction:** United Kingdom (UK GDPR + Data Protection Act 2018)
> **Hosting region:** `europe-west4-drams3a` (Amsterdam) via Railway IaC (`.railway/railway.ts`)

This document is a practical, engineering-facing compliance guide. It maps the My Trade Portal V2 implementation to UK GDPR requirements and lists the exact tasks that must be completed before launch.

---

## 1. Roles and responsibilities

### 1.1 Controller / processor split

| Party | Role | Data | Notes |
|---|---|---|---|
| My Trade Portal V2 operator | **Controller** | Staff user accounts, tenant business data, payment facilitator records, audit logs | Sets retention, security, and processing purposes |
| My Trade Portal V2 operator | **Processor** | Customer (contact) data entered by tenants | Tenants are controllers for their own customer/lead data; the platform processes it only on their instructions |
| Railway | Subprocessor | All application data at rest and in transit | Infrastructure provider |
| OpenAI | Subprocessor | Free-text quote descriptions / site surveys sent to LLM/embedding endpoints | Only for AI-generated quotes; no model fine-tuning on tenant data |
| Paddle | Subprocessor | Payment card tokens, transaction records, customer email | Payments only |

**Action before launch:**

1. Add a Data Processing Addendum (DPA) to the Terms of Service for tenants.
2. Publish a public Privacy Policy and Cookie Policy on the `web` service.
3. Ensure signed DPAs are in place with OpenAI, Paddle, and Railway.

---

## 2. Personal data inventory

The following tables and columns store personal data. The inventory is derived from `services/api/app/models.py`.

### 2.1 Tenant staff users (`users` table)

| Field | Category | Purpose |
|---|---|---|
| `email` | Identity / contact | Authentication, password reset, audit actor |
| `full_name` | Identity | UI display, audit logs |
| `phone` | Contact | Optional staff contact number |
| `password_hash` | Security | bcrypt hash of login password |
| `supabase_uid` | Identity | Optional Supabase Auth linkage |
| `role` | Access control | `admin`, `manager`, `technician` |

### 2.2 Customer / lead contacts (`contacts` table)

| Field | Category | Purpose |
|---|---|---|
| `name` | Identity | Customer display and quote documents |
| `email` | Contact | Quote/invoice delivery, communications |
| `phone` | Contact | Scheduling calls |
| `address`, `postcode` | Location | Site visits, quotes, invoices |
| `notes` | Special category risk | Free-text; may contain health, access, or vulnerability notes. Treat as potentially sensitive. |

### 2.3 Financial and work records (personal data by association)

These tables contain customer-linked business records and free-text fields that may include personal data:

- `quotes` — `description`, `title`, `extra_data`
- `quote_line_items` — `description`
- `bills_of_quantities` — `notes`, `customer_summary_lines`, `regulatory_citations`, `compliance_warnings`
- `boq_line_items` — `notes`, `description`
- `jobs` — `title`, `description`, `notes`, `scheduled_start`, `scheduled_end`
- `appointments` — `title`, `address`, `notes`, `start_at`, `end_at`
- `invoices` — `notes`
- `invoice_line_items` — `description`
- `payments` — `provider_payload` (Paddle transaction metadata)
- `communications` — `subject`, `body`, `provider_message_id`, `channel`
- `reviews` — `comment`, `response`, `rating`, `status`
- `audit_logs` — `payload` (may contain names/emails in snapshots), `actor_id`

### 2.4 MinIO object storage

Uploaded files (photos, PDFs, documents) may contain personal data. They are stored in the `mtp-uploads` bucket. Files are accessed via presigned URLs from the `files` router (`services/api/app/routers/files.py`).

---

## 3. Lawful basis for processing

| Activity | Lawful basis | Rationale |
|---|---|---|
| Staff account creation | Contract / Legitimate interest | Necessary to provide the platform |
| Customer contact storage | Contract (between tenant and their customer) | Tenants need contacts to quote, schedule, invoice |
| Quote, job, invoice records | Contract | Core service functionality |
| Communications logging | Legitimate interest | Customer-service record keeping |
| AI quote generation | Contract / Legitimate interest | Service feature requested by the tenant; data is processed only to generate the specific quote |
| Review collection | Consent | Explicit opt-in required before publishing reviews |
| Marketing / product updates | Consent | Separate opt-in; do not bundle with T&Cs |
| Audit logging | Legal obligation / Legitimate interest | Security, fraud prevention, dispute resolution |

**Action before launch:**

- Add consent checkboxes for review collection and marketing in the React UI (`web/app/src`).
- Persist consent records in the database (suggested new table: `consent_records`).

---

## 4. Data subject rights (DSR)

### 4.1 Right to access (Article 15)

**Current capability:**

- Tenant staff can view individual `contacts`, `quotes`, `jobs`, `invoices`, `communications`, and `reviews` via the FastAPI routers.
- Audit history is available in `audit_logs` (written by `services/api/app/audit.py`).

**Gap:** there is no single “export my data” endpoint for a contact or staff user.

**Recommended implementation:**

```python
# New router: services/api/app/routers/data_subjects.py

@router.post("/data-subjects/export")
async def export_data_subject(
    request: DataSubjectExportRequest,
    tenant: TenantDep,
    current_user: RequireAdminDep,
    db: DbDep,
) -> StreamingResponse:
    """Export all data for a contact across quotes, jobs, invoices, communications, reviews, and files."""
```

The export should be a machine-readable JSON (or CSV) containing all rows where `contact_id` or `user_id` matches, plus a manifest of MinIO object keys. Set `Content-Disposition: attachment` and provide within 30 days.

### 4.2 Right to rectification (Article 16)

**Current capability:** `PATCH /contacts/{id}` and `PATCH /users/{id}` allow updating personal data. All updates are logged to `audit_logs` with `Actions.CONTACT_UPDATED` or similar.

**Action:** ensure the UI exposes the same fields and logs all changes.

### 4.3 Right to erasure (Article 17 — “right to be forgotten”)

**Current capability:**

- `DELETE /contacts/{id}` cascades to `quotes`, `jobs`, `invoices` (via SQLAlchemy `cascade="all, delete-orphan"`).
- `DELETE /users/{id}` removes the staff user but leaves audit logs with `actor_id` set to `NULL`.

**Gaps:**

1. No bulk erasure for a tenant (e.g., when a tenant cancels).
2. No automated erasure of associated MinIO objects.
3. No retention-policy-driven automatic deletion.
4. Payment records in `payments` may retain Paddle `provider_transaction_id` and `provider_payload` for legal/accounting reasons even after contact deletion.

**Recommended commands / scripts:**

```bash
# One-off: erase a contact and all tenant-scoped child records
railway run --service api python -m scripts.erase_contact \
  --tenant-id <uuid> --contact-id <uuid> --actor-id <uuid>

# One-off: erase an entire tenant (DPO-only, after contract termination)
railway run --service api python -m scripts.erase_tenant \
  --tenant-id <uuid> --confirm-irreversible
```

Implement `scripts/erase_contact.py` and `scripts/erase_tenant.py` with `bypass_rls_in_session` (`services/api/app/rls.py:153`) and explicit deletion of MinIO objects.

### 4.4 Right to restrict processing (Article 18)

**Recommended implementation:** add a `processing_restricted` flag on `contacts` and `users`. When set:

- The contact is hidden from quote/job creation UIs.
- Existing records are retained but not used for new processing (e.g., marketing, AI training).
- No data is sent to OpenAI for that contact’s quotes.

### 4.5 Right to data portability (Article 20)

Provide the export described in 4.1 in a structured, commonly used, machine-readable format. JSON is acceptable; CSV is preferable for contact/invoice lists.

### 4.6 Right to object (Article 21)

- Marketing emails: must be one-click unsubscribe; update `users` / `contacts` with `marketing_opt_in = false`.
- Profiling / automated decision-making: AI quote generation is not fully automated decision-making (human review is required before sending), but disclose this in the Privacy Policy.

---

## 5. Retention policy

| Data category | Suggested retention | Rationale |
|---|---|---|
| Draft quotes | 2 years after last update, then delete or anonymise | HMRC / business record keeping |
| Approved quotes / invoices | 7 years (UK tax record requirement) | Legal / tax obligation |
| Contact records | While active + 2 years after last job/invoice, then erasure | Contract + legitimate interest |
| Communications | 2 years | Dispute resolution |
| Reviews | Until consent withdrawn or account closure | Consent basis |
| Audit logs | 7 years | Legal / security |
| Failed login / security events | 1 year | Security monitoring |
| MinIO uploads | Same as parent quote/job/invoice | Delete with parent record |

**Action before launch:**

1. Add `retention_until` or `deleted_at` columns to tenant-scoped tables.
2. Implement a nightly cleanup task (currently `services/worker/` is a placeholder; run as a scheduled Railway job or container cron).
3. Ensure Paddle transaction IDs are retained for 7 years even if contact details are erased.

---

## 6. Security measures

### 6.1 Multi-tenancy and access control

- PostgreSQL Row-Level Security (RLS) enforces tenant isolation at the database layer. Policies are applied to every table in `TENANT_SCOPED_TABLES` (`services/api/app/rls.py:26`).
- Application-layer dependencies (`TenantDep`, `CurrentUserDep`) verify JWT `tenant_id` claims and set `app.current_tenant` per request.
- The application role `mtp_app` cannot bypass RLS.
- Passwords are hashed with bcrypt (`services/api/app/security.py`).
- Session cookies are HTTP-only, Secure, and SameSite (`services/api/app/routers/auth.py`).

### 6.2 Encryption

- All Railway public domains serve HTTPS with managed TLS.
- Postgres and Redis connections use TLS.
- MinIO bucket objects should be encrypted at rest by Railway volume encryption.

### 6.3 Audit and monitoring

- `services/api/app/audit.py` writes immutable `audit_logs` rows for state changes (contact/quote/invoice CRUD, tenant updates).
- Failed logins and sensitive actions are rate-limited via `slowapi` (`services/api/app/limiter.py`).
- Security tests in `security/tests/` cover multi-tenancy and OWASP Top 10.

**Action before launch:**

1. Enable Railway log drains to a SIEM or secure store for 72-hour breach detection.
2. Run `pytest -m security` against production (see `security/README.md`).
3. Verify all services are deployed in the `europe-west4-drams3a` region as declared in IaC.

---

## 7. Subprocessors and international transfers

| Subprocessor | Purpose | Location | GDPR mechanism |
|---|---|---|---|
| Railway | Hosting, Postgres, Redis, volumes | `europe-west4-drams3a` (Amsterdam) | EU GDPR / UK GDPR adequate; DPA required |
| OpenAI | Embeddings and LLM quote generation | United States | Standard Contractual Clauses (SCCs) + UK Addendum; zero-retention API agreement required |
| Paddle | Payment processing | Varies by service | DPA + SCCs |
| Qdrant | Vector storage of cost-item/knowledge embeddings | Railway volume (`europe-west4-drams3a`) | Same as Railway |
| MinIO | Object storage for file uploads | Railway volume (`europe-west4-drams3a`) | Same as Railway |

**Action before launch:**

1. Confirm OpenAI zero-retention API access is enabled for the production account so prompt/embedding data is not used for model training.
2. Keep a current subprocessor list on the public website.
3. Verify all services are deployed in the `europe-west4-drams3a` region as declared in IaC.

---

## 8. AI and automated decision-making

### 8.1 How AI is used

- `POST /quotes/generate` uses Qdrant retrieval + OpenAI LLM + deterministic validation (`services/api/app/rag/`).
- `POST /quotes/generate-boq` with `use_ocerp=true` calls the OCERP microservice (`services/ocerp/`).
- The LLM is only used to parse free text into structured requirements; pricing, compliance, and citations are produced by deterministic Python functions (`services/ocerp/services/agent_graph.py`).

### 8.2 DPIA requirements

A Data Protection Impact Assessment (DPIA) is required because the processing involves:

- Systematic use of customer data (site surveys, addresses) in an innovative AI system.
- Potential impact on individuals (inaccurate quotes could lead to overcharging or unsafe electrical work).

**DPIA must cover:**

1. **Necessity and proportionality:** why AI is needed vs. manual quoting.
2. **Accuracy:** validation layer (`services/api/app/rag/validation.py`, `services/ocerp/services/compliance.py`) and price-floor checks.
3. **Human oversight:** every AI-generated quote is a draft; a staff user must review and approve before it is sent.
4. **Transparency:** Privacy Policy must state that AI is used to generate drafts and how to request human review.
5. **Data minimisation:** only the free-text description and existing cost data are sent to OpenAI; no unnecessary contact fields are transmitted.

**Action before launch:**

- Complete and sign off the DPIA.
- Add an AI disclosure notice in the quote-generation UI.
- Ensure the OpenAI DPA covers UK GDPR SCCs.

---

## 9. Cookies and tracking

**Current state:** the platform uses only HTTP-only session cookies for authentication (`session` cookie set by `/auth/login`). No third-party analytics or advertising cookies are implemented.

**Action before launch:**

1. If Google Analytics, PostHog, or similar are added later, implement a cookie-consent banner before setting non-essential cookies.
2. Document all cookies in the public Cookie Policy.

---

## 10. Data breach response

### 10.1 Detection

- Monitor Railway logs, failed-auth rate limits, and `audit_logs` for anomalies.
- Set up alerts for high volumes of `contact.deleted` or `quote.exported` actions.

### 10.2 Response playbook

1. **Contain** — revoke affected sessions, rotate `AUTH_SECRET_KEY`, disable compromised service accounts.
2. **Assess** — determine affected tenants, data categories, and number of individuals.
3. **Notify** — if a breach is likely to result in risk to rights and freedoms, notify the **ICO within 72 hours** and affected tenants/customers without undue delay.
4. **Document** — record the breach in a secure register (even if not reportable).
5. **Remediate** — patch, rotate secrets, re-run security tests (`pytest -m security`).

**Emergency commands:**

```bash
# Rotate JWT secret (forces all users to re-login)
railway variable set AUTH_SECRET_KEY="<new-strong-random>" --service api --environment production

# Rotate Django admin password
railway variable set DJANGO_SUPERUSER_PASSWORD="<new-password>" --service admin --environment production

# Re-run security tests
source .venv/bin/activate
export SECURITY_API_BASE_URL=https://<api-domain>
export SECURITY_ADMIN_BASE_URL=https://<admin-domain>
pytest -m security -v --no-cov
```

---

## 11. Pre-go-live GDPR checklist

- [ ] Privacy Policy published on `web` service.
- [ ] Cookie Policy published (even if only essential cookies).
- [ ] DPA / Terms of Service updated for tenant controller/platform processor split.
- [ ] OpenAI DPA signed and zero-retention confirmed.
- [ ] Paddle DPA signed.
- [ ] Railway DPA signed.
- [ ] DPIA completed and approved for AI quote generation.
- [ ] Consent tracking implemented for reviews and marketing.
- [ ] Data-subject export endpoint implemented.
- [ ] Contact/tenant erasure scripts implemented and tested.
- [ ] Retention policy documented and nightly cleanup job scheduled.
- [ ] Admin service region reconciled to `europe-west4-drams3a` (Amsterdam).
- [ ] Security tests (`pytest -m security`) run against production and passed.
- [ ] Log drains / alerting configured for breach detection.
- [ ] Staff trained on DSR handling and breach escalation.

---

## 12. Operational commands

### Verify RLS is enabled

```bash
railway run --service api python - <<'PY'
from sqlalchemy import text
from app.database import async_session_maker
import asyncio

async def main():
    async with async_session_maker() as db:
        rs = await db.execute(text(
            "SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(:tables)"
        ), {"tables": ["contacts", "users", "quotes", "invoices"]})
        for row in rs.all():
            print(row)
asyncio.run(main())
PY
```

### Export a contact’s data (after implementing the DSR endpoint)

```bash
curl -X POST https://<api-domain>/data-subjects/export \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -b session=$SESSION_COOKIE \
  -d '{"contact_id": "<uuid>"}' \
  --output contact-export.json
```

### Erase a contact (after implementing the erasure script)

```bash
railway run --service api python -m scripts.erase_contact \
  --tenant-id <uuid> \
  --contact-id <uuid> \
  --actor-id <uuid>
```

### Run dependency audits

```bash
pip-audit --desc --audit-level=high
pnpm audit --audit-level=high
```

---

## 13. Document control

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-24 | Platform team | Initial pre-go-live GDPR compliance guide |

**Review cycle:** every 6 months, or after any major change to data processing, subprocessors, or hosting region.

**Related documents:**

- `AGENTS.md` — architecture and security overview
- `docs/deployment.md` — production deployment and secrets management
- `docs/soc2-controls.md` — SOC2 control mapping
- `security/README.md` — security test framework
- `.railway/railway.ts` — infrastructure as code
