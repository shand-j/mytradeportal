# H2 — TryDemo interactive AI quote (hero `#try-ai`)

- **Actor:** public visitor (unauthenticated)
- **Surface:** https://www.mytradeportal.co.uk/ → hero demo phone → `POST /demo/quotes/generate` (live LLM, no auth)
- **Preconditions:** demo not yet used from this IP/browser (one-try limit)
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Load home, see demo phone | "New quote" form with job description textarea | Rendered (`01-nav-hero.png`) | PASS |
| 2 | Fill description: "Replace consumer unit in 3-bed semi, 10 circuits. Include new RCBO board, surge protection, earth bonding to gas and water, testing and certification." | Text accepted, counter 150/4000 | Filled (`02-description-filled.png`) | PASS |
| 3 | Click GENERATE QUOTE | Loading state | Clicked (`03-generating.png`) | PASS |
| 4 | Wait for LLM | Guide-priced ex-VAT line items with totals | **Generated in 15.6s · grounded**: 5 line items (£260 labour, £145 consumer unit w/ SPD, £50 gas bonding, £50 water bonding, £130 testing), AI confidence 40%, assumptions text, Subtotal £635 / VAT £127 / Total £762 (`04-demo-quote-result.png`, full text in `demo-result.txt`) | PASS |
| 5 | Revisit / retry demo from same IP | — | One-try limit shown: "You've already tried the AI demo — download the app for unlimited quotes" (`05-demo-one-try-limit.png`) | PASS (by design; see QE-W4) |

The live production LLM returned sane UK guide prices. "Refine with AI" affordance present but not exercised (would have consumed the single demo try).

**Overall: PASS**
