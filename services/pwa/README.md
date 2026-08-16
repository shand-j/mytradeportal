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
