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

## Device run results

Build 10 era (2026-09-10, John's iPhone, prod backend):

| Spec | Area | Result |
|---|---|---|
| 01 | Entry/auth/reset | 12/12 passing |
| 02 | Onboarding wizard | 11/12 + 1 documented (review-step assertion needs a build with 4a60f2a) |
| 10-18 | Trade: dashboard, quotes, leads, customers, jobs, invoices, calendar, messages, settings | all green |
| 20 | Customer requests + accept/reject/book | 5 passing, 2 documented skips (wizard submit — needs a build with 3b180d4) |
| 21 | Customer AI chat | 1 passing, 3 documented skips (same root cause as 20) |
| 22 | Customer profile | 2 passing, 1 documented skip (address prefill — needs a build with 3b180d4) |
| 23 | Customer calendar | skips: customer calendar not present in the installed build |
| 30 | Notifications, push-token, bells | 6/6 passing |

Build 11 (contains 4a60f2a, 3b180d4 — all app fixes, 2026-09-10):

| Spec | Area | Result |
|---|---|---|
| 20 | Customer requests + accept/reject/book | **7/7 strict** — wizard submits, persists with preferred dates |
| 21 | Customer AI chat | 3/4 — banner follow-up, inbound reply, triage-closure timing fixed; see below |
| 22 | Customer profile | **3/3 strict** — address prefill verified |
| 02 | Onboarding wizard | **12/12 strict** — review-step fix verified |

Spec 21's remaining test (`notifies the electrician once AI triage closes`)
asserts the backend's forced closure at `MAX_FOLLOWUP_TURNS` (5). The spec
now replies up to 6 turns and polls for the closure message; if the LLM's
confidence never reaches 80 the closure arrives exactly at turn 5.

## Defects found during device runs

**Fixed and deployed (services/api, prod-verified):**
- `POST /jobs` 500'd on tz-aware datetimes (job schedule columns are naive)
  — `field_validator` strips tz (84b3cf5).

**Fixed in app source (build 11 or 12):**
- Onboarding review step received only its own state slice (4a60f2a, build 11).
- Customer sessions (tenant-agnostic login + session restore) never loaded
  the tenant branding, so the quote-request wizard had no `business.slug`
  and **silently skipped its submit** while still showing the confirmation
  screen (3b180d4, build 11 — verified strict-green by spec 20). Backend was
  verified healthy end-to-end (manual submit → 201 → lead visible → AI
  follow-up fires).
- Customer profile screen did not prefill the address field (3b180d4,
  build 11 — verified strict-green by spec 22).
- Customer bottom tab bar never rendered: `usePathname()` returns paths
  without route-group segments (`/requests`, not `/(customer)/requests`), so
  the inclusion check always failed (391db18, build 12).

**Found, documented, not fixed:**
- Push tokens are globally re-pointed: one device token per row, so logging
  in as the customer after the trade account re-owns the token and trade
  pushes stop. This explains "push notifications not working" on John's
  phone, where both accounts are used. Registration itself works (spec 30
  asserts the staff row mid-run). Needs a product decision: scope tokens by
  (owner_type, owner_id) instead of globally unique.
- Calendar displays naive UTC job times one hour off during BST.
- Customer profile edits are UI-only (no backend PATCH endpoint); spec 22
  asserts the backend record is untouched.
- Quote refine intermittently 502s at the LLM gateway.
