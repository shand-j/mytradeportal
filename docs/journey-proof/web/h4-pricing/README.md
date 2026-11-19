# H4 — Pricing + subscribe

- **Actor:** public visitor → signed-in tradesperson
- **Surface:** https://www.mytradeportal.co.uk/#pricing → `/subscribe?plan=…&interval=…`
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Pricing section (monthly) | 3 tiers with prices | Sole Trader £25 / Pro £39 / Team £69 per business/mo (`01-pricing-section.png`) | PASS |
| 2 | Toggle YEARLY | Yearly prices | Toggle renders and switches (`02-pricing-yearly.png`) | PASS |
| 3 | Paddle live price preview | Live localised prices from Paddle | **Paddle preview calls hit `sandbox-api.paddle.com/pricing-preview`** (prod bundle loads sandbox Paddle env — see `paddle-network.txt`, QE-W3). Displayed prices match the static GBP fallback | FAIL (env misconfiguration; known as DEFECT-004) |
| 4 | Click SUBSCRIBE (Pro) | Paddle checkout | Navigates to `/subscribe?plan=pro&interval=month`, which requires trade sign-in first (`03-subscribe-page.png`) | PASS (gate) |
| 5 | Sign in as trade account | Session established, checkout or current-plan state | Account already subscribed: "You're on the Team plan — ACTIVE, 15 users included (2 in use)" + MANAGE SUBSCRIPTION (`04-subscribe-signin-filled.png`, `05-subscribe-after-signin.png`) | PASS |

Paddle checkout overlay itself was not reachable with this account because it already holds an active Team subscription; a fresh tenant account is needed to capture the checkout overlay.

**Overall: PARTIAL** — pricing renders and subscribe gating works, but production Paddle is wired to the sandbox environment (QE-W3) and the live checkout overlay is unproven in this pass.
