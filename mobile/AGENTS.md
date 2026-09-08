# AGENTS.md — My Trade Portal Mobile

## Scope

This directory contains the React Native + Expo iOS app for the pivot.

## Tech stack

- React Native (via Expo SDK 57)
- TypeScript 5
- Expo Router v6 for file-based navigation
- NativeWind v4 for Tailwind styling
- Zustand for global state (auth, business theme)
- Shared theme tokens from `@mtp/shared-ts`

## Commands

```bash
cd mobile
pnpm install
pnpm start        # Expo dev server
pnpm ios          # iOS simulator (macOS only)
pnpm lint         # tsc --noEmit
```

## Architecture conventions

- `src/theme/` — theme provider + business branding override hooks (backed by Zustand `businessStore`).
- `src/contexts/` — thin compatibility wrappers around Zustand stores (keeps existing `useAuth` hook).
- `src/stores/` — Zustand stores (`authStore`, `businessStore`).
- `src/hooks/` — reusable hooks including `useNavigationAdapter` (React Navigation-compatible API over Expo Router).
- `src/components/navigation/` — custom bottom tab bar used by trade and customer route groups.
- `src/components/ui/` — reusable themed components (`Text`, `Button`, `Screen`, `Header`, `CodeInput`).
- `src/screens/` — one directory per user profile (trade, customer, onboarding).
- `app/` — Expo Router routes. Group routes: `(trade)` and `(customer)`.

## Notes

- Light mode only at launch; dark mode is post-MVP.
- White-label branding is fetched live from the backend (`fetchPublicConfig` in `src/api/businesses.ts`) for the target business slug; there is no offline demo/mock mode.
- Use shared theme tokens (`@mtp/shared-ts`) for colors, spacing, and typography.
- The old React Navigation navigators and `App.tsx` entry point were removed; the app now boots from `expo-router/entry` via `app/_layout.tsx`.
- **No Expo Go.** Development uses a dev-client build (`expo-dev-client` is a
  devDependency; `eas.json` has `development` / `development-simulator` /
  `preview` / `production` profiles). OTA hot fixes go through EAS Update
  (`eas update --branch production`).
- `EXPO_PUBLIC_API_BASE_URL` must be set in BOTH places: `eas.json` build
  profiles (used at `eas build` time) AND as an EAS project environment
  variable (used at `eas update` time — eas.json profile envs are NOT applied
  to OTA updates; an OTA published without it bricks the app's API connection).
  It is set on the `production`, `preview` and `development` EAS environments.
- pnpm: the repo root `.npmrc` pins `node-linker=hoisted` (required by Metro/Babel
  preset resolution — do not reintroduce an isolated linker or a `mobile/.npmrc`).
  Packages used by `babel.config.js` must be declared in `package.json`
  (e.g. `babel-preset-expo`).
- `react-native-gesture-handler` is pinned at 3.2.1, one major above SDK 57's
  expected ~2.32.0. Intentional — verify on device before downgrading.
