@customer-app @p1
Feature: Customer mobile app
  Customers can register (claiming a passwordless intake account), log in
  without knowing the tenant, request quotes through the guided intake, chat,
  track appointments and pay invoices.

  Screens: mobile/src/screens/customer/ (CustomerQuoteRequestFlow + quote-steps/,
  RequestsScreen, MessagesScreen, CustomerCalendarScreen, CustomerInvoicesScreen,
  CustomerInvoiceDetailScreen, ProfileScreen); entry/LoginScreen.
  Endpoints: POST /customer/register, POST /customer/login,
  GET /customer/quote-requests, /appointments, /invoices.

  @automated-integration
  Scenario: Register, claiming a passwordless intake account
    Given the customer previously submitted a quote request on the portal
    When they register in the app with the same email
    Then POST /customer/register claims the auto-provisioned account
      and links their unclaimed quote requests (customer_portal.py claim-on-register)

  @automated-integration
  Scenario: Tenant-agnostic login
    When the customer logs in without any tenant slug or code
    Then POST /customer/login resolves the tenant post-auth (newest
      active wins) and lists tenant associations for future multi-tenant (backlog C12)

  @automated-e2e
  Scenario: Request a quote through the guided intake
    When the customer completes postcode, job category, property profile,
      questionnaire, media, urgency, budget, dates, contact and consents steps
    Then the quote request is submitted with account creation in one flow
      (CustomerQuoteRequestFlow + quote-steps/)
    And the confirmation step sets expectations for triage and drafting

  @automated-e2e
  Scenario: Track requests with a welcoming empty state
    Given a customer with quotes still generating
    Then the requests screen shows a live-count "generating" banner rather than
      a "not connected" error (backlog C20)
    And the customer can add photos post-submission (backlog C21)
    # mobile/e2e/regression.spec.ts group B.

  @automated-e2e
  Scenario: Chat with the electrician
    Given an app-preference customer
    Then messages flow in the shared thread and the electrician is notified
    # mobile/e2e/demo-customer-chat.spec.ts exercises live chat.

  @automated-integration
  Scenario: View appointments and pay invoices
    Then GET /customer/appointments lists bookings on the customer calendar
    And GET /customer/invoices with POST /invoices/{id}/pay pays by card
    # services/api/tests/test_customer_invoices.py (7).

  @automated-integration
  Scenario: App-preference customers get chat push plus email
    Given the customer's contact preference flipped to the app on claim
    When the electrician sends a chat message
    Then the customer is pushed (registered push token) and emailed
    # services/api/tests/test_contact_preference.py (8) + test_push.py (8).
