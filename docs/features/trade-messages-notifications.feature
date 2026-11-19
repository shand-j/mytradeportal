@tradie @p1
Feature: Messages and notifications
  The tradesperson chats with reachable customers in-app, falls back to
  phone/email for unreachable ones, and is notified by push, in-app bell and
  unread badge without notification spam.

  Screens: mobile/src/screens/trade/InboxScreen, RequestInfoScreen,
  mobile/src/screens/notifications/NotificationsScreen; ContactCustomerCard.
  Endpoints: POST /communications/threads, GET/POST /communications,
  GET /notifications, POST /notifications/read-all,
  PATCH /notifications/{id}/read, GET /notifications/unread-count.

  Background:
    Given an onboarded tradesperson with customers

  @automated-e2e
  Scenario: Start a chat with an account-holding customer
    When the tradesperson taps + on Messages and searches customers with app accounts
    Then POST /communications/threads opens a direct thread (backlog N29)
    And the customer is notified of the staff-started chat
    # mobile/e2e/messages.spec.ts.

  @automated-e2e
  Scenario: Empty inbox renders the designed empty state
    Given a freshly onboarded tradesperson with no quote requests or threads
    When they open the Messages tab
    Then the inbox shows the designed empty state ("No conversations yet — new
      quote requests will appear here."), not a blank screen or an error
      (backlog N24)
    # mobile/e2e/messages.spec.ts.

  @automated-e2e
  Scenario: Request more info on a quote opens the customer chat
    When the tradesperson taps "Request more info" on a lead
    Then the customer chat opens in all cases, falling back to a direct thread
      (backlog C7)

  @automated-integration
  Scenario: Unreachable customers get phone/email contact options
    Given a customer whose preferred contact method is phone or email, or who
      has no app account
    When the tradesperson opens ContactCustomerCard on the lead or job
    Then tel:/mailto: actions are offered instead of chat (backlog N5)
    # Native tel/mailto verified on device — device checklist.

  @automated-integration
  Scenario: Message direction is tenant-relative
    Given a thread with legacy messages
    When the tradesperson reads the thread
    Then customer messages render inbound, staff messages outbound (backlog C2)

  @automated-integration
  Scenario: Staff bell fires once per customer burst
    Given a customer sending several AI-chat replies in quick succession
    Then staff receive a single bell notification, re-armed only by a staff or
      AI reply (backlog C14)

  @manual
  Scenario: Push notification arrives with the app closed and deep-links
    Given the tradesperson has granted push permission
    When a quote-ready, message or reminder event fires
    Then a push arrives with sound and badge, and tapping it deep-links to the
      notified entity (backlog N1, N2)
    # Requires the APNs key on EAS — device checklist item 1.
    # API-side plumbing covered by services/api/tests/test_push.py (8 tests).

  @automated-e2e
  Scenario: Notification rows navigate to the notified entity
    Given unread notifications in the bell list
    When the tradesperson taps a row
    Then the app navigates to the related quote, job, invoice or thread
    And "mark all as read" clears the badge via POST /notifications/read-all
    # mobile/e2e/notifications.spec.ts.
