@customer-portal @p0
Feature: Portal quotes, decisions and bookings
  The customer reviews quotes on the portal, accepts with preferred dates,
  declines, or asks for changes; acceptance leads to a booking request and a
  booking-confirmed email once the electrician schedules the visit.

  Pages: src/portal/pages/PortalQuotes, PortalQuoteDetail.
  Endpoints: GET /customer/quotes, POST /customer/quotes/{id}/accept,
  POST /customer/quotes/{id}/reject, POST /customer/appointments.

  Background:
    Given a portal customer with at least one sent quote

  @automated-integration
  Scenario: List and view only customer-visible quotes
    When the customer opens the quotes list
    Then GET /customer/quotes returns quotes in the positive allow-list
      of statuses (sent, accepted, …) — never pre-review drafts (backlog C3)

  @evidence-video
  Scenario: View the branded quote
    Then the quote page shows the tenant branding, line items, ex-VAT subtotal,
      VAT and total, and the awaiting-response status
    # docs/evidence/wave-a/01-quote-view.webm (view-only /quote/:token page;
    # portal in-browser accept added after capture).

  @automated-integration
  Scenario: Accept with preferred dates
    When the customer accepts and optionally suggests dates that suit them
    Then POST /customer/quotes/{id}/accept records the acceptance and
      the preferred dates
    And a quote_accepted outcome event (actor=customer) is emitted
    And the tradesperson is notified in-app and by email
    # Lifecycle proven in docs/evidence/wave-a/00b-terminal-accept-job-invoice.webm.

  @automated-integration
  Scenario: Decline a quote
    When the customer declines with a reason
    Then POST /customer/quotes/{id}/reject records the decline and the
      tradesperson is notified

  @automated-integration
  Scenario: Request changes via the quote thread
    When the customer replies "discuss" on the quote
    Then a message lands in the shared thread so the tradesperson can revise
      and resend

  @automated-integration
  Scenario: Booking request to booking-confirmed email
    Given an accepted quote
    When the customer submits preferred dates via POST /customer/appointments
      and the electrician schedules the visit
    Then the booking-confirmed email is sent with a magic link and the claim
      CTA for passwordless customers (email sequence in ADR-004 §4)
    # services/api/tests/test_email_sequence.py (29 tests).
