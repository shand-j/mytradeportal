@tradie @p0
Feature: Quote to job conversion and scheduling
  An accepted (or sent) quote converts into a scheduled job. The calendar
  respects working hours, job creation pre-fills duration and dates from the
  quote, and job detail supports assignees, notes, photos and navigation.

  Screens: mobile/src/screens/trade/CalendarScreen, JobCreateScreen,
  JobDetailScreen, QuoteEditScreen (Convert to…). Endpoints:
  POST /quotes/{id}/convert-to-job, POST /jobs, POST /jobs/{id}/start,
  POST /jobs/{id}/complete, GET /appointments/availability, GET /calendar/feed.

  Background:
    Given an onboarded tradesperson with at least one sent or accepted quote

  @automated-integration
  Scenario: Convert a sent quote to a scheduled job
    When the tradesperson chooses "Convert to… → Job" on a sent quote
    Then POST /quotes/{id}/convert-to-job creates the job and marks the quote accepted first
    And the AI quote assumptions and notes are copied into the job notes (backlog N12)
    And photos uploaded on the quote are attached to the job (backlog N13)

  @automated-e2e
  Scenario: Job creation prefills duration and dates from the quote
    Given a quote with 3 lines totalling 30 quoted hours
    When the tradesperson creates a job from that quote
    Then the duration is prefilled from the quoted hours and remains editable (backlog N15)
    And date and time pickers prefill from the customer's accepted preferred dates

  @automated-e2e
  Scenario: Create a job for a brand-new customer inline
    Given a quote agreed off-app
    When the tradesperson toggles "New customer" on the job create screen
    Then the customer is created inline with dedupe protection and the job is scheduled
    # mobile/e2e/jobs.spec.ts (backlog N9).

  @automated-e2e
  Scenario: Assign staff and edit notes on a job
    Given an existing job
    When the tradesperson selects an assignee and edits the notes
    Then the assignee is validated as same-tenant staff and the notes persist (backlog N11)

  @automated-integration
  Scenario: Working hours drive booking availability
    Given working_day_start, working_day_end and working_days are configured
    When a customer requests preferred dates
    Then GET /appointments/availability only offers slots inside working hours (backlog N16)

  @automated-integration
  Scenario: Start and complete a job
    Given a scheduled job
    When the tradesperson starts and later completes it
    Then POST /jobs/{id}/start and /complete move the job through its lifecycle

  @manual
  Scenario: Navigate to the job site in the default maps app
    Given a job with a customer address
    When the tradesperson taps navigate on job detail
    Then the platform default maps app opens (backlog N10) — device checklist item 6

  @manual
  Scenario: Subscribe to the calendar feed on iOS
    When the tradesperson taps the calendar subscribe button
    Then the iOS native subscribe prompt appears for the webcal feed (backlog N7)
    # Device checklist item 7 — native prompt not web-testable.
