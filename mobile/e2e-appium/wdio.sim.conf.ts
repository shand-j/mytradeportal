/**
 * Simulator variant of the device E2E config.
 *
 * Used for marketing clip recording (and any simulator-based runs): points
 * at the booted iPhone 17 Pro simulator, drops real-device signing, and lets
 * Appium build WDA fresh (the prebuilt WDA in WDA_DERIVED_DATA_PATH is a
 * device build).
 *
 *   pnpm exec wdio run wdio.sim.conf.ts --spec specs/90-marketing-pt1.spec.ts
 */
import { config as baseConfig } from "./wdio.conf";

export const config = {
  ...baseConfig,
  specs: ["./specs/**/*.spec.ts"],
  // LLM quote generation regularly exceeds the base 5-minute mocha timeout;
  // marketing specs drive the full generation flow end-to-end. NB: mocha's
  // `timeout: 0` disable-flag is mangled by WDIO's adapter (it computes
  // 0 - 3 = -3 and clamps to 1ms), so use a large explicit value instead.
  mochaOpts: { ...baseConfig.mochaOpts, timeout: 1200000 },
  capabilities: [
    {
      platformName: "iOS",
      "appium:automationName": "XCUITest",
      "appium:udid":
        process.env.SIM_UDID ?? "0A81AB89-D2DA-468A-8D07-A9D241AC6DA2",
      "appium:bundleId": "com.mytradeportal.mobile",
      "appium:noReset": true,
      "appium:fullReset": false,
      "appium:dontStopOnReset": true,
      "appium:newCommandTimeout": 300,
      "appium:useNewWDA": false,
      "appium:usePrebuiltWDA": false,
      "appium:wdaLaunchTimeout": 240000,
      "appium:wdaConnectionTimeout": 240000,
      // Keep the RN dev server requirement off: Release simulator builds
      // embed the JS bundle.
      // Simulator-only: SpringBoard permission prompts (push/location) are
      // auto-accepted. The device config deliberately keeps these manual —
      // specs exercise the dialogs — but marketing runs must never stall
      // on them mid-clip.
      "appium:autoAcceptAlerts": true,
      "appium:autoDismissAlerts": false,
      "appium:shouldTerminateApp": true,
      "appium:forceAppLaunch": true,
    },
  ],
};
