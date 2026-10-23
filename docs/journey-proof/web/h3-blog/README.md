# H3 — Blog index + article

- **Actor:** public visitor
- **Surface:** https://www.mytradeportal.co.uk/blog and `/blog/:slug`
- **Captured:** 2026-10-23, production

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/blog` | Blog index renders | Rendered (`01-blog-index.png`) | PASS |
| 2 | Open first post (`/blog/ai-in-the-trades`) | Article renders | "AI in the trades: what it can (and can't) do for electricians in 2026", dated 8 September 2026, full article + CTA (`02-blog-post.png`, URL in `post-url.txt`) | PASS |

**Overall: PASS**
