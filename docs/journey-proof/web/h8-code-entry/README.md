# H8 — Short-code entry (`/code`)

- **Actor:** homeowner with the electrician's 6-digit code
- **Surface:** https://www.mytradeportal.co.uk/code → `GET /businesses/by-code/{code}/public-config`
- **Setup:** tenant Shand 1 Electrical's public config reports `code: 755862`
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/code` | Code entry page | "Find your electrician's portal", 6-digit input + GO (`01-code-entry.png`) | PASS |
| 2 | Enter `755862`, click GO | Redirect to the tenant's portal | Redirected to `https://shand-1-electrical-lorg9.mytradeportal.co.uk/` — tenant-branded portal home with quote-request form (`02-code-filled.png`, `03-code-result.png`, URL in `code-result-url.txt`) | PASS |

**Overall: PASS** — also proves tenant-subdomain routing works end to end.
