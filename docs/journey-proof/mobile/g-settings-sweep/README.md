# G — Trade settings sweep (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** deep-link navigation (`xcrun simctl openurl mtp://<route>`) + screenshot; all screens render real prod data for tenant Shand 1 Electrical.

| # | Screen | Observed | Result |
|---|--------|----------|--------|
| 01 | Settings home | Signed-in card (John Shand / Shand 1 Electrical), 6-digit customer code 755862 with Share, Subscription "Active · Team plan · Renews 3 Nov", settings links — [01-settings.png](01-settings.png) | PASS |
| 02 | Branding | Business name/phone/address prefilled; logo thumbnail renders (auth-gated image works); review-link field; Save — [02-branding.png](02-branding.png) | PASS |
| 03 | Working hours | Start 08:00 / end 18:00, Mon–Sun all on — [03-working-hours.png](03-working-hours.png) | PASS |
| 04 | Follow-ups | Quote reminders on (3 reminders, 3-day gap), invoice reminders on — [04-follow-ups.png](04-follow-ups.png) | PASS |
| 05 | Payment details | Bank details (Shand 1 · 010101 · 11111111) — appear on invoice emails — [05-payment-details.png](05-payment-details.png) | PASS |
| 06 | Payments (Stripe Connect) | "Stripe connection — Not connected", "Connect Stripe" CTA, card-payments toggle disabled until connected — [06-payments-stripe-connect.png](06-payments-stripe-connect.png) | PASS (screen); Connect onboarding itself blocked platform-wide by DEFECT-017 |
| 07 | Billing / subscription | Plan chooser: Sole Trader £25, Pro £39 (most popular), Team £69; "14-day free trial" copy — [07-billing-subscription.png](07-billing-subscription.png) | PASS |
| 08 | Analytics (Revenue & costs) | Paid £755, Outstanding £2164, Quoted £2016, Costs £0, Estimated profit £755 (LIVE) — [08-analytics.png](08-analytics.png) | PASS |
| 09 | Customers (CRM) | Searchable contact list incl. the B1/B3 "John Shand" contact — [09-customers-crm.png](09-customers-crm.png) | PASS |
| 10 | Customer detail | "Customer since 23 Oct 2026 · no app account (email-only)", editable contact fields, preferred-contact chips, Create quote — [10-customer-detail.png](10-customer-detail.png) | PASS |
| 11 | Notifications | Real rows from this wave: "Job scheduled 'QE multi-day full rewire (16h block)'…", "Quote ready for review", "Quote accepted"… unread dots + "Mark all read" — [11-notifications.png](11-notifications.png) | PASS |
| 12 | Messages | Conversation view with AI assistant banner, empty state, composer — [12-messages.png](12-messages.png) | PASS |
| 13 | Inbox | Conversation list, empty state "No conversations yet — new quote requests will appear here", + new-lead action — [13-inbox.png](13-inbox.png) | PASS |

**Note:** the "Messages" tab badge/list vs `/inbox` route both render conversation surfaces (12 is a thread-style view, 13 the list); titling is consistent ("Messages") but the two routes could confuse — cosmetic.
