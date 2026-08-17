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

## Lint

```bash
pnpm lint
```

## Structure

- `src/theme/` — theming and white-label branding.
- `src/contexts/` — auth and global state.
- `src/navigation/` — onboarding, trade, and customer navigators.
- `src/screens/` — screen components.
- `src/components/ui/` — themed UI primitives.
