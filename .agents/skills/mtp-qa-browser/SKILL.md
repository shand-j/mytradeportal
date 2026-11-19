---
name: mtp-qa-browser
description: Drive a real browser against MyTradePortal (web back-office, landing site, tenant portal, API) using the Playwright CLI — navigate, fill forms, click, snapshot the accessibility tree, capture screenshots, monitor console/network. Use for any manual or agentic UI testing, bug reproduction, login/auth flows, magic-link email flows via Mailpit, or visual checks of mytradeportal pages.
---

# Browser driving for MyTradePortal QA

Drive Chromium from the terminal with the Playwright CLI. Every other `mtp-qa-*`
skill depends on this one.

## Invocation

The binary is **not** installed in this repo. Always invoke it as:

```bash
npx -y @playwright/cli <command>
```

(The command prints itself as `playwright-cli`. If a global `playwright-cli`
binary exists on the machine it works too — but never assume it; use the `npx`
form in scripts and examples.)

First use downloads the package. If Chromium is missing, run
`npx playwright install chromium` (the repo already has Playwright for its e2e
suites, so the browser is usually present).

## Core workflow

```bash
npx -y @playwright/cli open http://demo.localhost:3000
npx -y @playwright/cli snapshot                 # accessibility tree → YAML file, elements get refs like e5
npx -y @playwright/cli fill e5 "admin@demo.example.com"
npx -y @playwright/cli click e8
npx -y @playwright/cli snapshot                 # re-snapshot after EVERY state change
npx -y @playwright/cli screenshot --filename=shot.png
npx -y @playwright/cli close
```

Key commands: `goto`, `snapshot [--filename=f.yml]`, `find <text|regex>` (search
the snapshot), `click/fill/type/press/hover/select/check/uncheck <ref>`,
`eval <js> [ref]`, `screenshot [--filename=f.png] [ref]`, `go-back/reload`,
`resize <w> <h>`, `tab-new/tab-list/tab-select`, `console [level]`, `network`,
`dialog-accept/dialog-dismiss`, `state-save/state-load <file>`,
`route/unroute` (request mocking), `tracing-start/stop`, `video-start/stop`.
Refs (`e5`, `e12`, …) come from the most recent snapshot and go stale after
navigation — re-snapshot.

Full command reference: see `references/` in this skill directory
(session management, storage state, request mocking, running raw Playwright
code, tracing, video).

## MyTradePortal targets

| Surface | Local URL | Notes |
|---|---|---|
| Web back-office (React SPA) | `http://demo.localhost:3000` | **Tenant subdomain matters** — use `demo.localhost`, not bare `localhost`; the app resolves tenancy from the host. Served by the `mtp_web` container or `cd web/app && pnpm dev`. |
| FastAPI backend | `http://demo.localhost:8000` | OpenAPI UI at `/docs`. |
| Landing site + customer portal | `http://localhost:3000` via `cd "web/landing/new design/app" && pnpm dev` | **Port clash:** the landing dev server also wants 3000 — run it OR web/app, not both, or pass `--port`. Portal pages: `/quote/:token`, `/invoice/:token`, `/pay/:token`, `/reset-password`, `/fair-use`. |
| Mailpit | `http://localhost:8025` | All dev email (magic links, invites, quote/invoice emails, reminders) lands here. API on `/api/v1/messages`. |
| MinIO console | `http://localhost:9001` | Object storage for uploads. |

Stack startup: `docker compose up -d` (full) or
`docker compose up -d postgres redis qdrant minio mailpit` for data infra only.
**Check `docker info` first** — if the daemon is down, nothing above works.

Chromium resolves `*.localhost` to loopback natively, so `demo.localhost` needs
no `/etc/hosts` entry.

## Credentials

- Web e2e admin: tenant slug `demo`, `admin@demo.example.com` / `e2e-password-123`
  (seeded by the e2e bootstrap; cookie-based session, cookie name `session`).
- Mobile/demo trade account: `owner@demo.trade` / `demo123` (real seeded user).
- Customer portal uses invisible magic-link auth — request the link, then read
  it from Mailpit (see recipe below).

## Recipe: fast login via API + cookie injection

UI login is slow and flaky for repeated runs. Get a session cookie from the API
and inject it:

```bash
TOKEN=$(curl -s -c - -X POST http://demo.localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"tenant_slug":"demo","email":"admin@demo.example.com","password":"e2e-password-123"}' \
  | awk '/^demo.localhost.*session/{print $NF}')
npx -y @playwright/cli open http://demo.localhost:3000
npx -y @playwright/cli cookie-set session "$TOKEN" --domain=demo.localhost --httpOnly
npx -y @playwright/cli goto http://demo.localhost:3000/dashboard
```

Then `state-save auth.json` once and `state-load auth.json` in later sessions.
See `references/storage-state.md`.

## Recipe: customer magic-link via Mailpit

1. In the portal, submit the email form (or `POST` the magic-link endpoint).
2. `curl -s http://localhost:8025/api/v1/messages | jq '.messages[0].ID'` then
   fetch the body, or open `http://localhost:8025` in the browser and click
   through.
3. Extract the `http://…/auth/…token…` link and `goto` it in the test browser.

## Recipe: watching for silent failures (bug hunting)

Silent console/network errors are the top source of "looks green, actually
broken":

```bash
npx -y @playwright/cli console          # all console messages; add level filter: console error
npx -y @playwright/cli network          # requests with statuses — look for 4xx/5xx and failed fetches
```

Run both after every navigation and every form submit while exploring. A page
that renders but fires a 500 on load is a bug, not a pass.

## Recipe: visual/styling review

Screenshots are evidence you can inspect directly:

```bash
npx -y @playwright/cli resize 1440 900 && npx -y @playwright/cli screenshot --filename=desktop.png
npx -y @playwright/cli resize 390 844 && npx -y @playwright/cli screenshot --filename=mobile.png
```

Then read the PNG with the ReadMediaFile tool and check against the shared
theme tokens in `packages/shared/ts` (colors, spacing, radii, typography).
Check: overflow/horizontal scroll at 390px, clipped text, inconsistent
button/card styling, broken images, light-mode-only assumption (dark mode is
post-MVP — flag any auto-dark rendering).

## Gotchas

- **Refs go stale.** After `goto`, submits, or dialog open/close, re-snapshot
  before interacting.
- **Empty/malformed snapshot YAML is a hard stop** — report it; don't guess the
  page state from memory.
- **Docker daemon down** = all local URLs dead. Verify with `docker info`
  before concluding the app is broken.
- The mobile app (`mobile/`) is iOS/React Native; its Playwright e2e drives a
  **web build** — mobile-specific UI bugs need the Expo dev server or a
  simulator, not this CLI.
- `mobile/e2e/run.sh` and `start-stack.sh` still reference the deleted
  `services/pwa` path (known issue) — don't trust them; drive the stack
  directly.
