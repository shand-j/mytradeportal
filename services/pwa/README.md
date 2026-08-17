# My Trade Portal — iOS App

React Native + Expo mobile app for UK electricians and their customers.

## Setup

```bash
cd services/pwa
pnpm install
```

## Run

```bash
pnpm start   # Expo dev server
pnpm ios     # iOS simulator (requires macOS + full Xcode)
```

### Build & run in Xcode

The native `ios/` project is generated (git-ignored). Generate it, then open the
workspace:

```bash
npx expo prebuild -p ios --clean          # regenerates ios/ + runs pod install
open ios/MyTradePortal.xcworkspace        # open in Xcode (use the .xcworkspace)
pnpm start                                # Metro must run for Debug builds
```

Full step-by-step, command-line build, and troubleshooting:
[`../../docs/runbooks/ios-xcode.md`](../../docs/runbooks/ios-xcode.md).

## Backend connection (demo vs connected mode)

The app runs in one of two modes depending on whether an API base URL is set:

- **Demo mode (default)** — no backend required. Login accepts the pre-filled demo
  credentials and every screen is populated from local mock data in `src/data/`.
  This is what powers the marketing video and offline showcase.
- **Connected mode** — set `EXPO_PUBLIC_API_BASE_URL` to a running `services/api`
  instance. Trade login then calls the real `POST /auth/token` endpoint, stores the
  bearer token in the iOS Keychain (`expo-secure-store`), and wired screens fetch
  live data (e.g. the dashboard "Outstanding quotes" total shows a **LIVE** badge).
  If the backend is unreachable the app falls back to demo mode so a beta build is
  never left unusable.

```bash
# Point the app at a local backend, then start Metro
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm start
```

`EXPO_PUBLIC_*` variables are inlined by Metro at bundle time, so restart the dev
server after changing it.

**Manual testing on the iOS Simulator against Docker** — one command brings up
the backend (dev + local auth + demo seed) and launches the app connected:

```bash
pnpm ios:connected     # iPhone 17 by default; e.g. pnpm ios:connected "iPhone 16 Pro"
```

See [`../../docs/runbooks/ios-xcode.md`](../../docs/runbooks/ios-xcode.md#4c-connected-manual-testing-against-the-docker-backend)
for login credentials and details.

## Lint

```bash
pnpm lint
```

## Connected-mode E2E

`e2e/` holds a Playwright smoke suite that drives the app (served as web) against
a real API stack — proving the wired flows end-to-end: trade login → live
dashboard/quotes/jobs, business onboarding → a real tenant, and white-label
branding from `/businesses/{slug}/public-config`.

```bash
# One-shot: bring up the API stack + seed, then run both suites (requires Docker)
pnpm test:e2e

# Or run a single suite against an already-running stack (see e2e/start-stack.sh)
pnpm test:e2e:trade
pnpm test:e2e:white-label
```

Notes:
- `e2e/start-stack.sh` starts the API in dev mode with local auth (Supabase
  disabled via `docker-compose.e2e.yml`) and seeds the demo tenant + owner
  (`owner@demo.trade` / `demo123`) plus a quote and a job.
- The web build is a test harness for the native app (which has no CORS), so
  Chromium runs with web security disabled.
- The trade and white-label suites use different `EXPO_PUBLIC_*` builds, so they
  run sequentially on the same port (never concurrently).
- CI runs this via `.github/workflows/pwa-e2e.yml`.

## Structure

- `src/theme/` — theming and white-label branding.
- `src/contexts/` — auth and global state.
- `src/navigation/` — onboarding, trade, and customer navigators.
- `src/screens/` — screen components.
- `src/components/ui/` — themed UI primitives.
