/**
 * MARKETING — clip 05 standalone (one-touch invoicing).
 *
 * Tolerant of the job's current state (a previous run may have already
 * started/completed it): only drives start/complete when the buttons are
 * there, and only adds an invoice line when none exists yet.
 *
 *   E2E_TENANT_SLUG=hartley-electrical \
 *   E2E_TRADE_EMAIL=tom@hartleyelectrical.example.com E2E_TRADE_PASSWORD='Sparky2026!' \
 *   pnpm exec wdio run wdio.sim.conf.ts --spec specs/93-marketing-invoice.spec.ts
 */
import { loginAsTrade } from "../helpers/auth";
import {
  byId,
  handlePermissionAlert,
  swipeUp,
  tapId,
  textElContains,
  waitForId,
  waitForText,
} from "../helpers/ui";
import { abortClip, scrollToIdAndTap, startClip, stopClip, typeSlowly } from "../demo/recorder";

const TOM_EMAIL = "tom@hartleyelectrical.example.com";
const TOM_PASSWORD = "Sparky2026!";

/**
 * The numeric pad has no return key and WDA can't hide it — but RN
 * ScrollViews blur their inputs on an outside tap (default
 * keyboardShouldPersistTaps). Tap neutral content until the keyboard goes.
 */
async function tapToDismissKeyboard(): Promise<void> {
  for (let i = 0; i < 4; i++) {
    let shown = false;
    try {
      shown = await driver.isKeyboardShown();
    } catch {
      /* assume shown */
    }
    if (!shown) return;
    const size = await driver.getWindowSize();
    await driver.performActions([
      {
        type: "pointer",
        id: "tap",
        parameters: { pointerType: "touch" },
        actions: [
          {
            type: "pointerMove",
            duration: 0,
            x: Math.round(size.width / 2),
            y: Math.round(size.height * 0.3),
          },
          { type: "pointerDown", button: 0 },
          { type: "pointerUp", button: 0 },
        ],
      },
    ]);
    await driver.releaseActions();
    await driver.pause(700);
  }
}

afterEach(async function () {
  const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
  if (state === "failed") await abortClip();
});

describe("M2b: marketing clip 05 — one-touch invoice", () => {
  before(function () {
    this.timeout(0);
  });

  it("05-one-touch-invoice", async () => {
    await loginAsTrade(TOM_EMAIL, TOM_PASSWORD);
    await waitForText("Dashboard", 25000);
    await handlePermissionAlert("allow");

    await startClip("05-one-touch-invoice");
    await tapId("tab-calendar");
    await waitForText("Calendar", 15000);
    await driver.pause(1500);
    // Today's EV charger booking.
    await textElContains("EV charger").waitForExist({ timeout: 15000 });
    await textElContains("EV charger").click();
    await waitForText("Job detail", 20000);
    await driver.pause(2000);

    // Drive the job lifecycle only if not already completed by a prior run.
    if (await byId("job-start").isExisting()) {
      await tapId("job-start");
      await textElContains("IN PROGRESS").waitForExist({ timeout: 15000 });
      await driver.pause(1500);
    }
    if (await byId("job-complete").isExisting()) {
      await tapId("job-complete");
      await textElContains("COMPLETED").waitForExist({ timeout: 15000 });
      await driver.pause(1500);
    }

    // Invoice items: add one line unless a previous attempt left one behind.
    const existingLine = driver.$(
      '-ios predicate string:name CONTAINS[c] "job-invoice-description"'
    );
    if (!(await existingLine.isExisting())) {
      await scrollToIdAndTap("job-add-variation");
      const desc = driver.$(
        '-ios predicate string:name CONTAINS[c] "job-invoice-description"'
      );
      await desc.waitForExist({ timeout: 15000 });
      await typeSlowly(
        desc,
        "7kW EV charger — install, certification and DNO notification"
      );
      const amount = driver.$(
        '-ios predicate string:name CONTAINS[c] "job-invoice-amount"'
      );
      await amount.waitForExist({ timeout: 15000 });
      await typeSlowly(amount, "1240");
    }
    // The numeric keyboard covers the footer button — blur the field first,
    // then scroll once more so the footer is fully clear of the keyboard.
    await tapToDismissKeyboard();
    await swipeUp();
    await driver.pause(1200);
    await scrollToIdAndTap("job-create-invoice");
    // If an invoice already exists from a previous run, open it instead.
    if (await textElContains("View invoice").isExisting()) {
      await textElContains("View invoice").click();
    }

    // Invoice detail: SENT badge, total, line items.
    await waitForId("invoice-total", 20000);
    await driver.pause(3000);
    await swipeUp();
    await driver.pause(2000);
    if (await byId("invoice-mark-paid").isExisting()) {
      await tapId("invoice-mark-paid");
      await textElContains("Payment received").waitForExist({ timeout: 15000 });
      await driver.pause(2500);
    }
    await stopClip("05-one-touch-invoice");
  });
});
