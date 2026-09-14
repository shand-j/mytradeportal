@customer-portal @p0
Feature: Portal arrival, quote request and inline AI triage
  A homeowner arrives at {slug}.mytradeportal.co.uk from a QR code or 6-digit
  code, submits a quote request with no account, gets an inline AI triage
  answer where possible, and is auto-provisioned with a magic-link email.
  Invisible auth per ADR-004 — customers never register.

  Pages: src/portal/pages/CodeEntryPage (/code), PortalHome (quote-request form).
  Endpoints: POST /quote-requests (with entry_channel and sync_check),
  GET/POST /quote-requests/{qr_id}/messages (guest thread),
  POST /quote-requests/{id}/media, POST /customer/auth/magic/request.

  Background:
    Given a tenant with a portal subdomain and branding

  @automated-integration
  Scenario: Arrive via QR code or 6-digit code
    When a homeowner scans the QR on the van/card or enters the 6-digit code on
      www.mytradeportal.co.uk/code
    Then they land on the tenant-branded portal at {slug}.mytradeportal.co.uk
    And the visit is recorded with its entry_channel (qr / code / link)

  @automated-integration
  Scenario: Submit a quote request
    When the homeowner submits the form with name, email, phone, address,
      postcode, property profile, photos, preferred dates and contact preference
    Then POST /quote-requests persists the request and attachments
    And a Customer row is auto-provisioned with no password
    And a magic-link email is sent so every notification deep-links into the portal

  @automated-integration
  Scenario: Inline AI triage asks one follow-up when needed
    Given the intake supports sync_check=true
    When the cheap-model triage decides a follow-up question is needed within 12s
    Then the homeowner answers inline via a guest-scoped thread token (2h TTL,
      single-thread power)
    And the full 60–120s AI draft still runs in the background

  @automated-integration
  Scenario: Triage is fail-open when slow or unavailable
    When the triage call exceeds its budget or the model is unavailable
    Then the form submission succeeds without the inline question
    And the electrician is notified to follow up manually

  @automated-integration
  Scenario: Triage acknowledges detail already provided
    Given the homeowner already answered key questions in the form
    When the AI follow-up fires on a low-confidence first attempt
    Then the question renders provided answers under an already-provided banner
      and never re-asks them (backlog C13)

  @automated-integration
  Scenario: Bot protection on the unauthenticated form
    When the public form is submitted abusively
    Then rate limiting answers 429 without creating quote requests
