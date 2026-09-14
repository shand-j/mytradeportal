# ADR-004: Tenant-Subdomain Customer Portal with Invisible (Magic-Link) Auth

- **Status:** Accepted
- **Date:** 2026-09-14
- **Supersedes:** the `/t/{org_slug}` vanity-URL approach in `docs/mytradeportal-research/PRD-Customer-Portal.md` (§3.1)
- **Related:** ADR-002 (web-first portal), ADR-003 (Stripe Connect payments)

## Context

The pack specified tradie-scoped vanity URLs (`mytradeportal.co.uk/t/{org_slug}`) as the portal entry. Product review before beta concluded the portal needed to be a **full customer back office**, not just an intake surface: customers must view/accept/discuss quotes, submit and track bookings, pay invoices, and receive every notification as a deep link — with **zero registration friction** (occasional users; a homeowner needs an electrician once a decade). Subdomains give each tradie a branded, bookmarkable home (`{slug}.mytradeportal.co.uk`) that also carries their logo/colours, hosts their customers' password reset, and keeps every emailed link obviously "from" the tradie's business.

## Decision

1. **Per-tenant subdomains** — `{slug}.mytradeportal.co.uk` served by the existing landing app (single bundle, host-aware: www/apex = marketing, `{slug}` = portal). A wildcard custom domain on Railway + wildcard DNS at Hostinger; tenant resolution API-side already existed via Host header.
2. **Invisible auth** — customers never register. `Customer` rows are auto-provisioned at quote-request intake (email required on the portal form, no password). Every customer email carries a **magic link** (`CustomerPortalToken`, SHA-256 at rest, 30-day TTL, revocable, reusable) that exchanges for a customer JWT at `/auth/magic`. Password register/login stays for app users; registering against a passwordless auto-provisioned account *claims* it (sets password) instead of 409ing.
3. **Fast inline AI check** — intake supports `sync_check=true`: one bounded cheap-model call (≤12s, fail-open) decides if a follow-up question is needed; if so the customer answers inline via a **guest-scoped thread token** (2h TTL, single-thread power). The full 60–120s draft still runs in background.
4. **Email sequence is the interface** — quote ready → acceptance/pending-booking → booking confirmed (on electrician scheduling) → invoice → payment received + review prompt (tenant's `review_url`, configured in onboarding). Primary CTA is always the magic link; view-only doc-token links remain as secondary fallback.

## Consequences

- Railway plan must allow ≥3 custom domains on the landing service (wildcard + www + apex) — Hobby's 2-domain limit is exceeded; Pro upgrade or apex consolidation required.
- CORS accepts `https://*.mytradeportal.co.uk` via origin regex.
- `PORTAL_BASE_DOMAIN` + `app/portal_links.py` build all customer-facing URLs per tenant; `PUBLIC_DOCS_BASE_URL` remains for legacy token pages.
- Reserved-slug blocklist protects platform hosts (www/api/admin/…).
- Emailed links are tenant-scoped and revocable; sessions expire in 30 days with a self-serve "email me a new link" path.
- The pack's portal PRD §3.1 (vanity URLs, QR → vanity) should be read with subdomain URLs substituted; QR codes now encode `https://{slug}.mytradeportal.co.uk`.
