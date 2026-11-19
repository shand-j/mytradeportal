# Data retention & tenant offboarding

This document is the retention statement referenced by the tenant-offboarding
flow (`POST /tenants/me/offboard`, implemented in
`services/api/app/routers/tenants.py`). It covers what is kept, for how long,
and what happens when a tenant leaves.

## Offboarding flow

Offboarding is self-service for the tenant's admin (`role=admin`) and requires
an explicit `confirm_slug` body matching the tenant's slug. Tenants are
expected to export their data first via `GET /export/my-data` (the "no
lock-in" export); the offboard response does not include an export.

One transaction performs, in order:

1. **Provider detachment (best-effort).** The Paddle SaaS subscription is
   cancelled with `effective_from=immediately`
   (`app/paddle_client.py::cancel_subscription`) and the local subscription
   row is marked `canceled`. The Stripe Connect Express account is deleted
   via the Stripe API (`app/stripe_client.py::delete_connected_account`) and
   the local `stripe_accounts` row is removed regardless, so an offboarded
   tenant can never take another card payment through the platform. Provider
   outages are logged and never block offboarding — a failed Paddle cancel is
   reconciled by ops from the provider dashboard.
2. **Access revocation.** All staff users and customer accounts are
   deactivated (`is_active=false`). Both JWT validators
   (`app/dependencies.py::get_current_user` / `get_current_customer`) check
   `is_active` on every request, so every previously issued token stops
   working immediately — this is how stateless-JWT "session revocation" is
   implemented. In addition the persisted token families are revoked:
   customer portal magic links (`customer_portal_tokens`), staff invite links
   (`user_invite_tokens`), public quote/invoice document links
   (`document_access_tokens`) and unused password-reset tokens.
3. **Tenant deactivation.** `tenants.is_active=false`, `status="offboarded"`.
   Tenant resolution (`get_current_tenant` / `resolve_tenant`) rejects
   inactive tenants, so the portal subdomain, the public business pages and
   every `X-Tenant-ID`-scoped endpoint stop resolving for the tenant.
4. **PII anonymisation in place.** Personal data is replaced or cleared
   immediately — see below.

## What is anonymised on offboarding

| Data | Treatment |
|---|---|
| Staff users (`users`) | email → `deleted-<id>@offboarded.invalid`, name → "Offboarded user", phone/password hash/Supabase uid cleared, deactivated |
| Customer accounts (`customers`) | email → `deleted-<id>@offboarded.invalid`, name → "Former customer", phone/address/postcode/property profile cleared, password hash + magic-link token cleared, marketing consent off, deactivated |
| CRM contacts (`contacts`) | name → "Former customer", email/phone/address/postcode/notes/site notes cleared |
| Properties (`properties`) | address/postcode replaced, geo + notes cleared, deactivated |
| Communications (`communications`) | subject/body cleared (metadata kept) |
| Quote requests (`quote_requests`) | free-text `raw_text`, `structured_data` and AI summary cleared |
| Jobs (`jobs`) | site address/postcode/geo cleared; title/status/schedule kept |
| Tenant settings | `email`/`phone`/`address`/`postcode` keys removed (branding/pricing kept) |
| Document access tokens | revoked and snapshot `contact_email` cleared |

## What is retained, and for how long

| Record class | Retention | Basis |
|---|---|---|
| Invoices, invoice line items, payments | **6 years** from the end of the financial year they relate to | HMRC record-keeping requirement for UK businesses (VAT/PAYE/corporation tax) |
| Quotes and quote line items (accepted) | 6 years, as supporting evidence for the retained invoices | HMRC |
| Quotes (draft/declined/expired) | 24 months, then deletable | Legitimate interest (pipeline analysis) |
| Audit logs | 6 years | SOC2 / dispute evidence |
| Anonymised operational rows (jobs, appointments, contacts stub rows) | Until hard deletion with the tenant's financial rows | Referential integrity of retained records |
| Staff/customer accounts, credentials, tokens | Anonymised/revoked **immediately** at offboarding | GDPR data minimisation |
| Paddle/Stripe references on retained invoices | Kept (transaction ids are financial records) | HMRC / chargeback evidence |

Hard deletion of the tenant row and its remaining (anonymised) records is an
ops task run after the 6-year financial retention window; `ondelete="CASCADE"`
on the tenant foreign keys removes every tenant-scoped row in one pass.

## Backups

Production database backups (Railway/Postgres snapshots) rotate on a rolling
window and age out within **35 days** of the offboarding date. Because
offboarding anonymises PII in the live database, any backup that still
contains pre-offboarding PII is at most 35 days old; restored copies must be
re-anonymised by re-running the offboard transaction before the database is
used for anything other than disaster recovery. Deleted/anonymised personal
data is therefore unrecoverable from platform backups after the rotation
window.

## Data subject requests (homeowners)

A homeowner's data is controlled by the tenant (the trade business). Erasure
requests from homeowners are handled by the tenant against their own records;
the platform-level equivalent for a whole business is the tenant offboarding
above. The export endpoint doubles as the access-request (DSAR) mechanism for
tenants.
