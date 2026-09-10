import { BUNDLE_ID, DEVICE_UDID, TEAM_ID } from "./helpers/env";

export const config = {
  runner: "local" as const,
  tsConfigPath: "./tsconfig.json",
  specs: ["./specs/**/*.spec.ts"],
  exclude: [],
  maxInstances: 1,
  capabilities: [
    {
      platformName: "iOS",
      "appium:automationName": "XCUITest",
      "appium:udid": DEVICE_UDID,
      "appium:bundleId": BUNDLE_ID,
      "appium:xcodeOrgId": TEAM_ID,
      "appium:xcodeSigningId": "Apple Development",
      // Launch the already-installed TestFlight build; never reinstall/resign.
      "appium:noReset": true,
      "appium:fullReset": false,
      "appium:dontStopOnReset": true,
      "appium:newCommandTimeout": 300,
      "appium:useNewWDA": false,
      "appium:usePrebuiltWDA": true,
      "appium:derivedDataPath": process.env.WDA_DERIVED_DATA_PATH ?? "/Users/home/Library/Developer/Xcode/DerivedData/WebDriverAgent-djaxkwladvjtfpeaepewxzgirrdk",
      "appium:wdaLaunchTimeout": 240000,
      "appium:wdaConnectionTimeout": 240000,
      // System permission dialogs (notifications/location/photos) are part of
      // what we test — never auto-accept them.
      "appium:autoAcceptAlerts": false,
      "appium:autoDismissAlerts": false,
      "appium:shouldTerminateApp": true,
      "appium:forceAppLaunch": true,
    },
  ],
  logLevel: "warn",
  bail: 0,
  waitforTimeout: 20000,
  connectionRetryTimeout: 240000,
  connectionRetryCount: 3,
  services: [
    [
      "appium",
      {
        // Absolute path: the workspace devDependency `appium` shadows the
        // global one on PATH and has no drivers installed.
        command: "/opt/homebrew/bin/appium",
        args: {
          relaxedSecurity: false,
          address: "127.0.0.1",
        },
      },
    ],
  ],
  framework: "mocha",
  reporters: ["spec"],
  mochaOpts: {
    ui: "bdd",
    timeout: 300000,
    retries: 0,
  },
};
