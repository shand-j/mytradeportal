@tradie @p0
Feature: Invoicing and card payments
  Completed work becomes an invoice. Invoices created from a quote mirror its
  totals exactly; scratch invoices are rounded once at creation. With Stripe
  Connect the tradesperson can take card payments per invoice, and refunds
  flow back through webhooks.

  Screens: mobile/src/screens/trade/InvoiceCreateScreen, InvoiceDetailScreen,
  PaymentsSettingsScreen, PaymentDetailsSettingsScreen. Endpoints:
  POST /invoices, POST /invoices/{id}/send, POST /invoices/{id}/mark-paid,
  POST /invoices/{id}/refund, POST /payments/connect, PATCH /invoices/{id}
  (card-payments toggle), POST /webhooks/stripe.

  Background:
    Given an onboarded tradesperson

  @automated-integration
  Scenario: Invoice created from a job mirrors the accepted quote exactly
    Given a job created from an accepted quote
    When the tradesperson creates an invoice from the job
    Then subtotal, VAT, total and rounding_adjustment match the quote exactly
      and are never re-rounded (rounding rules in AGENTS.md)
    And POST /invoices resolves the quote from job.quote_id when only job_id is sent

  @automated-integration
  Scenario: Quote-less job flows through the AI invoice-create page
    Given a job with no quote attached
    When the tradesperson chooses to invoice it
    Then the AI create-invoice page drafts editable lines and the CTA creates
      the invoice and lands on the send page (backlog N19)
    # e2e group E in mobile/e2e/regression.spec.ts (needs the invoice-create step).

  @evidence-video
  Scenario: Send an invoice by email
    Given a draft invoice
    When the tradesperson sends it
    Then POST /invoices/{id}/send emails the customer a branded invoice with a
      magic link and view-only token fallback
    And the email includes the configured bank payment details (backlog N27)
    # docs/evidence/wave-a/00b-terminal-accept-job-invoice.webm + 07-mailpit.webm.

  @manual
  Scenario: Connect a Stripe Express account
    When the tradesperson starts Stripe Connect from Payments settings
    Then POST /payments/connect returns the Express onboarding link
    And completing onboarding stores the charges-enabled account
    # ADR-003 — requires live Stripe keys; not covered by local automation.

  @automated-integration
  Scenario: Toggle card payments per invoice
    Given the tenant has a charges-enabled Stripe Connect account
    When the tradesperson disables card payments on one invoice
    Then the customer payment page for that invoice offers no card option
      while other invoices still do

  @evidence-video
  Scenario: Refund a paid invoice in full
    Given an invoice settled by card
    When the tradesperson issues a full refund via POST /invoices/{id}/refund
    Then the invoice becomes refunded, an audit row and staff notification are written
    And the replayed charge.refunded webhook is an idempotent no-op
    # docs/evidence/wave-a/00d-terminal-refund.webm, 06-invoice-refunded.webm.

  @automated-integration
  Scenario: Bank transfer payments are marked paid manually
    Given a sent invoice paid by bank transfer
    When the tradesperson marks it paid
    Then POST /invoices/{id}/mark-paid settles the invoice without Stripe
