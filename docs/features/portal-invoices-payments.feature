@customer-portal @p0
Feature: Portal invoices and card payment
  The customer views invoices on the portal, pays by card through Stripe
  (destination charge to the tradesperson's Connect account), and receives a
  payment-received email with the review prompt. View-only /invoice/:token
  pages remain as the secondary fallback.

  Pages: src/portal/pages/PortalInvoices, PortalInvoiceDetail,
  src/portal/pay/ (PayShell, PaymentForm); legacy pages ViewInvoice, PayInvoice.
  Endpoints: GET /customer/invoices, POST /customer/invoices/{id}/pay,
  POST /webhooks/stripe.

  Background:
    Given a portal customer with a sent invoice from a Stripe-connected tenant

  @automated-integration
  Scenario: List and view invoices
    Then GET /customer/invoices shows statuses, totals and due dates
      for the authenticated customer's invoices only

  @evidence-video
  Scenario: Pay button renders only when card payment is available
    Given the tenant is Stripe-connected with card payments enabled on the invoice
    Then the invoice page shows "Pay this invoice" backed by a real
      payment_url from the destination-charge path
    # docs/evidence/wave-a/03-invoice-pay-button.webm.

  @evidence-video
  Scenario: Pay page degrades gracefully without Stripe.js config
    Given the landing app has no VITE_STRIPE_PUBLISHABLE_KEY
    Then /pay/:token renders the branded shell with the documented
      "Card payments aren't available right now" state
    # docs/evidence/wave-a/04-pay-page-degraded.webm — honest degradation;
    # the Stripe Payment Element itself requires live Stripe (manual).

  @evidence-video
  Scenario: Payment settles via a signed webhook
    When the customer pays and Stripe delivers payment_intent.succeeded with a
      genuine HMAC signature
    Then the invoice flips to paid with paid_at, a payments row is written,
      and payment_url is cleared from the public payload
    And an invoice_paid outcome closes the AI funnel and notifies the tradesperson
    # docs/evidence/wave-a/00c-terminal-payment-settled.webm, 05-invoice-paid.webm.

  @automated-integration
  Scenario: Payment-received email carries the review prompt
    When the payment settles
    Then the customer receives the payment-received email with a review CTA
      pointing at the tenant's review_url (email sequence, ADR-004 §4)

  @automated-integration
  Scenario: Out-of-order webhooks cannot resurrect a refunded invoice
    Given a refunded invoice
    When a late payment_intent.succeeded arrives
    Then the invoice stays refunded (post-capture fix noted in wave-a README)

  @manual
  Scenario: Pay with a real card against live Stripe
    # Requires STRIPE_* keys + publishable key; P-wave go-live gate in
    # docs/beta-backlog.md. Not covered by local automation.
