/**
 * MARKETING — clip 06 standalone retake (dashboard overview).
 *
 * Retake after the demo-data VAT fix so the stat cards show realistic
 * outstanding-quote values.
 *
 *   E2E_TENANT_SLUG=hartley-electrical \
 *   E2E_TRADE_EMAIL=tom@hartleyelectrical.example.com E2E_TRADE_PASSWORD='Sparky2026!' \
 *   pnpm exec wdio run wdio.sim.conf.ts --spec specs/95-marketing-dashboard.spec.ts
 */
import { loginAsTrade } from "../helpers/auth";
import { relaunchApp } from "../helpers/app";
import { handlePermissionAlert, swipeUp, tapBack, tapId, waitForText } from "../helpers/ui";
import { abortClip, startClip, stopClip } from "../demo/recorder";

const TOM_EMAIL = "tom@hartleyelectrical.example.com";
const TOM_PASSWORD = "Sparky2026!";

afterEach(async function () {
  const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
  if (state === "failed") await abortClip();
});

describe("M1d: marketing clip 06 — dashboard overview (retake)", () => {
  before(function () {
    this.timeout(0);
  });

  it("06-dashboard-overview", async () => {
    await loginAsTrade(TOM_EMAIL, TOM_PASSWORD);
    await handlePermissionAlert("allow");
    await relaunchApp();
    await waitForText("Dashboard", 25000);

    await startClip("06-dashboard-overview");
    await driver.pause(3000);
    await swipeUp();
    await driver.pause(2000);
    await swipeUp();
    await driver.pause(2000);
    await tapId("tab-dashboard");
    await driver.pause(1500);
    await tapId("notifications-bell-trade");
    await driver.pause(2500);
    await tapBack();
    await driver.pause(1000);
    await tapId("dashboard-more");
    await driver.pause(2500);
    await stopClip("06-dashboard-overview");
  });
});
