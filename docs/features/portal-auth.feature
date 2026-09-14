@customer-portal @p0
Feature: Portal magic-link auth and account claim
  Customers authenticate invisibly: emailed magic links exchange for a session,
  sessions expire and can be re-sent self-serve, and claiming the account
  sets a password and flips the CRM contact preference to the app.

  Pages: src/portal/pages/PortalMagicAuth, PortalClaim.
  Endpoints: POST /customer/auth/magic, POST /customer/auth/magic/request,
  POST /customer/auth/claim.

  Background:
    Given an auto-provisioned passwordless customer

  @automated-integration
  Scenario: Consume a magic link
    When the customer opens a magic link from any portal email
    Then POST /customer/auth/magic exchanges the SHA-256-stored token
      for a customer JWT scoped to their own data
    And the link remains reusable within its 30-day TTL and is revocable

  @automated-integration
  Scenario: Expired session offers a self-serve resend
    Given an expired or missing session
    When the customer requests a new link via POST /customer/auth/magic/request
    Then a fresh magic-link email is sent (202) without revealing account existence

  @automated-integration
  Scenario: Object-level authorisation on customer data
    Given two customers of the same tenant
    Then neither can read the other's quotes, invoices or messages
    # services/api/tests/test_portal_auth.py + test_tenant_isolation.py.

  @automated-integration
  Scenario: Claim the account from the booking-confirmation email
    When the customer opens the one-shot /claim link, sets a password and confirms
    Then POST /customer/auth/claim claims the account exactly once
    And the thank-you screen shows the App Store link (placeholder pre-release)
    And the CRM contact's preferred contact method flips to the app
    And a customer who already has a password can still claim — the token
      doubles as a verified password reset

  @automated-integration
  Scenario: Registering against an auto-provisioned account claims it
    Given a passwordless intake account
    When the customer registers in the mobile app with the same email
    Then registration claims the account (sets the password) instead of 409ing
