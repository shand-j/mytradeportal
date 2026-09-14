@tradie @p0
Feature: AI quote generation, editing, refine and send
  The tradesperson drafts guide-priced, ex-VAT line items with the AI quote
  pipeline, edits them, asks the AI to refine, and sends the quote to the
  customer. Quotes honour rounding and VAT settings, edits are captured as
  training data, and sending feeds the outcome funnel.

  Screens: mobile/src/screens/trade/QuoteIntakeScreen, QuoteEditScreen,
  QuotesScreen. Endpoints: POST /quotes/generate (and /generate-async),
  PATCH /quotes/{id}, POST /quotes/{id}/refine, POST /quotes/{id}/send,
  GET /quotes/{id}/pdf, GET /quotes/training-events.

  Background:
    Given an onboarded tradesperson with an active or trialling tenant

  @automated-integration
  Scenario: Generate an AI-drafted quote from free text
    When the tradesperson describes a job in the quote intake screen and submits
    Then POST /quotes/generate returns a draft with ai_generated line items,
      guide prices, ai_confidence, ai_warnings and ai_assumptions
    And retrieval_status reflects whether catalogue grounding succeeded

  @automated-integration
  Scenario: Grounded lines take catalogue units and prices
    Given the Qdrant catalogue contains consumer units, sockets and twin & earth
    When a quote is generated for a consumer unit replacement
    Then grounded lines use catalogue units (ea, m, hr) rather than "job"
      (backlog C6, N21)
    And guide prices fall inside the eval golden-set bands

  @automated-unit
  Scenario: Quote totals honour the tenant rounding setting
    Given quote_rounding is set to round up to the nearest £10
    When a quote total is computed
    Then the total is rounded up and the uplift is stored as rounding_adjustment

  @automated-integration
  Scenario: Non-VAT-registered tenants quote at 0% VAT
    Given the tenant is not VAT registered
    When any quote is generated
    Then every line and total carries 0% VAT (backlog C1)

  @automated-integration
  Scenario: Edit AI draft lines and capture the edit as training data
    Given an AI-drafted quote
    When the tradesperson edits a line price or description and saves
    Then PATCH /quotes/{id} persists the change
    And a quote_lines_edited event with before/after snapshots is recorded
    And the edits are exportable via GET /quotes/training-events (backlog C9)

  @automated-e2e
  Scenario: Refine an AI quote with instructions
    Given an AI-drafted quote
    When the tradesperson enters refine instructions and taps refine
    Then POST /quotes/{id}/refine regenerates the AI lines, preserving any
      manually added or edited lines
    And the screen shows the refine skeleton (testID refine-skeleton) including
      an assumptions placeholder
    And a notify-on-complete banner (testID refine-banner) appears when the
      refine finishes in the background (backlog C10)

  @evidence-video
  Scenario: Send the quote to the customer
    Given a reviewed AI-drafted quote
    When the tradesperson taps send
    Then POST /quotes/{id}/send emails the customer a branded quote with a
      magic link and a view-only token fallback
    And a quote_sent outcome event is recorded for the AI funnel
    And the 3rd sent AI quote triggers the trial extension
    # Proven end-to-end in docs/evidence/wave-a/00a-terminal-onboarding-quote.webm
    # and 07-mailpit.webm (quote email captured in Mailpit).

  @automated-integration
  Scenario: Download the quote PDF
    When the tradesperson requests GET /quotes/{id}/pdf
    Then a branded PDF of the quote is returned
