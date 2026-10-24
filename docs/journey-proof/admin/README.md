# G — Django admin journeys (wave 3, captured 2026-10-24)

Screenshot-proven pass over the production Django admin
(`https://admin-production-d0f5.up.railway.app/admin/`, Railway `admin` service),
superuser `admin_john`, Playwright Chromium at 1440x900.

Registrations under test (`services/admin/operations/admin.py`): Tenant, Contact,
Customer, User (all `TenantScopedAdminMixin`), Quote (+QuoteLineItem inline), Job,
Appointment, Invoice (+InvoiceLineItem +Payment inlines), Payment, Communication,
CostItem, AuditLog, AiRollupUserDay, AiRollupOrgDay, AiCallEvent.

| Step | Expected | Observed | Result | Evidence |
|---|---|---|---|---|
| G-0 Login | `/admin/login/` authenticates superuser, lands on admin index | Login OK; index lists all 15 registered models | PASS | `01-login.png`, `02-admin-index.png` |
| G-a1 Tenant lookup | Changelist of all tenants with search + `is_active`/`paddle_sandbox` filters | 14 tenants listed (incl. QE wave tenants from waves 1–2) | PASS | `03-tenant-list.png` |
| G-a2 Tenant detail | Shand 1 Electrical change form: slug, onboarding progress JSON, VAT flag, quote defaults | All fields render; onboarding_progress JSON shows tax/branding/services/compliance completion | PASS | `04-tenant-detail-shand.png` |
| G-a3 Cross-tenant scoping | Support ops can pivot between tenants' data | **Documented accurately:** `TenantScopedAdminMixin` adds `list_filter=("tenant", "status")` + tenant search — it does NOT override `get_queryset`; the superuser sees every tenant's rows and narrows via the filter sidebar. Filtering Quotes by "Calder Valley Electrics Ltd" narrows 41 → 1 row. True isolation is enforced at the API/RLS layer, not in Django admin | PASS (as designed) | `05-quote-list.png`, `05b-quote-list-filtered-tenant.png` |
| G-b1 Quote drill-down | Quote change form with QuoteLineItem inline (description/qty/unit price/total, total read-only) | Quote "Consumer unit" (draft, AI-generated) shows tenant, contact, AI `extra_data.rag` notes, and the line-item inline with rows and computed totals | PASS | `06-quote-detail-lines.png` (full page) |
| G-b2 Invoice + payment inlines | Invoice change form with InvoiceLineItemInline and PaymentInline | INV-006 (paid) shows line items inline and Payments inline. **QE-I-1:** the Payments inline is EMPTY because `POST /invoices/{id}/mark-paid` (`paid_via="manual"`) never writes a `payments` row — only Stripe-webhook settlements do (INV-001 has `pi_3UOKUI5pCtc1F7Y714AqdL2D`). Manual settlements are only evidenced by `invoice.paid_at` + the `invoice.paid` audit row | PASS with defect QE-I-1 | `08-invoice-detail-inlines.png` (full page), `09-payment-list.png`, `07-invoice-list.png` |
| G-e AuditLog review | Read-only audit trail; find today's QE activity | `tenant.created` filter shows 14 rows incl. "QE Wave2 Electrical" (23 Oct 22:22, wave-2 onboarding) and "Shand 1 Electrical" (19 Sep); unfiltered list shows today's `quote.generated` / `contact.updated` rows from wave-3 API activity | PASS | `10-auditlog-list.png`, `10b-auditlog-tenant-created.png`, `11-auditlog-detail.png` |
| G-d AI cost rollups | Per-user/org daily AI spend review | `AiRollupUserDay`: 42 rows for Shand 1 Electrical, per-feature (quote_draft/quote_refine/triage_followup/intake_triage/outcome) with generations + cost_gbp + p95 latency. `AiRollupOrgDay` equivalent per org. `AiCallEvent`: raw events, today's wave-3 traffic visible (`triage_followup` on gpt-4o-mini ≈ $0.0002, `quote_draft` on openai/kimi-k2.6 ≈ $0.011, 44–72s latency) | PASS | `12-ai-rollup-user-day.png`, `13-ai-rollup-org-day.png`, `14-ai-call-event-list.png`, `15-ai-call-event-detail.png` |
| G-f Communications log | Chat/email communication rows per tenant | 26 rows; today's wave-3 threads visible (in_app_chat inbound/outbound) | PASS | `16-communication-list.png` |

## Notes

- Read-only enforcement: AiRollup*/AiCallEvent admins deny add/change; AuditLog is
  described as read-only in code (its admin still shows an "Add audit log" button —
  cosmetic, no permission plumbing issue found on the read path).
- The AiCallEvent changelist renders `Select ai call event to view` (view-only),
  confirming the read-only permission overrides work.
- AI event detail (`15`) carries full telemetry: tenant/user ids, model, token
  counts, est_cost_usd, cost_gbp, fx_rate + fx_rate_date, latency, status,
  trace_id, prompt_version, confidence, retrieval_status.
