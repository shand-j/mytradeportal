# My Trade Portal — iOS App

React Native + Expo mobile app for UK electricians and their customers.

## Setup

```bash
cd mobile
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

## Backend connection (connected mode)

The Beta build runs in **connected mode** against a real `services/api` backend.
Set `EXPO_PUBLIC_API_BASE_URL` to a running API instance. Trade login then calls
`POST /auth/token`, stores the bearer token in the iOS Keychain
(`expo-secure-store`), and wired screens fetch live data.

`EXPO_PUBLIC_*` variables are inlined by Metro at bundle time, so restart the dev
server after changing them.

### Local backend via Docker

The mobile backend stack is in `docker-compose.mobile.yml`. It brings up Postgres,
Redis, Qdrant, MinIO, Mailpit, the FastAPI service on `http://localhost:8000`,
and the Django admin service on `http://localhost:8001` with local bcrypt auth
(no Supabase required).

```bash
# From the repo root
docker compose -f docker-compose.mobile.yml up -d

# In another terminal, point the iOS Simulator at the local API
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm ios
```

Trade users are created and authenticated through the mobile onboarding/login
flow (`POST /tenants` then `POST /auth/token`). The Django admin at
`http://localhost:8001/admin` is available for back-office support tasks such as
resetting a user's password or inspecting tenant data.

> **Auth mode:** `docker-compose.mobile.yml` defaults `SUPABASE_URL` and the
> Supabase keys to empty, so local bcrypt/JWT auth is used. If your `.env` sets
> real Supabase credentials, make sure the Supabase instance is reachable, or
> blank those variables for local development.

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
