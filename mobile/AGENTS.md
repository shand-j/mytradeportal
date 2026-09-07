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
