# Route coverage matrix — Appium E2E suite

Every UI surface a user can see or touch, mapped to the spec that exercises
it. Status: `✅` spec written (device run pending WDA signing); `⚠️` partial /
asserts intended behaviour blocked by a known gap; `—` out of beta scope.

| Route | Surface | Spec |
|---|---|---|
| `app/index.tsx` | Entry screen (default + white-label card, business code lookup) | 01 |
| `app/trade-login.tsx` | Electrician login (validation, invalid creds, forgot-password, reset deep link) | 01 |
| `app/customer-login.tsx` | Customer login + register toggle | 01 |
| `app/reset-password.tsx` | Set-new-password deep-link screen (invalid/expired token paths) | 01 |
| `app/onboarding/index.tsx` | 10-step tenant wizard: every step's UI, validation gating, back-nav persistence; stops before plan payment (no real tenant) | 02 |
| `app/paywall.tsx` | Plan selection / Paddle checkout | ⚠️ 02 asserts entry point only — creating a real tenant + Paddle session excluded by data-safety rule |
| `app/(trade)/dashboard.tsx` | Stats, three-dot settings, notification bell, bottom nav (all 5 tabs) | 10 |
| `app/(trade)/quotes.tsx` + `quote/[id].tsx` | List, detail totals cross-checked vs API, refine-with-AI regeneration state, request-info, send (status + audit log), convert-to-job | 11 |
| `app/(trade)/quote-intake.tsx` | AI quote generation intake + generating/ready banners | 12 |
| `app/(trade)/request-info.tsx` | Request-more-info → customer chat thread | 11 |
| `app/(trade)/manual-lead.tsx` | Manual lead capture, all fields persisted (contact + quote_request) | 12, 13 |
| `app/(trade)/lead/[id].tsx` | Lead detail, invite-to-app flag for unregistered customers, lead → AI quote | 12, 13 |
| `app/(trade)/customers.tsx` | List, new customer, CRM card (address, since, create-quote), has-account state | 13 |
| `app/(trade)/calendar.tsx` | Day/week job grid, new-job, booking → job detail | 14, 16 |
| `app/(trade)/job/new.tsx` + `job/[id].tsx` | Manual job create (persisted), start/complete transitions, invoice surface, VAT rate from source quote | 14, 15 |
| `app/(trade)/invoices.tsx` + `invoice/[id].tsx` | List, detail totals, create-and-send (status + audit), reminder, mark-paid | 15 |
| `app/(trade)/messages.tsx` + `inbox.tsx` | Inbox, thread, send message; direction=outbound persisted | 17 |
| `app/(trade)/notifications.tsx` | Bell → list vs backend rows | 10, 30 |
| `app/(trade)/analytics.tsx` | AI insights | — pre-beta surface; not in navigation |
| `app/(trade)/follow-ups.tsx` | Follow-up nudges | — hidden pre-beta |
| `app/(trade)/certificates.tsx` + `certificate/[id].tsx` | EICR certificates | — post-beta (hidden from UI) |
| `app/(trade)/settings.tsx` | Settings root, identity, subscription plan, logout → entry | 10, 18 |
| `app/(trade)/branding.tsx` | Brand fields vs API, colour swatch/hex save → persisted → survives relaunch → restore | 18 |
| `app/(trade)/billing.tsx` | Plan tiers, subscription state | 18 |
| `app/(customer)/requests.tsx` | Empty-state copy, 10-step request wizard (persisted title/raw_text/postcode/preferred dates), draft-withheld gating, accept + date reconfirmation + booking, reject, revised-quote → chat | 20 |
| `app/(customer)/messages.tsx` | AI chat: follow-up question, reply persisted direction=inbound, triage-complete notification, bottom-nav access | 21 |
| `app/(customer)/notifications.tsx` | Bell + list + badge | 30 |
| `app/(customer)/calendar.tsx` | Bookings from accepted quotes | 23 |
| `app/(customer)/profile.tsx` | Pre-filled fields, edit flow, keyboard-avoidance, back button | 22 |
| iOS system surfaces | Notification permission prompt, push-token registration (DB row), SpringBoard alert handling, background/foreground | 30 |

## Known gaps the suite documents (assert intended behaviour)

- **Customer profile save** (`ProfileScreen.save()` shows a toast only; no
  customer-profile PATCH endpoint exists) — spec 22 asserts the read path and
  documents the gap rather than failing.
- **Paywall/Paddle checkout** excluded: creating a real tenant in production
  is prohibited; onboarding spec stops at the plan entry point.
- **Push banner delivery while app closed** needs a dev-signed build +
  APNs; the TestFlight build asserts the in-app notification row + token
  registration instead.
