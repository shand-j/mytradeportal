@tradie @customer-app @customer-portal @p1
Feature: Password reset on branded pages
  Both tradespersons and customers reset passwords on mytradeportal.co.uk
  branded pages — never on the admin back office. Tokens are single-use and
  signed; the portal variant carries the tenant's branding.

  Pages: web/landing "new design"/app/src/pages/ResetPassword.tsx,
  src/portal/pages/PortalResetPassword.tsx; mobile ResetPasswordScreen.
  Endpoints: POST /auth/password-reset/request, GET /auth/password-reset/inspect,
  POST /auth/password-reset/confirm.

  @automated-integration
  Scenario: Request a reset email
    When a user requests a password reset
    Then POST /auth/password-reset/request emails a single-use signed token
      linking to the mytradeportal.co.uk reset page (backlog N28)
    And the response never reveals whether the account exists

  @manual
  Scenario: Complete the reset round-trip
    Given a reset email in the inbox
    When the user opens the link, sees their email displayed, and sets a new
      password on the branded page
    Then the token is consumed and the new password logs them in
    # Full email → landing round-trip is device checklist item 9
    # (docs/beta-test-plan.md) — needs live email delivery.

  @automated-integration
  Scenario: Expired or reused tokens are rejected
    Given a consumed or expired reset token
    When the user submits a new password
    Then POST /auth/password-reset/confirm rejects it

  @automated-integration
  Scenario: Tenant-branded reset on the customer portal
    Given a customer of a tenant with portal branding
    When they reset their password from {slug}.mytradeportal.co.uk
    Then the reset page renders the tenant's logo and colours
      (src/portal/reset/ResetPasswordPanel.tsx)
