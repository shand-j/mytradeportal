@tradie @p0
Feature: Tradesperson onboarding and subscription signup
  A new electrician goes from first launch to a paying (or trialling) tenant:
  account creation, business setup, branding including the review link, plan
  selection, Paddle checkout, and the 14-day no-card trial.

  Screens: mobile/src/screens/onboarding/ (OnboardingStepperScreen + steps/).
  Endpoints: POST /auth/register, PATCH /onboarding/step/{step_name},
  POST /onboarding/launch, POST /tenants, GET /billing/plans,
  POST /billing/checkout, GET /auth/tenant-status.

  Background:
    Given the tradesperson has installed the app and opened it for the first time

  @automated-integration
  Scenario: Create an account and start business setup
    When the tradesperson registers with email and password on the Account step
    Then an account is created via POST /auth/register
    And the onboarding stepper advances to the business identity step

  @automated-integration
  Scenario: Complete business setup and branding including the review link
    Given the tradesperson has an account
    When they complete the business identity, address/service area, services,
      branding and compliance steps
    Then each step is persisted via PATCH /onboarding/step/{step_name}
    And the branding step captures logo, colours and the review_url used by
      the payment-received review prompt
    And membership type is persisted to tenant settings (backlog C11)

  @automated-integration
  Scenario: Tenant bootstrap rejects reserved slugs
    When a tenant is created with a reserved slug such as "www", "api" or "admin"
    Then POST /tenants rejects it (reserved-slug blocklist, ADR-004)

  @automated-integration
  Scenario: Plan selection does not 500 on Supabase admin failures
    Given the tradesperson reaches the plan step (backlog C23)
    When Supabase admin_create_user fails during POST /tenants
    Then the API answers 502/503 with a clear message, not an unhandled 500

  @manual
  Scenario: Pay for a plan via Paddle checkout
    Given the tradesperson has selected a plan on the Plan & Payment step
    When they continue to Paddle checkout
    Then the checkout email is prefilled and locked to the account email (backlog C19)
    And completing checkout activates the subscription via the Paddle webhook
    # Device checklist item 8, docs/beta-test-plan.md — requires Paddle sandbox.

  @automated-integration
  Scenario: Start on the 14-day no-card trial
    Given the tradesperson skips payment during onboarding
    Then an internal no-card trial row is created with trial_ends_at 14 days out
    And GET /auth/tenant-status reports "trialing" so the app is usable

  @automated-integration
  Scenario: Tenant-status gate paywalls lapsed tenants
    Given a tenant whose subscription is incomplete, paused or cancelled
    When the app checks GET /auth/tenant-status at launch
    Then the paywall screen is shown instead of the dashboard (backlog C22)
    And beta_comped tenants pass the gate without paying
