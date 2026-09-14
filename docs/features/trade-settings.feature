@tradie @p1
Feature: Tradesperson settings
  Branding, working hours, review link, reminder cadence, quote rounding, VAT
  status, payments and bank details are all editable in-app and drive quotes,
  invoices, availability and the portal.

  Screens: mobile/src/screens/trade/SettingsScreen, BrandingSettingsScreen,
  WorkingHoursSettingsScreen, FollowUpSettingsScreen, PaymentsSettingsScreen,
  PaymentDetailsSettingsScreen. Endpoints: PATCH /tenants/settings,
  GET /tenants/{id}, POST /billing/portal-session.

  Background:
    Given an onboarded tradesperson on the Settings screen

  @automated-e2e
  Scenario Outline: Update tenant settings and see them take effect
    When the tradesperson changes <setting>
    Then PATCH /tenants/settings persists it
    And <effect>

    Examples:
      | setting                         | effect |
      | brand colours and logo          | the tenant portal and documents rebrand |
      | the review link                 | the payment-received email carries the review prompt CTA |
      | working days and hours          | /appointments/availability only offers valid slots |
      | quote reminder cadence and max  | the scheduler follows the new chase sequence |
      | invoice reminder interval       | unpaid invoices are chased on the new cadence |
      | quote rounding (£5/£10)         | new quote totals round up with rounding_adjustment |
      | VAT registration status         | new quotes and invoices apply 0% or 20% VAT |
    # mobile/e2e/settings.spec.ts; API rules in test_reminders.py (10),
    # test_working_hours.py (4), test_quote_rounding.py (9), test_vat_registration.py (7).

  @automated-integration
  Scenario: Reminder chases stop and recur as configured
    Given quote reminders enabled with a max of 3 and invoice reminders enabled
    Then the scheduler sends at most 3 quote reminders then stops
    And invoice reminders recur until the invoice is paid (backlog N6)

  @automated-integration
  Scenario: Configure bank payment details for invoice emails
    When the tradesperson saves account name, sort code, account number and
      reference format
    Then sent invoice emails include the payment details block (backlog N27)

  @automated-integration
  Scenario: Manage the subscription via the Paddle customer portal
    When the tradesperson taps manage subscription
    Then POST /billing/portal-session returns a Paddle portal session URL
