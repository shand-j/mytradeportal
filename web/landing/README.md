# My Trade Portal — landing page

Marketing site: brand-forward hero, feature showcases with demo-video slots,
and Paddle-localised pricing. Next.js App Router, plain CSS (design tokens in
`app/globals.css`), deployed as a standalone Node server (Railway-ready).

## Hallmark build record

- Macrostructure: Marquee Hero · Nav: N5 floating pill · Footer: Ft5 statement
- Theme: custom (brand anchor supplied — slate `#0F1E26`, hi-vis yellow `#FFC107`)
- Genre: modern-minimal, utilitarian worksite voice
- Honest-copy discipline: no invented metrics, testimonials or stats anywhere
- Responsive floor: 320 / 375 / 414 / 768 verified, `overflow-x: clip`

## Develop

```bash
pnpm install
cp .env.example .env.local   # fill in (see below)
pnpm dev                     # http://localhost:3100
```

## Env (`.env.local`, gitignored)

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_TESTFLIGHT_URL` | Public TestFlight join link — every beta CTA points here. Swap for the App Store URL at launch. |
| `NEXT_PUBLIC_PADDLE_ENV` | `sandbox` (default) or `production`. |
| `NEXT_PUBLIC_PADDLE_CLIENT_TOKEN` | Paddle client token for the matching environment. |
| `NEXT_PUBLIC_PADDLE_PRICE_{STARTER,PRO,BUSINESS}_{MONTH,YEAR}` | Price IDs (`pri_...`) from the matching Paddle catalog. Unset tiers show "Beta — free". |

Pricing is pulled live with `Paddle.PricePreview()` — localised to the
visitor's country with tax included. The monthly/yearly toggle appears only
when yearly price IDs are configured.

## Media

Demo-video slots live in `public/media/` — see `public/media/README.md`.
Poster frames (real screenshots from the product recordings) ship in
`public/media/posters/` so the page looks finished before the AI-generated
iPhone renders arrive.
