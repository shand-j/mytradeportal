# A2 — Trade login (mobile)

**Captured:** 2026-10-23 · iPhone 17 Pro simulator (iOS 26.5) · dev-client build of `main@598cb93` via Metro · prod API `api-production-65db.up.railway.app`
**Account:** jshand89@gmail.com (tenant Shand 1 Electrical, `shand-1-electrical-lorg9`)
**Driving:** UI-driven via Appium (XCUITest) after a fresh `simctl uninstall`/`install`. Note: the iOS simulator **keychain survives uninstall**, so the "fresh" launch resumed the previous session; the entry screen was reached by signing out from Settings instead.

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Entry screen (no session) | Role selection: tradesperson vs customer | "Get started" screen with "I'm an Electrician" / "I'm a Customer" cards — [01-entry-role-select.png](01-entry-role-select.png) | PASS |
| 2 | Tap "I'm an Electrician" | Electrician entry with Log in / Register | "Log in" + "Register my business — Free during beta" — [02-electrician-choice.png](02-electrician-choice.png) | PASS |
| 3 | Tap "Log in" | Login form | "Electrician login" — email + password fields, "Sign in", "Forgot password?", invite and help links — [03-login-form.png](03-login-form.png) | PASS |
| 4 | Submit wrong password | Error shown, no session | Inline amber "Invalid email or password." under the password field — [04-invalid-password-error.png](04-invalid-password-error.png) | PASS |
| 5 | Submit correct credentials | Routed to trade dashboard | Dashboard loads as "Shand 1 Electrical / Hi John Shand" with live figures (Outstanding quotes £1299, revenue cards); a local "Quote ready for review" notification banner arrived on login — [05-dashboard-after-login.png](05-dashboard-after-login.png) | PASS |

Token storage (iOS Keychain via expo-secure-store) confirmed indirectly: session survives app restart (used by later journeys after `simctl terminate`/`launch` cycles).

**Not captured:** tenant-mismatch 403 variant and paywall redirect variant (need a second tenant account / expired-subscription account).
