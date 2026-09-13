# ADR-002 — Web-first customer portal (no app install on the customer path)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-13 |
| **Reference** | [docs/mytradeportal-research/PRD-Customer-Portal.md](../mytradeportal-research/PRD-Customer-Portal.md) |

## Context

Customers of a tradesperson are occasional users — they interact a handful of
times per job (submit a request, answer triage, view a quote, pay an invoice).
Every install step on that path is drop-off. The iOS app is the tradesperson's
tool; making customers install it would put an App Store visit in the middle of
the tradie's revenue flow.

## Decision

- The customer portal is **web-first (PWA)**. No app install exists anywhere on
  the customer critical path.
- **QR codes, vanity URLs, and 6-digit codes never route to an app store** —
  they open the web portal directly.
- Authentication is **magic links** (plus progressive registration) — no
  password ceremony for occasional users.
- An **app-store path exists only for repeat customers** (landlords, property
  managers) for whom an installed app genuinely earns its place; it is offered
  as an upgrade, never a requirement.

## Consequences

- Customer-facing surfaces (quote view, invoice view, intake form, chat) must
  work as responsive web pages with tradie branding.
- Install prompts (PWA) are measured but never gated on.
- Requests to require an app install for any customer flow are closed against
  this ADR unless conversion evidence challenges web-first (see
  Backlog-Management, locked-decision filter).
