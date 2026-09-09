/**
 * Smoke test: proves the harness can drive the installed app on the real
 * device. Every other spec depends on this working.
 */
import { relaunchApp } from "../helpers/app";
import { byId, hasText, waitAppReady } from "../helpers/ui";
import { BUNDLE_ID } from "../helpers/env";

describe("smoke: app launches on device", () => {
  it("is installed and reaches the foreground", async () => {
    const installed = await driver.isAppInstalled(BUNDLE_ID);
    if (!installed) {
      throw new Error(
        `App ${BUNDLE_ID} is not installed on the device. Install the TestFlight build first.`
      );
    }
    await relaunchApp();
    expect(await driver.queryAppState(BUNDLE_ID)).toBe(4);
  });

  it("renders the entry screen or restores a session", async () => {
    // Either the unauthenticated entry screen or a restored session surface.
    const onEntry =
      (await byId("entry-trade-login").isExisting()) ||
      (await byId("entry-customer-login").isExisting());
    const inSession = await hasText("Dashboard").catch(() => false);
    expect(onEntry || inSession).toBe(true);
    await waitAppReady();
  });
});
