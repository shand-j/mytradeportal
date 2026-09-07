# Running the iOS app in Xcode

How to build and run the My Trade Portal mobile app (`services/pwa`, Expo +
React Native) on the iOS Simulator via Xcode. Verified on Xcode 26.6 with the
iPhone 17 simulator (iOS 26.5).

The native `ios/` project is **generated** (git-ignored) — you create it locally
with `expo prebuild`. Everything below is run from the repo root unless noted.

---

## 1. Prerequisites

| Tool | Notes |
|---|---|
| macOS + **full Xcode** | Not just Command Line Tools. Install from the App Store or developer.apple.com. |
| An iOS Simulator runtime | Xcode ▸ Settings ▸ Components (e.g. iOS 26.5). |
| Node ≥ 20 + **pnpm** | This is a pnpm workspace. |
| CocoaPods | `brew install cocoapods` (or `sudo gem install cocoapods`). |
| Watchman (optional) | `brew install watchman` — smoother Metro file watching. |

### Point the toolchain at full Xcode

`expo run:ios` and `xcodebuild` need the active developer directory to be Xcode,
not the Command Line Tools. Check it:

```bash
xcode-select -p        # if this prints /Library/Developer/CommandLineTools, switch it
```

Persistent switch (recommended, needs your password once):

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept     # first run only
```

Or, without sudo, set it per shell for every command below:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
```

---

## 2. Install dependencies

```bash
pnpm install                 # from the repo root (installs the whole workspace)
```

The app consumes the workspace package `@mtp/shared-ts` (theme tokens). It is
symlinked automatically by pnpm; no build step is required.

---

## 3. Generate the native iOS project

```bash
cd services/pwa
npx expo prebuild -p ios --clean
```

This regenerates `services/pwa/ios/` from `app.json` and runs `pod install`
(~100 pods). It also writes `ios/.xcode.env.local` with your local Node path,
which is why `ios/` is git-ignored.

---

## 4a. Fastest path — one command

```bash
cd services/pwa
pnpm ios          # = expo run:ios: builds, installs, launches, and starts Metro
```

Pick a specific simulator if needed:

```bash
pnpm exec expo run:ios --device "iPhone 17"
```

## 4c. Connected manual testing (against the Docker backend)

To exercise the **real** wired flows (login, quotes, jobs, leads, invoices,
onboarding, the customer portal) the app must point at a running backend. One
script orchestrates everything — it brings up the API in dev mode with local
auth + demo seed data, then builds, installs, launches the app and starts Metro
in **connected** mode:

```bash
cd services/pwa
pnpm ios:connected            # = bash scripts/run-ios.sh  (defaults to iPhone 17)
pnpm ios:connected "iPhone 16 Pro"   # pick a different simulator
```

What it sets up:

- Backend: `services/pwa/e2e/start-stack.sh` (Docker) — API in `development`
  mode with **Supabase disabled** (so local bcrypt login works), rate limiting
  off, and the demo tenant seeded (`owner@demo.trade`, plus quotes / jobs / a
  lead so screens have data). Idempotent.
- App: `EXPO_PUBLIC_API_BASE_URL=http://localhost:8000` is inlined into the JS
  bundle. The iOS Simulator shares the host network, so `localhost:8000` reaches
  the Docker-published API. (A physical device needs the host's LAN IP.)
- `EXPO_PUBLIC_SETUP_TOKEN` is set so the in-app **Register my business** flow
  provisions a real tenant (the dev API leaves `POST /tenants` open).

Sign in once it's running:

| Who | How |
|---|---|
| **Electrician** | Tap **Electrician login** → **Sign in** (pre-filled `owner@demo.trade` / `demo123`). |
| **Homeowner (branded)** | Enter code **123456** at the entry → opens the "Demo" business → **Request a quote** or **Customer login**. |
| **Homeowner (account)** | Tap **Customer login** → **Create an account** to register, or sign in. |

Keep the script running — it serves Metro (the JS bundle) and hot-reloads JS
edits. `Ctrl-C` to stop; re-run to relaunch.

Notes:
- Already have the stack up? Skip the Docker step: `SKIP_BACKEND=1 pnpm ios:connected`.
- Run **without** the script (demo mode, no backend) with `pnpm ios` — the app
  falls back to mock data and the pre-filled demo credentials.
- A one-time iOS system prompt ("Allow widgets from Maps to use your location")
  can appear over the entry screen — tap **Don't Allow**; it's unrelated to the app.

## 4b. Open and run in Xcode (GUI)

```bash
cd services/pwa
open ios/MyTradePortal.xcworkspace     # ALWAYS the .xcworkspace, never the .xcodeproj
```

In Xcode:

1. Scheme: **MyTradePortal**.
2. Destination: an iOS Simulator (e.g. **iPhone 17**).
3. Press **▶ Run** (⌘R).

In **Debug**, the app loads its JavaScript from Metro. Start Metro in a terminal
(leave it running) before or just after pressing Run:

```bash
cd services/pwa
pnpm start        # Metro on http://localhost:8081
```

The app connects to Metro automatically on the simulator. Edit JS/TS and it
hot-reloads.

---

## 5. Command-line build (CI-style verification)

To confirm the app compiles without opening the GUI:

```bash
cd services/pwa
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
xcodebuild \
  -workspace ios/MyTradePortal.xcworkspace \
  -scheme MyTradePortal \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath ios/build \
  CODE_SIGNING_ALLOWED=NO build
```

Expect `** BUILD SUCCEEDED **`. The app bundle lands at
`ios/build/Build/Products/Debug-iphonesimulator/MyTradePortal.app`.

Install and launch it on a booted simulator (with Metro running):

```bash
xcrun simctl boot "iPhone 17" 2>/dev/null || true
xcrun simctl install "iPhone 17" ios/build/Build/Products/Debug-iphonesimulator/MyTradePortal.app
xcrun simctl launch "iPhone 17" com.mytradeportal.mobile
```

---

## App facts

| | |
|---|---|
| Scheme / target | `MyTradePortal` |
| Bundle identifier | `com.mytradeportal.mobile` |
| Minimum iOS | 16.4 |
| New Architecture | disabled (`app.json` → `ios.newArchEnabled: false`) |
| JS entry | `expo-router/entry` (file-based routes in `app/`) |

---

## Troubleshooting

- **"Unable to find a device matching the provided destination specifier".**
  The device name must exist for the *latest* installed runtime, or specify the
  OS explicitly. `name=iPhone 17` matches iOS 26.5; for older sims use
  `name=iPhone 16,OS=18.0`. List devices with `xcrun simctl list devices available`.

- **`xcodebuild requires Xcode` / build can't find `simctl`.** The active
  developer dir is Command Line Tools. Fix with `sudo xcode-select -s
  /Applications/Xcode.app/Contents/Developer` or export `DEVELOPER_DIR` (§1).

- **Edits don't show up on the simulator.** Metro caches aggressively; if it was
  started with `CI=1` it won't watch files. Restart it with a clean cache:
  `pnpm start --clear` (or `npx expo start --clear`).

- **Red screen: "Unable to resolve module @mtp/shared-ts".** Run `pnpm install`
  at the repo root so the workspace symlink exists, then restart Metro with
  `--clear`.

- **Pod errors after changing native config or SDK.** Re-run
  `npx expo prebuild -p ios --clean` (regenerates `ios/` and reinstalls pods).

- **Wrong Node found during the Xcode build.** `ios/.xcode.env.local` pins the
  Node path; it is regenerated by `expo prebuild`. Re-run prebuild if you change
  Node versions.

---

See also: [`services/pwa/README.md`](../../services/pwa/README.md) and
[`AGENTS.md`](../../AGENTS.md) (Mobile iOS app section).
