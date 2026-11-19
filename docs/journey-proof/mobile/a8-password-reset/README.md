# A8 — Trade password reset request (mobile, iOS)

Captured 2026-10-24 against production, same rig as `../a3-onboarding/`.

**Result: PASS (request side).** The consume side is web-covered (`../../web/h6-reset-password/`).

| # | Shot | What it shows |
|---|---|---|
| 01 | `01-trade-login.png` | Trade login ("Electrician login") |
| 02 | `02-forgot-no-email-error.png` | "Forgot password?" with an empty email → inline error: "Enter your email above so we know where to send the reset link." |
| 03 | `03-forgot-email-filled.png` | Reset requested for `jshand89+reset@gmail.com` |
| 04 | `04-reset-requested-confirmation.png` | Confirmation state: "If an account exists for …, we've emailed a reset link. Check your inbox (and spam) — the link expires in 30 minutes." (generic, enumeration-safe) |

Notes: the flow is inline on the login screen (`login-forgot-password` →
`POST /auth/password-reset/request`); there is no separate request screen in the app.
The reset email itself went to a real mailbox (plus-alias) and was not consumed —
token consumption was proven in the web wave (H6, full round-trip).
