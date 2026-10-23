# E6 — Portal auth: magic link + claim + reset

- **Actor:** customer (homeowner)
- **Surface:** https://shand-1-electrical-lorg9.mytradeportal.co.uk/auth/magic, `/claim`, `/reset-password`
- **API:** `POST /customer/auth/magic/request` (202, anti-enumeration), `POST /customer/auth/magic` (exchange)
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/auth/magic` with no token | Invalid-link state + recovery path | "This link has expired or has already been used. Magic links are single-use — we'll email you a fresh one." + email form (`01-magic-consume-no-token.png`, duplicate `04-…`) | PASS |
| 2 | Enter customer email, request link | `POST /customer/auth/magic/request` → 202; email sent | "EMAIL ME A NEW LINK" submitted (`02-magic-email-filled.png`, `03-magic-request-sent.png`); **magic-link email arrived within seconds** (`../i1-email-evidence/04-your-sign-in-link-…png`) | PASS |
| 3 | Open emailed magic link (`/auth/magic?token=…&next=/quotes`) | Token exchanged, session created, redirected | Redirected to `/quotes` signed in (`07-magic-consume-redirect.png`, `08-magic-signed-in.png`, URL in `magic-final-url.txt`) | PASS |
| 4 | `/claim` page | Claim form for auto-provisioned accounts | Renders (`05-claim-page.png`); not exercised — needs an unclaimed account's magic token | PASS (render) |
| 5 | Portal `/reset-password` without token | Invalid-link state | "This reset link is invalid or has expired… request a fresh one from the app's forgotten-password screen" (`06-portal-reset-password.png`) — no web request form (QE-W7) | PASS (state renders) |

API evidence: `POST /customer/auth/magic/request` → `202 {"detail":"If an account exists for this email, a sign-in link is on its way."}` (same response for unknown emails — no enumeration). A request for an email with no account produced no email (verified via the disposable inbox), matching the anti-enumeration contract.

**Overall: PASS** (full magic-link round-trip proven with a real email and a real session)
