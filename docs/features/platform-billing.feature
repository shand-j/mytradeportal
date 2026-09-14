@platform @p0
Feature: Billing, trials, tier gates and fair-use guardrails
  Flat unmetered pricing (ADR-001) across Sole Trader, Pro and Team tiers.
  Tenants bootstrap with reserved-slug protection, trial for 14 days with a
  3-quote extension, and hit capability gates per tier. AI usage is guarded
  by fair-use limits that stay invisible to customers. Paddle webhooks keep
  subscription state in sync.

  Endpoints: POST /tenants, GET /billing/plans, POST /billing/checkout,
  POST /webhooks/paddle, GET /billing/subscription, POST /billing/portal-session.

  @automated-integration
  Scenario: Bootstrap a tenant with reserved-slug protection
    When a tenant is created via POST /tenants
    Then the slug is unique and the reserved blocklist (www, api, admin, …)
      is rejected (ADR-004)

  @automated-integration
  Scenario: 14-day no-card trial with 3-quote extension
    Given a tenant on the internal trial
    Then trial_ends_at is 14 days out
    And sending the 3rd AI quote extends the trial once and stamps
      trial_extended_at
    # services/api/tests/test_trial.py (11); extension proven in
    # docs/evidence/wave-a/00a-terminal-onboarding-quote.webm.

  @automated-integration
  Scenario: Tier capability matrix is enforced server-side
    Then Sole Trader, Pro and Team each expose their entitled features via
      the capability matrix (plans.py / entitlements)
    And gated features answer a clear upgrade error on lower tiers
    # services/api/tests/test_tier_gates.py (10), test_entitlements.py (13).

  @automated-integration
  Scenario: Fair-use guardrails burst-limit AI routes
    When a tenant bursts AI generation beyond the fair-use allowance
    Then the expensive routes answer 429 with a retry hint
    And cheap routes (e.g. the inline triage check) stay on the cheap model
    And customers never see fair-use errors — degradation is invisible
      (fair-use page: web/landing src/pages/FairUse.tsx)
    # services/api/tests/test_fair_use.py (17), test_rate_limit.py (3).

  @automated-integration
  Scenario: Paddle checkout creates the subscription
    When a tradesperson completes checkout
    Then POST /billing/checkout binds the Paddle customer with the email
      prefilled and locked, and the subscription activates

  @automated-integration
  Scenario: Subscription state syncs via Paddle webhooks
    When Paddle delivers subscription.created/updated/cancelled events
    Then POST /webhooks/paddle verifies the signature, is idempotent on
      replay, and mirrors status (trialing/active/past_due/paused/canceled)
      into the tenant record
    # services/api/tests/test_webhooks.py (22), test_paddle_client.py (5).

  @automated-integration
  Scenario: Tenant-status gate reflects subscription state
    Then GET /auth/tenant-status passes trialing/active/past_due and
      beta_comped, and paywalls incomplete/paused/canceled (backlog C22)
