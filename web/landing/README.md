# My Trade Portal — landing site

The live marketing site + customer-facing pages (portal, quote/invoice/pay,
help centre) is the React + Vite app in `new design/app/` — this is what
Railway builds and serves at www.mytradeportal.co.uk.

The earlier Next.js implementation that lived at this directory root was
removed (2026-10): unreferenced by the workspace/deploys and dragging stale
next/sharp advisories into the dependency audit gate.

## Local install/build (deterministic)

Use the repository root workspace install (frozen lockfile), then run landing
commands from the active app directory:

```bash
corepack pnpm install --frozen-lockfile
cd "web/landing/new design/app"
corepack pnpm build
corepack pnpm typecheck:e2e
```

Do not use `pnpm install --ignore-workspace` in the landing app directory.
That creates an ad-hoc local lockfile and bypasses the committed workspace
dependency graph used by CI and production builds.
