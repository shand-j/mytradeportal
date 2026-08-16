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
pnpm ios     # iOS simulator (requires macOS + Xcode)
```

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
