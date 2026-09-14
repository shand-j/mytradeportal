@platform @p2
Feature: Parked and specified-not-built capabilities
  Journeys that are specified but not built (or only partially built). Each
  scenario is tagged @gap and cites its spec location. These exist so coverage
  tooling and planning can see the delta between spec and implementation —
  none of them should be asserted in CI until un-parked.

  @gap
  Scenario: Email bounce or send failure alerts staff with a phone fallback
    # Founder rule: when a customer email bounces or fails to send, the
    # electrician is told in-app and directed to phone the customer instead.
    # Status: implementation INTERRUPTED mid-flight — untracked, uncommitted,
    # untested code exists in services/api/app/email_alerts.py (design
    # docstring is the spec) and services/api/app/routers/resend_webhooks.py
    # (Svix-verified POST /webhooks/resend, per-day dedupe ledger in
    # email_failure_alerts). Router is wired in app/main.py but no tests exist.
    Given a quote-ready or reminder email to a customer
    When the Resend send raises, or an email.bounced / email.failed webhook arrives
    Then staff receive one alert per tenant+contact+day naming the failed email
      and directing them to the customer's phone number
    And alerts never raise and cannot loop (staff mail skips the failure hook)

  @gap
  Scenario: Installable portal PWA
    # Spec: docs/mytradeportal-research/PRD-Customer-Portal.md §4;
    # beta-backlog row S4 (planned, post-beta-start).
    Given a portal customer on a mobile browser
    Then the portal is installable to the home screen as a PWA

  @gap
  Scenario: Embeddable quote-request widget on the tradie's own website
    # Spec: PRD-Customer-Portal.md §4.1–4.2; beta-backlog row S4.
    Given a tradesperson with their own website
    Then they can embed a quote-request widget that feeds the same intake pipeline

  @gap
  Scenario: QR asset pack for vans, cards and stickers
    # Spec: PRD-Customer-Portal.md §4.1; beta-backlog row S4.
    # (In-app QR modal with portal URL + native share is built — ae1f3a6 —
    # but printable asset packs are not.)
    Then the tradesperson can download print-ready QR assets encoding
      https://{slug}.mytradeportal.co.uk

  @gap
  Scenario: Xero / QuickBooks sync
    # Spec: Delivery-Plan-Pre-Beta-to-Launch.md Phase 1;
    # PRD-Pricing-and-Billing.md §2 (Tradify parity) — planned on all tiers.
    Then invoices and payments sync to the tenant's accounting package

  @gap
  Scenario: Deposits and partial payments
    # Spec: F6/F7 in beta-backlog research alignment; PRD-Pricing-and-Billing.md
    # §2 (Pro gate) — planned.
    Then a quote can request a deposit and invoices can be paid in part

  @gap
  Scenario: Electrical certificates (EICR and friends)
    # Spec: F8 in beta-backlog research alignment; PRD-Pricing-and-Billing.md §2.
    # Status: mobile UI PROTOTYPE ONLY — CertificateScreen, CircuitFormScreen
    # and src/lib/certificates are client-side; there is no API router, no
    # persistence and no PDF issuance.
    Then the tradesperson can issue a certificate against a completed job

  @gap
  Scenario: Offline mode
    # Spec: F9 in beta-backlog research alignment; PRD-Pricing-and-Billing.md §2.
    Given no network connectivity
    Then the tradesperson can view recent jobs and queue edits for sync

  @gap
  Scenario: Multi-user teams with roles
    # Spec: Team tier in plans.py / PRD-Pricing-and-Billing.md §2 — jobs
    # already carry an assignee, but invitations, roles and permissions are
    # not built.
    Then a Team-tier tenant can invite staff with role-scoped permissions
