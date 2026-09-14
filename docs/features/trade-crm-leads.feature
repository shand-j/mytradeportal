@tradie @p1
Feature: CRM, customer badges and leads
  The CRM screen lists customers with full detail editing; risky customers are
  badged automatically (late payer, time waster) with manual overrides, and
  blocking cuts off login, quote requests and chat. New quote requests arrive
  as leads with search and filter dropdowns.

  Screens: mobile/src/screens/trade/CRMScreen, CustomerDetailScreen,
  LeadDetailScreen, ManualLeadScreen, DashboardScreen. Endpoints:
  GET/PATCH /customers/{id}, GET /quote-requests, PATCH /quote-requests/{id},
  POST /quote-requests/from-share.

  Background:
    Given an onboarded tradesperson with CRM customers

  @automated-integration
  Scenario: Edit customer detail with parking and access notes
    When the tradesperson edits a customer's address, parking or access fields
    Then PATCH /customers/{id} persists the full address plus postcode (backlog C5)
    And parking/access prefill the quote intake for that customer (backlog N25)

  @automated-integration
  Scenario: Duplicate customer creation is rejected
    When a customer is created with an existing email or matching name+phone
    Then the API answers 409 with duplicate_contact:email or duplicate_contact:name_phone
      and the existing contact is linked instead (backlog C15)

  @automated-integration
  Scenario: Badges are auto-assigned and manually overridable
    Given a customer with unpaid overdue invoices or 3+ unanswered quotes
    Then the Late Payer / Time Waster badges are auto-assigned (backlog N26)
    And the tradesperson can override each badge (tri-state) on customer detail

  @automated-integration
  Scenario: Block a customer
    Given a customer flagged as a time waster
    When the tradesperson blocks them
    Then the customer can no longer log in, submit quote requests or use live chat
    # Anonymous public lead-form block is a deferred follow-up (beta-backlog).

  @automated-e2e
  Scenario: Review incoming leads with search and filters
    When new quote requests arrive from the portal or mobile intake
    Then they appear on the leads/quotes screen ordered oldest first (backlog N33)
    And search and the status/sort dropdowns filter the list
    And account-less requesters show an unregistered flag setting comms
      expectations (backlog C4)
    # mobile/e2e/crm.spec.ts + dashboard.spec.ts.

  @automated-integration
  Scenario: Log a lead received off-app
    When the tradesperson shares a lead into the app or enters it manually
    Then POST /quote-requests/from-share stores it with its entry_channel
