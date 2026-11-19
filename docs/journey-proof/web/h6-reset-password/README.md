# H6 — Reset password (`/reset-password`)

- **Actor:** user/customer with a reset email
- **Surface:** https://www.mytradeportal.co.uk/reset-password (+ tenant portal variant)
- **Setup:** `POST /auth/password-reset/request {email: qe-web-…@maxxspace.com}` → `password_reset` email received with `https://www.mytradeportal.co.uk/reset-password?token=…` (email evidence `../i1-email-evidence/06-password-reset.png`)
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/reset-password` with no token | Clear invalid-link state | "This reset link is invalid or has expired… request a fresh one from the app's forgotten-password screen" (`01-reset-password.png`) | PASS (but see QE-W7 — no web request form) |
| 2 | Open emailed `/reset-password?token=…` | Branded form showing the account email + new password fields | Renders, account email shown, two password fields (`02-reset-valid-token.png`) | PASS |
| 3 | Enter + confirm new password, submit | Password updated | "Password updated for qe-web-…@maxxspace.com. You can now return to the app and log in" (`03-reset-filled.png`, `04-reset-result.png`) | PASS |
| 4 | Verify the reset functionally | New password works, old fails | `POST /customer/login` with new password → 200; with old password → 401 (API-verified) | PASS |

**Overall: PASS**
