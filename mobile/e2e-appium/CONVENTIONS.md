# E2E Appium conventions (read before writing specs)

Target: real iPhone, XCUITest, installed TestFlight build (`com.mytradeportal.mobile`).
 NEVER reinstall or reset the app; use `relaunchApp()` between specs.

## Helpers (import from `../helpers/…` — do NOT modify helpers; add local
functions inside your own spec file if needed)

- `helpers/ui.ts`: `byId(testID)` → `~id` accessibility-id query;
  `textEl(label)` / `textElContains(label)` → StaticText by label;
  `waitForText/waitForId`, `tapText/tapId`, `hasText`, `scrollToTextAndTap`,
  `swipeUp`, `tapBack` (Header back, `back-button`), `handlePermissionAlert("allow"|"deny")`
  for SpringBoard permission prompts, `dismissAlertIfAny`, `waitAppReady`.
- `helpers/app.ts`: `relaunchApp()`, `backgroundApp(seconds)`.
- `helpers/auth.ts`: `loginAsTrade(email, password)`, `loginAsCustomer(email, password)`,
  `ensureLoggedOut()`.
- `helpers/api.ts`: `TRADE_EMAIL/TRADE_PASSWORD/CUSTOMER_EMAIL/CUSTOMER_PASSWORD`
  (from env; `tradeCredsConfigured()` / `customerCredsConfigured()` guards),
  `loginTradeApi()` → `{ tenantId, tenantSlug, token }`, `apiGet/apiPatch(ctx, path)`,
  `dbConfigured()` + pg readers `findContactByEmail`, `findTenantBySlug`,
  `findQuotesByTitle`, `findQuoteRequestsByTitle`, `findPushTokenByData`,
  `countRows`, `deleteTestData(whereSql, params)`, `closeDb`.

## Hard rules

1. Every created record uses a unique suffix: `const tag = Date.now().toString(36)`
   embedded in names/titles/emails, e.g. `E2E Customer ${tag}`. Assert
   persistence via helpers/api (API GET or pg read) using the tag. Delete what
   you create at spec end (`after` hook) with `deleteTestData` or API DELETE
   where available — production DB, leave it clean.
2. Specs that need missing credentials must skip, not fail:
   `if (!tradeCredsConfigured()) { it.skip = true return }` pattern:
   ```ts
   describe("...", () => {
     if (!tradeCredsConfigured()) { console.log("SKIP: E2E_TRADE_EMAIL/PASSWORD not set"); return; }
   ```
3. Selector preference: `testID` (byId) where the component has one — grep the
   screen source first; visible button text via `tapText` as fallback
   (RN Pressable receives child taps). RN TextInput by its `testID`, set value
   with `el.setValue(...)` then `driver.hideKeyboard().catch(()=>{})`.
4. Waits: default `waitForText/waitForId` 15 s; network journeys 25 s.
   `driver.pause(300–800)` after navigation.
5. One `describe` per UI surface/journey, numbered file prefix, e.g.
   `11-trade-quotes.spec.ts`. Always `relaunchApp()` in the first `it` or
   `before` to get a known state; use `ensureLoggedOut()` for pre-auth specs.
6. TypeScript strict, no `any` unless unavoidable. `driver` is a global
   (WebdriverIO). Run `pnpm exec tsc --noEmit` from `mobile/e2e-appium`
   before finishing; it must pass.
7. Do NOT run wdio/device tests — the device is reserved to the parent.
8. Assert what the user sees AND what the DB stores ("data entered ⇒ persisted").
   Cross-check numbers shown in UI against API values where practical.
9. iOS quirks: bottom tab bar testIDs — trade: `tab-dashboard`, `tab-quotes`,
   `tab-customers`, `tab-calendar`, `tab-messages`; customer: `tab-requests`,
   `tab-calendar`, `tab-messages`, `tab-profile`. Three-dot settings:
   `header-settings`. Logout: `settings-logout` on the settings screen.
   Permission alerts: `handlePermissionAlert` right after an action that
   triggers the prompt (notifications, location, photos).

## Env (already configured unless noted)

`MTP_API_BASE` (prod Railway API), `MTP_DB_URL` (pg via Railway TCP proxy),
`E2E_TRADE_EMAIL`/`E2E_TRADE_PASSWORD` (electrician account — user provides),
`E2E_CUSTOMER_EMAIL`/`E2E_CUSTOMER_PASSWORD` (existing customer account).
