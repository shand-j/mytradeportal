/**
 * App lifecycle helpers. The TestFlight build is already installed; we launch
 * and terminate it by bundle id, never reinstall.
 */
import { BUNDLE_ID } from "./env";
import { waitAppReady } from "./ui";

/** Fresh launch: terminate if running, then launch. */
export async function relaunchApp() {
  const state = await driver.queryAppState(BUNDLE_ID);
  if (state === 4) {
    await driver.terminateApp(BUNDLE_ID);
    await driver.pause(500);
  }
  await driver.activateApp(BUNDLE_ID);
  await waitAppReady();
  // Allow the splash/router to settle.
  await driver.pause(1500);
}

/** Send the app to the background for `seconds` (notification tests). */
export async function backgroundApp(seconds: number) {
  await driver.background(seconds);
  await waitAppReady(15000);
}
