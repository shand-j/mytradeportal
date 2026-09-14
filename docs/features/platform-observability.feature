@platform @p1
Feature: AI observability, alerting, data export and email reminders
  Every AI call is attributed by actor and channel, costs roll up on a
  schedule, budget/anomaly/fair-use/rollup-failure alerts fire to ops,
  keep-rate measures draft quality, tenants can export their data, and the
  reminder scheduler chases quotes and invoices.

  Modules: app/ai_telemetry.py, app/ai_quality.py, app/alerting.py,
  app/scheduler.py, app/routers/data_export.py, app/routers/analytics.py.

  @automated-integration
  Scenario: AI calls are attributed by actor and channel
    When any LLM call is made (draft, refine, triage)
    Then an ai_call_events row records actor (tradesperson/customer/system),
      channel (app/portal/api), model, tokens and cost — fail-open so
      telemetry never breaks the workflow
    # services/api/tests/test_ai_telemetry.py (11).

  @automated-integration
  Scenario: Spend rollups and ops alerts
    Given the rollup scheduler runs
    Then daily/weekly rollups aggregate ai_call_events per tenant
    And budget breach, cost anomaly, fair-use pressure and rollup-failure
      alerts dispatch via Slack webhook and email
    # services/api/tests/test_rollups.py (12), test_alerting.py (4),
    # test_observability_hardening.py (25), test_reconcile_ai_costs.py (4).

  @automated-unit
  Scenario: Keep-rate feedback loop measures draft quality
    Given a draft/final snapshot pair for a sent quote
    Then keep_rate = unchanged AI lines / total AI draft lines (quantised to 0.001)
    And price or content edits count against the keep-rate
    # app/ai_quality.py; services/api/tests/test_ai_quality.py (16).

  @automated-integration
  Scenario: Tenant data export excludes secrets and honours authorisation
    When a tenant admin requests GET /export/my-data
    Then the export contains their tenant's data only (RLS-scoped)
    And secrets (API keys, tokens, webhook secrets) are excluded
    And non-admin staff are rejected
    # services/api/tests/test_data_export.py (4).

  @automated-integration
  Scenario: Quote and invoice chase sequences
    Given the reminder scheduler is enabled
    Then quotes are chased up to the configured max (default 3) then stop
    And invoices are chased until paid, cancelling on settlement
    And each send is ledgered in the reminders table with staff notified
    And per-tenant cadence comes from tenant settings
    # services/api/tests/test_reminders.py (10), test_email_sequence.py (29).

  @automated-integration
  Scenario: Product analytics events land in the events table
    When the app tracks an analytics event
    Then app/analytics.py writes an analytics.* row to the events table,
      fail-open, with optional PostHog passthrough when POSTHOG_API_KEY is set
    # services/api/tests/test_analytics.py (8), test_analytics_shim.py (6).
