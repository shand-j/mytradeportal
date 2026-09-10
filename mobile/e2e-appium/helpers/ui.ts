/**
 * Selector + interaction helpers for the RN app on iOS (XCUITest).
 *
 * Strategy: components forward `testID` → iOS accessibility identifier
 * (queried with `~id`). Where no testID exists we match the visible text on
 * the underlying StaticText — RN Pressable receives touches on children, so
 * tapping the text activates the button.
 */

import { BUNDLE_ID } from "./env";

/** Element by accessibility identifier (testID). */
export const byId = (id: string) => $(`~${id}`);

/** Element by visible label (any type).
 *
 * RN Pressable buttons collapse into a single XCUIElementTypeOther carrying
 * the title as its label — they are NOT StaticText. An NSPredicate matches
 * any element type so both real text and buttons are found.
 */
export const textEl = (label: string) =>
  $(`-ios predicate string:label == "${esc(label)}"`);

/** Any element whose label contains the given string (case-insensitive). */
export const textElContains = (label: string) =>
  $(`-ios predicate string:label CONTAINS[c] "${esc(label)}"`);

function esc(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

/** True when our app (not e.g. Calendar/Mail opened by a notification) is foregrounded. */
async function isAppForeground() {
  try {
    return (await driver.queryAppState(BUNDLE_ID)) === 4;
  } catch {
    return true; // don't block the test on a probe failure
  }
}

/** Bring the app back if iOS switched away (notification tap, deep link). */
export async function ensureForeground() {
  if (await isAppForeground()) return;
  await driver.activateApp(BUNDLE_ID);
  await driver.pause(1200);
}

export async function waitForText(label: string, timeoutMs = 15000) {
  const el = textEl(label);
  await el.waitForExist({ timeout: timeoutMs });
  return el;
}

export async function waitForId(id: string, timeoutMs = 15000) {
  const el = byId(id);
  await el.waitForExist({ timeout: timeoutMs });
  return el;
}

export async function tapText(label: string, timeoutMs = 15000) {
  await ensureForeground();
  const el = await waitForText(label, timeoutMs);
  await el.click();
}

export async function tapId(id: string, timeoutMs = 15000) {
  await ensureForeground();
  const el = await waitForId(id, timeoutMs);
  await el.click();
}

/** Open the customer profile: bottom tab on new builds, header action otherwise. */
export async function openCustomerProfile() {
  const tab = byId("tab-profile");
  if (await tab.isExisting()) {
    await tab.click();
    return;
  }
  const hdr = textEl("Profile");
  await hdr.waitForExist({ timeout: 15000 });
  await hdr.click();
}

/**
 * Open the trade settings screen from any trade tab page.
 * The dashboard header uses `dashboard-more`; other main tabs use the shared
 * `header-settings` three-dot button (both carry the "Settings" label).
 * Clicks are verified: a tap right after a tab switch can be swallowed by the
 * settling ScrollView, so retry until the settings screen actually opens.
 */
export async function openTradeSettings() {
  const settingsProbe = byId("settings-logout");
  for (let attempt = 0; attempt < 3; attempt++) {
    const dash = byId("dashboard-more");
    if (await dash.isExisting()) {
      await dash.click();
    } else {
      const header = byId("header-settings");
      if (await header.isExisting()) {
        await header.click();
      } else {
        await tapText("Settings", 8000);
      }
    }
    if (await settingsProbe.waitForExist({ timeout: 8000 }).then(() => true).catch(() => false)) {
      return;
    }
    await driver.pause(800);
  }
  throw new Error("openTradeSettings: settings screen did not open after 3 attempts");
}

/** True when the given text is on screen now (no waiting). */
export async function hasText(label: string): Promise<boolean> {
  return textEl(label).isExisting();
}

/** Scroll until an element with the given text is visible, then tap it. */
export async function scrollToTextAndTap(
  label: string,
  opts: { scrollId?: string; timeoutMs?: number } = {}
) {
  const timeout = opts.timeoutMs ?? 20000;
  const start = Date.now();
  // RN ScrollViews respond to class-chain scrollToVisible via XCUITest's
  // scroll strategy only on the first scrollable ancestor; simpler and more
  // reliable on RN is repeated swipe-up until the text exists.
  while (!(await textEl(label).isExisting())) {
    if (Date.now() - start > timeout) {
      throw new Error(`scrollToTextAndTap timed out looking for text: ${label}`);
    }
    await swipeUp();
    await driver.pause(350);
  }
  await tapText(label);
}

export async function swipeUp() {
  const size = await driver.getWindowSize();
  const x = Math.round(size.width / 2);
  const fromY = Math.round(size.height * 0.72);
  const toY = Math.round(size.height * 0.28);
  await driver.performActions([
    {
      type: "pointer",
      id: "swipe",
      parameters: { pointerType: "touch" },
      actions: [
        { type: "pointerMove", duration: 0, x, y: fromY },
        { type: "pointerDown", button: 0 },
        { type: "pointerMove", duration: 350, x, y: toY },
        { type: "pointerUp", button: 0 },
      ],
    },
  ]);
  await driver.releaseActions();
}

/** Back chevron rendered by our Header (testID back-button). */
export async function tapBack() {
  await tapId("back-button", 8000);
}

/**
 * Handle a SpringBoard permission alert if one is showing. Returns the
 * decision taken ("allow" | "deny" | null).
 */
export async function handlePermissionAlert(
  decision: "allow" | "deny"
): Promise<"allow" | "deny" | null> {
  // Appium's alert API reaches SpringBoard alerts on XCUITest.
  try {
    const text = await driver.getAlertText();
    const allow = await driver.$("~Allow");
    const allowAlways = await driver.$("~Allow While Using App");
    const ok = await driver.$("~OK");
    const target = decision === "allow" ? (await allow.isExisting()) ? allow : (await allowAlways.isExisting()) ? allowAlways : ok : await driver.$("~Don't Allow");
    if (await target.isExisting()) {
      await target.click();
      return decision;
    }
    void text;
  } catch {
    /* no alert — fine */
  }
  return null;
}

/**
 * Dismiss the software keyboard. `hideKeyboard` usually fails on RN apps
 * ("Did not know how to dismiss the keyboard"), and iOS exposes Return/Done
 * as a Button, not a Key — so tap that first, then fall back.
 */
export async function dismissKeyboard() {
  try {
    if (!(await driver.isKeyboardShown())) return;
  } catch {
    /* proceed anyway */
  }
  const returnKey = await driver.$(
    `-ios predicate string:(type == 'XCUIElementTypeKey' OR type == 'XCUIElementTypeButton') AND label IN {'return','Return','Done','done','Search','Go','Next'}`
  );
  if (await returnKey.isExisting()) {
    await returnKey.click();
    await driver.pause(300);
    return;
  }
  try {
    await driver.hideKeyboard();
    return;
  } catch {
    /* last resort below */
  }
  // Tap the status-bar area to defocus.
  const size = await driver.getWindowSize();
  await driver.performActions([
    {
      type: "pointer",
      id: "tap",
      parameters: { pointerType: "touch" },
      actions: [
        { type: "pointerMove", duration: 0, x: Math.round(size.width / 2), y: 80 },
        { type: "pointerDown", button: 0 },
        { type: "pointerUp", button: 0 },
      ],
    },
  ]);
  await driver.releaseActions();
  await driver.pause(300);
}

/**
 * Dismiss the iCloud Keychain "Save Password?" prompt if one is showing.
 * It appears over the app after password entry and swallows every tap.
 */
export async function dismissPasswordPrompt(): Promise<boolean> {
  // The prompt animates in asynchronously after the triggering tap, so poll.
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    try {
      const notNow = await driver.$("~Not Now");
      if (await notNow.isExisting()) {
        await notNow.click();
        await driver.pause(500);
        return true;
      }
      // SpringBoard alerts: reach it via the alert API and cancel it.
      const alertText = await driver.getAlertText();
      if (/save (this )?password/i.test(String(alertText))) {
        await driver.dismissAlert();
        await driver.pause(500);
        return true;
      }
    } catch {
      /* no prompt — keep polling */
    }
    await driver.pause(400);
  }
  return false;
}

/** Dismiss any open alert by tapping its first button (e.g. OK). */
export async function dismissAlertIfAny() {  try {
    const buttons = await driver.$$("-ios predicate string:type == 'XCUIElementTypeButton'");
    const n: number = await buttons.length;
    if (n > 0) {
      const last = await buttons[n - 1];
      await last.click();
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

/** Wait for the app to be in the foreground. */
export async function waitAppReady(timeoutMs = 20000) {
  await driver.waitUntil(async () => (await driver.queryAppState(BUNDLE_ID)) === 4, {
    timeout: timeoutMs,
    timeoutMsg: "App did not reach foreground state",
  });
}
