# H1 — Marketing home page (`/`)

- **Actor:** public visitor (unauthenticated)
- **Surface:** https://www.mytradeportal.co.uk/
- **Preconditions:** none
- **Captured:** 2026-10-23, Playwright Chromium 1440x900 (plus 390x844 nav variant), production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/` | Page loads, nav visible | 200, full nav bar with section anchors + JOIN THE BETA CTA (`00-nav.png`, mobile `00b-nav-mobile.png`) | PASS |
| 2 | Hero (`#try-ai`) | Headline + embedded AI quote demo phone | Renders; demo phone shows "New quote" form (`01-hero-try-ai.png`) | PASS |
| 3 | Marquee | Scrolling trades strip | Renders (`02-marquee.png`) | PASS |
| 4 | TradesStrip | Trade icons/labels | Renders (`03-trades-strip.png`) | PASS |
| 5 | Statement | Brand statement section | Renders (`04-statement.png`) | PASS |
| 6 | Problem | Problem section | Renders (`05-problem.png`) | PASS |
| 7 | Showcase (`#features`) | Product screenshots/features | Renders (`06-showcase.png`) | PASS |
| 8 | VideoDemo | Video demo section | Renders (`07-video-demo.png`) | PASS |
| 9 | HowItWorks (`#how`) | 3-step explainer | Renders (`08-how-it-works.png`) | PASS |
| 10 | Pricing (`#pricing`) | 3 tiers with prices | Renders £25/£39/£69 per business/mo (`09-pricing.png`) — see h4-pricing for live/static analysis | PASS |
| 11 | Testimonials (`#reviews`) | Review cards | Renders (`10-testimonials.png`) | PASS |
| 12 | FinalCta (`#cta`) | CTA band | Renders (`11-final-cta.png`) | PASS |
| 13 | Footer | Links, copyright | Renders (`12-footer.png`) | PASS |

`00-full-page.png` is a full-page capture of the whole page (resized to 1600px). `sections.json` lists the DOM section order used for the capture. The sticky nav appearing mid-page in some full-page screenshots is a screenshot artifact of sticky-position capture, not a layout bug.

**Overall: PASS**
